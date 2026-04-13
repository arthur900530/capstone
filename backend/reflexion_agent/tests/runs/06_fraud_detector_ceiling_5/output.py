from dataclasses import dataclass
from typing import List, Dict, FrozenSet
import csv
import json
from datetime import datetime, timedelta


@dataclass
class FraudAlert:
    alert_type: str       # "rapid_duplicate", "structuring", or "round_trip"
    tx_ids: frozenset     # set of transaction IDs involved
    account: str          # the primary account flagged
    description: str      # human-readable explanation
    aggregate_usd: float  # total USD amount involved (0.0 if not applicable)


def load_transactions(csv_path: str) -> List[Dict]:
    """Load transactions from CSV. amount is converted to float, timestamp to datetime."""
    txns = []
    with open(csv_path, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Convert amount to float
            row['amount'] = float(row['amount'])
            # Parse timestamp into datetime for easier comparisons
            try:
                row['timestamp'] = datetime.strptime(row['timestamp'], "%Y-%m-%d %H:%M:%S")
            except Exception:
                # If parsing fails, keep original string
                pass
            txns.append(row)
    return txns


def normalize_to_usd(amount: float, currency: str, fx_path: str) -> float:
    """Convert amount from given currency to USD using fx rates file."""
    with open(fx_path) as f:
        data = json.load(f)
    rates = data.get('rates', {})
    if currency not in rates:
        raise ValueError(f"Unknown currency: {currency}")
    rate = rates[currency]
    return float(amount * rate)


def detect_rapid_duplicates(txns: List[Dict]) -> List[FraudAlert]:
    """Detect transactions with same (from,to,amount) within 5 minutes."""
    # Group by key
    groups = {}
    for t in txns:
        key = (t.get('account_from'), t.get('account_to'), t.get('amount'), t.get('currency'))
        groups.setdefault(key, []).append(t)

    alerts = []
    seen = set()  # set of frozenset(tx_ids) to avoid duplicates
    window_seconds = 5 * 60

    for key, items in groups.items():
        # Sort by timestamp
        items_sorted = sorted(items, key=lambda x: x.get('timestamp'))
        n = len(items_sorted)
        for i in range(n):
            for j in range(i + 1, n):
                t1 = items_sorted[i]
                t2 = items_sorted[j]
                # compute time delta in seconds; if timestamp isn't datetime, skip
                ts1 = t1.get('timestamp')
                ts2 = t2.get('timestamp')
                if not isinstance(ts1, datetime) or not isinstance(ts2, datetime):
                    continue
                delta = abs((ts2 - ts1).total_seconds())
                if delta <= window_seconds:
                    tx_ids = frozenset({t1.get('tx_id'), t2.get('tx_id')})
                    if tx_ids in seen:
                        continue
                    seen.add(tx_ids)
                    desc = (
                        f"Rapid duplicate: {t1.get('account_from')}->{t1.get('account_to')}"
                        f" amount {t1.get('amount')} {t1.get('currency')} within {delta} seconds"
                    )
                    alert = FraudAlert(
                        alert_type='rapid_duplicate',
                        tx_ids=tx_ids,
                        account=t1.get('account_from'),
                        description=desc,
                        aggregate_usd=0.0,
                    )
                    alerts.append(alert)
                else:
                    # Since items_sorted is time-ordered, if delta exceeds window for this j,
                    # further j will only be larger deltas; but we cannot break because earlier i may pair with later j.
                    # However we can break inner loop for efficiency here.
                    break
    return alerts


def detect_structuring(txns: List[Dict], fx_path: str) -> List[FraudAlert]:
    """Detect structuring: 3+ outgoing wire transfers in 24 hours where each
    individual amount is <= 10,000 USD and aggregate exceeds 25,000 USD.
    """
    # Collect outgoing wire transfers per account
    outgoing = {}
    for t in txns:
        # treat category case-insensitively
        if str(t.get('category')).lower() != 'wire':
            continue
        acct = t.get('account_from')
        try:
            amount_usd = normalize_to_usd(t.get('amount'), t.get('currency'), fx_path)
        except ValueError:
            # skip unknown currency
            continue
        # consider amounts <= 10000.0 (inclusive) as potential structuring
        if amount_usd <= 10000.0:
            outgoing.setdefault(acct, []).append({
                'tx': t,
                'timestamp': t.get('timestamp'),
                'amount_usd': amount_usd,
            })

    alerts = []
    seen = set()
    window_seconds = 24 * 3600

    for acct, items in outgoing.items():
        items_sorted = sorted(items, key=lambda x: x['timestamp'])
        n = len(items_sorted)
        left = 0
        for right in range(n):
            # Move left pointer to maintain window <= 24h
            while left <= right and (not isinstance(items_sorted[right]['timestamp'], datetime) or not isinstance(items_sorted[left]['timestamp'], datetime) or (items_sorted[right]['timestamp'] - items_sorted[left]['timestamp']).total_seconds() > window_seconds):
                left += 1
            # Consider current window [left, right]
            window_size = right - left + 1
            if window_size >= 3:
                tx_ids = frozenset({items_sorted[k]['tx']['tx_id'] for k in range(left, right + 1)})
                if tx_ids in seen:
                    continue
                aggregate = sum(items_sorted[k]['amount_usd'] for k in range(left, right + 1))
                if aggregate > 25000.0:
                    seen.add(tx_ids)
                    # Round aggregate to cents for stability
                    aggregate_rounded = round(aggregate, 2)
                    desc = (
                        f"Structuring detected for {acct}: {window_size} wire transfers totaling ${aggregate_rounded} within 24h"
                    )
                    alert = FraudAlert(
                        alert_type='structuring',
                        tx_ids=tx_ids,
                        account=acct,
                        description=desc,
                        aggregate_usd=aggregate_rounded,
                    )
                    alerts.append(alert)
    return alerts


def detect_round_trip(txns: List[Dict], fx_path: str) -> List[FraudAlert]:
    """Detect round-trip A->B then B->A with matching amounts within 2% and 48 hours."""
    alerts = []
    seen = set()
    # Build index of transactions by (from,to)
    by_pair = {}
    for t in txns:
        key = (t.get('account_from'), t.get('account_to'))
        by_pair.setdefault(key, []).append(t)

    # For each pair A->B, look for B->A
    for (a, b), forward_list in by_pair.items():
        reverse_list = by_pair.get((b, a), [])
        if not reverse_list:
            continue
        # compare each forward tx with each reverse tx
        for f in forward_list:
            for r in reverse_list:
                # ensure distinct transactions
                if f.get('tx_id') == r.get('tx_id'):
                    continue
                ts_f = f.get('timestamp')
                ts_r = r.get('timestamp')
                if not isinstance(ts_f, datetime) or not isinstance(ts_r, datetime):
                    continue
                if abs((ts_r - ts_f).total_seconds()) > 48 * 3600:
                    continue
                # normalize both amounts
                try:
                    a_usd = normalize_to_usd(f.get('amount'), f.get('currency'), fx_path)
                    b_usd = normalize_to_usd(r.get('amount'), r.get('currency'), fx_path)
                except ValueError:
                    continue
                # tolerance 2% of original amount (use a_usd)
                tol = 0.02 * a_usd
                if abs(a_usd - b_usd) <= tol:
                    tx_ids = frozenset({f.get('tx_id'), r.get('tx_id')})
                    if tx_ids in seen:
                        continue
                    seen.add(tx_ids)
                    desc = (
                        f"Round-trip between {a} and {b}: {f.get('tx_id')}->{r.get('tx_id')} "
                        f"amounts ${round(a_usd,2)} and ${round(b_usd,2)} within 48h"
                    )
                    alert = FraudAlert(
                        alert_type='round_trip',
                        tx_ids=tx_ids,
                        account=a,
                        description=desc,
                        aggregate_usd=round(a_usd + b_usd, 2),
                    )
                    alerts.append(alert)
    return alerts


def generate_report(txns: List[Dict], fx_path: str) -> Dict:
    rapid = detect_rapid_duplicates(txns)
    struct = detect_structuring(txns, fx_path)
    rounds = detect_round_trip(txns, fx_path)
    total = len(rapid) + len(struct) + len(rounds)
    return {
        "rapid_duplicates": rapid,
        "structuring": struct,
        "round_trips": rounds,
        "summary": {"total_alerts": total},
    }
