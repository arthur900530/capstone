"""
Strict test suite for fraud_detector.py — a transaction fraud analysis engine.

The detector must:
  1. Load transactions.csv and fx_rates.json
  2. Normalize all amounts to USD using the FX rates
  3. Detect three types of suspicious patterns
  4. Produce a structured fraud report

ALL 18 tests must pass: pytest test_fraud_detector.py -v
"""
import pytest
import json
from fraud_detector import (
    load_transactions,
    normalize_to_usd,
    detect_rapid_duplicates,
    detect_structuring,
    detect_round_trip,
    generate_report,
    FraudAlert,
)


# ===========================================================================
# Data loading
# ===========================================================================

class TestLoadTransactions:

    def test_loads_correct_count(self):
        txns = load_transactions("transactions.csv")
        assert len(txns) == 25

    def test_fields_present(self):
        txns = load_transactions("transactions.csv")
        required = {"tx_id", "timestamp", "account_from", "account_to",
                     "amount", "currency", "category"}
        assert required.issubset(set(txns[0].keys()))

    def test_amount_is_float(self):
        txns = load_transactions("transactions.csv")
        assert all(isinstance(t["amount"], float) for t in txns)


# ===========================================================================
# FX normalization
# ===========================================================================

class TestNormalize:

    def test_usd_unchanged(self):
        assert normalize_to_usd(100.0, "USD", "fx_rates.json") == 100.0

    def test_eur_to_usd(self):
        result = normalize_to_usd(200.0, "EUR", "fx_rates.json")
        assert result == pytest.approx(216.0, abs=0.01)

    def test_gbp_to_usd(self):
        result = normalize_to_usd(500.0, "GBP", "fx_rates.json")
        assert result == pytest.approx(635.0, abs=0.01)

    def test_unknown_currency_raises(self):
        with pytest.raises(ValueError):
            normalize_to_usd(100.0, "JPY", "fx_rates.json")


# ===========================================================================
# Pattern 1: Rapid duplicates
# Two or more transactions with the same (account_from, account_to, amount)
# within a 5-minute window.
# ===========================================================================

class TestRapidDuplicates:

    def test_finds_acc1001_to_acc5050_cluster(self):
        """T005, T006, T007 — ACC-1001→ACC-5050 within 2.5 min, amounts ~$10K."""
        txns = load_transactions("transactions.csv")
        alerts = detect_rapid_duplicates(txns)
        ids_in_alerts = {a.tx_ids for a in alerts}
        assert frozenset({"T005", "T006"}) in ids_in_alerts

    def test_finds_acc3010_to_acc9090_pair(self):
        """T012, T013 — ACC-3010→ACC-9090, same amount within 1 min."""
        txns = load_transactions("transactions.csv")
        alerts = detect_rapid_duplicates(txns)
        ids_in_alerts = {a.tx_ids for a in alerts}
        assert frozenset({"T012", "T013"}) in ids_in_alerts

    def test_finds_acc4020_to_acc5050_pair(self):
        """T016, T017 — ACC-4020→ACC-5050, same amount within 1 min."""
        txns = load_transactions("transactions.csv")
        alerts = detect_rapid_duplicates(txns)
        ids_in_alerts = {a.tx_ids for a in alerts}
        assert frozenset({"T016", "T017"}) in ids_in_alerts

    def test_total_rapid_duplicate_alerts(self):
        txns = load_transactions("transactions.csv")
        alerts = detect_rapid_duplicates(txns)
        assert len(alerts) >= 3


# ===========================================================================
# Pattern 2: Structuring (smurfing)
# A single account sends 3+ outgoing wire transfers within 24 hours where
# each individual amount is below $10,000 USD but the aggregate exceeds $25,000.
# ===========================================================================

class TestStructuring:

    def test_finds_acc1001_jan7(self):
        """T005 ($10K) + T006 ($10K) + T007 ($9999.99) on Jan 7 — aggregate $29,999.99."""
        txns = load_transactions("transactions.csv")
        alerts = detect_structuring(txns, "fx_rates.json")
        accounts = {a.account for a in alerts}
        assert "ACC-1001" in accounts

    def test_finds_acc1001_jan30(self):
        """T024 ($9999.99) + T025 ($9999.99) on Jan 30 — only 2 txns, should NOT trigger."""
        txns = load_transactions("transactions.csv")
        alerts = detect_structuring(txns, "fx_rates.json")
        jan30_alerts = [a for a in alerts if "T024" in a.tx_ids or "T025" in a.tx_ids]
        assert len(jan30_alerts) == 0

    def test_structuring_alert_has_aggregate(self):
        txns = load_transactions("transactions.csv")
        alerts = detect_structuring(txns, "fx_rates.json")
        acc1001 = [a for a in alerts if a.account == "ACC-1001"]
        assert len(acc1001) >= 1
        assert acc1001[0].aggregate_usd == pytest.approx(29999.99, abs=0.02)


# ===========================================================================
# Pattern 3: Round-trip detection
# Money flows A→B then B→A with matching amounts (after FX normalization)
# within 48 hours. Tolerance: 2% of original amount.
# ===========================================================================

class TestRoundTrip:

    def test_finds_eur_refund_round_trip(self):
        """T003 (ACC-1001→ACC-4020, €200) and T004 (ACC-4020→ACC-1001, €200)."""
        txns = load_transactions("transactions.csv")
        alerts = detect_round_trip(txns, "fx_rates.json")
        pairs = {a.tx_ids for a in alerts}
        assert frozenset({"T003", "T004"}) in pairs

    def test_finds_gbp_refund_round_trip(self):
        """T010 (ACC-2005→ACC-8080, £500) and T011 (ACC-8080→ACC-2005, £500)."""
        txns = load_transactions("transactions.csv")
        alerts = detect_round_trip(txns, "fx_rates.json")
        pairs = {a.tx_ids for a in alerts}
        assert frozenset({"T010", "T011"}) in pairs


# ===========================================================================
# Report generation
# ===========================================================================

class TestReport:

    def test_report_is_dict(self):
        txns = load_transactions("transactions.csv")
        report = generate_report(txns, "fx_rates.json")
        assert isinstance(report, dict)

    def test_report_has_all_sections(self):
        txns = load_transactions("transactions.csv")
        report = generate_report(txns, "fx_rates.json")
        assert "rapid_duplicates" in report
        assert "structuring" in report
        assert "round_trips" in report
        assert "summary" in report

    def test_summary_total_alerts(self):
        txns = load_transactions("transactions.csv")
        report = generate_report(txns, "fx_rates.json")
        total = report["summary"]["total_alerts"]
        assert total >= 6
