#!/usr/bin/env bash
set -euo pipefail

REPORT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(git -C "$REPORT_DIR" rev-parse --show-toplevel)"

EVIDENCE_REF="${EVIDENCE_REF:-origin/main}"
REPORT_MD="${REPORT_MD:-$REPORT_DIR/TECHNICAL_CONTRIBUTION_ASSIGNMENT.md}"
TIMELINE_SVG="$REPORT_DIR/contribution_timeline.svg"
PDF_OUT="${PDF_OUT:-$REPORT_DIR/contribution_report.pdf}"
CSS_FILE="$REPORT_DIR/report.css"

if ! git -C "$ROOT" rev-parse --verify --quiet "$EVIDENCE_REF" >/dev/null; then
  printf 'Evidence ref not found: %s\n' "$EVIDENCE_REF" >&2
  printf 'Fetch refs or override with EVIDENCE_REF=main.\n' >&2
  exit 1
fi

for cmd in pandoc python3; do
  if ! command -v "$cmd" >/dev/null; then
    printf 'Missing required command: %s\n' "$cmd" >&2
    exit 1
  fi
done

CHROME_BIN="${CHROME_BIN:-}"
if [[ -z "$CHROME_BIN" ]]; then
  CHROME_BIN="$(command -v chromium || command -v chromium-browser || command -v google-chrome || true)"
fi
if [[ -z "$CHROME_BIN" ]]; then
  printf 'Missing Chromium/Chrome. Set CHROME_BIN=/path/to/chrome and retry.\n' >&2
  exit 1
fi

python3 - "$ROOT" "$EVIDENCE_REF" "$TIMELINE_SVG" <<'PY'
from __future__ import annotations

import datetime as dt
import html
import subprocess
import sys
from collections import defaultdict

root, evidence_ref, output = sys.argv[1:4]

raw = subprocess.check_output(
    [
        "git",
        "-C",
        root,
        "log",
        evidence_ref,
        "--no-merges",
        "--date=short",
        "--format=%ad%x09%H%x09%aN",
    ],
    text=True,
)

author_order = [
    "Aditya Kumar",
    "Andrew Zhang",
    "Arthur Chien",
    "Aspen Chen",
    "Danni Qu / Angela",
    "Hin Kit Eric Wong",
    "Yuling Wang",
]
colors = {
    "Aditya Kumar": "#2563eb",
    "Andrew Zhang": "#dc2626",
    "Arthur Chien": "#7c3aed",
    "Aspen Chen": "#059669",
    "Danni Qu / Angela": "#d97706",
    "Hin Kit Eric Wong": "#0891b2",
    "Yuling Wang": "#4b5563",
}


def normalize_author(author: str, commit: str) -> str:
    if commit.startswith("86d234a"):
        return "Hin Kit Eric Wong"
    if author in {"Andrew Zhang", "andrew-yifanzhang"}:
        return "Andrew Zhang"
    if author == "AspenC":
        return "Aspen Chen"
    if author == "Danni Qu":
        return "Danni Qu / Angela"
    if author == "Yuling":
        return "Yuling Wang"
    return author


def week_start(date_text: str) -> dt.date:
    day = dt.date.fromisoformat(date_text)
    return day - dt.timedelta(days=day.weekday())


counts: dict[tuple[str, dt.date], int] = defaultdict(int)
weeks: set[dt.date] = set()
totals: dict[str, int] = defaultdict(int)

for line in raw.splitlines():
    if not line.strip():
        continue
    date_text, commit, author = line.split("\t", 2)
    author = normalize_author(author, commit)
    week = week_start(date_text)
    counts[(author, week)] += 1
    totals[author] += 1
    weeks.add(week)

weeks_sorted = sorted(weeks)
authors = [author for author in author_order if totals.get(author, 0)]

width = 1120
height = 620
left = 80
right = 24
top = 64
bottom = 128
plot_w = width - left - right
plot_h = height - top - bottom
max_count = max(counts.values() or [1])
max_axis = max(10, ((max_count + 9) // 10) * 10)
group_w = plot_w / max(1, len(weeks_sorted))
bar_gap = 2
bar_w = max(4, (group_w - 18) / max(1, len(authors)) - bar_gap)

parts: list[str] = [
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
    "<title id=\"title\">Merged non-merge commit timeline by week</title>",
    "<desc id=\"desc\">Weekly merged non-merge commit counts by contributor from git history.</desc>",
    '<rect width="100%" height="100%" fill="#ffffff"/>',
    f'<text x="{left}" y="32" font-family="Inter, Arial, sans-serif" font-size="22" font-weight="700" fill="#102a43">Merged non-merge commit timeline by week</text>',
    f'<text x="{left}" y="52" font-family="Inter, Arial, sans-serif" font-size="12" fill="#52606d">Evidence ref: {html.escape(evidence_ref)}. Merge commits excluded.</text>',
]

for tick in range(0, max_axis + 1, 10):
    y = top + plot_h - (tick / max_axis) * plot_h
    parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" stroke="#e5e7eb" stroke-width="1"/>')
    parts.append(f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" font-family="Inter, Arial, sans-serif" font-size="11" fill="#52606d">{tick}</text>')

parts.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#9aa5b1" stroke-width="1"/>')
parts.append(f'<line x1="{left}" y1="{top + plot_h}" x2="{width - right}" y2="{top + plot_h}" stroke="#9aa5b1" stroke-width="1"/>')

for wi, week in enumerate(weeks_sorted):
    group_x = left + wi * group_w + 9
    label_x = left + wi * group_w + group_w / 2
    for ai, author in enumerate(authors):
        value = counts.get((author, week), 0)
        bar_h = (value / max_axis) * plot_h
        x = group_x + ai * (bar_w + bar_gap)
        y = top + plot_h - bar_h
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" fill="{colors.get(author, "#64748b")}">'
            f'<title>{html.escape(author)}: {value} commits in week of {week.isoformat()}</title></rect>'
        )
    parts.append(
        f'<text x="{label_x:.1f}" y="{top + plot_h + 18}" text-anchor="middle" font-family="Inter, Arial, sans-serif" font-size="11" fill="#52606d">{week.strftime("%m-%d")}</text>'
    )

legend_x = left
legend_y = height - 82
legend_step = 158
for i, author in enumerate(authors):
    x = legend_x + (i % 4) * legend_step
    y = legend_y + (i // 4) * 26
    parts.append(f'<rect x="{x}" y="{y - 11}" width="13" height="13" fill="{colors.get(author, "#64748b")}"/>')
    parts.append(
        f'<text x="{x + 19}" y="{y}" font-family="Inter, Arial, sans-serif" font-size="12" fill="#243b53">{html.escape(author)} ({totals[author]})</text>'
    )

parts.append("</svg>\n")

with open(output, "w", encoding="utf-8", newline="\n") as handle:
    handle.write("\n".join(parts))
PY

HTML_OUT="$(mktemp "$REPORT_DIR/.contribution_report.XXXXXX.html")"
trap 'rm -f "$HTML_OUT"' EXIT

pandoc "$REPORT_MD" \
  --from gfm \
  --to html5 \
  --standalone \
  --embed-resources \
  --resource-path="$REPORT_DIR" \
  --metadata pagetitle="Contribution Report" \
  --css "$CSS_FILE" \
  --output "$HTML_OUT"

"$CHROME_BIN" \
  --headless \
  --disable-gpu \
  --no-sandbox \
  --no-pdf-header-footer \
  --print-to-pdf="$PDF_OUT" \
  "file://$HTML_OUT" >/dev/null

printf 'Wrote %s\n' "$TIMELINE_SVG"
printf 'Wrote %s\n' "$PDF_OUT"
