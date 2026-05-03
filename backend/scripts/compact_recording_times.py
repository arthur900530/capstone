"""Compact a recording's timestamps for snappy demo playback.

The agent's natural pace is fine for live runs but feels glacial when
played back as a demo (a 10-minute capture takes 10 minutes to replay).
This script walks the events / submits / browser frames of a recording,
reassigns each ``t`` so the deltas between consecutive entries collapse
into a much shorter range with a bit of randomness so the replay still
feels organic instead of metronome-perfect.

Two-stage design so chat trajectory and noVNC framebuffer stay in lock-step:

  1. Submits + events are compacted on their own clock using bucketed
     inter-event deltas. This gives the trajectory a tight, snappy pace
     without being dragged down by hundreds of intervening RFB frames.
  2. Each browser frame's ``t`` is then *interpolated* onto the same
     compressed clock by finding which (submit/event)→(submit/event)
     segment it originally lived in and placing it at the same fractional
     position inside the corresponding compressed segment. A frame that
     was 30% of the way between ``tool_call`` and ``tool_result`` in the
     original recording will still be 30% of the way between them after
     compaction, just inside a much shorter window.

The result: the noVNC <canvas> visibly updates at exactly the same chat
events as in the original run, even after a 10-minute recording is
crunched to a 30-second demo.

Usage:
    python scripts/compact_recording_times.py recordings/_default.json
    python scripts/compact_recording_times.py recordings/_default.json --target-seconds 30
"""

from __future__ import annotations

import argparse
import bisect
import json
import random
import sys
from pathlib import Path
from typing import Any


def _bucket_delta(orig_delta_ms: int, rng: random.Random) -> int:
    """Map an original inter-event delta to a compressed delta.

    Brackets are intentionally coarse — we want every bucket to feel
    qualitatively like the original (instant / fast / pause / long wait)
    without being literal:

        <50ms     -> 10..40ms      ("same instant", e.g. tool_call -> tool_result)
        <500ms    -> 40..120ms     ("fast follow")
        <2s       -> 150..400ms    ("quick step")
        <10s      -> 350..900ms    ("thinking pause")
        anything  -> 700..1500ms   ("longer wait", capped)
    """
    if orig_delta_ms <= 0:
        return rng.randint(0, 8)
    if orig_delta_ms < 50:
        return rng.randint(10, 40)
    if orig_delta_ms < 500:
        return rng.randint(40, 120)
    if orig_delta_ms < 2_000:
        return rng.randint(150, 400)
    if orig_delta_ms < 10_000:
        return rng.randint(350, 900)
    return rng.randint(700, 1500)


def _scale_to_target(
    items: list[dict[str, Any]],
    target_ms: int,
    last_overall: int,
) -> list[dict[str, Any]]:
    """Linearly scale all ``t`` values by ``target_ms / last_overall``.

    We pass ``last_overall`` (the max ``t`` across submits + events +
    frames combined) so submits, events, and frames all use the *same*
    scale factor and stay synchronized.
    """
    if not items or target_ms <= 0 or last_overall <= 0:
        return items
    scale = target_ms / last_overall
    return [
        {**it, "t": int(round(int(it.get("t", 0)) * scale))} for it in items
    ]


def _build_anchor_timeline(
    submits: list[dict[str, Any]],
    events: list[dict[str, Any]],
    rng: random.Random,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[int], list[int]]:
    """Assign new compressed ``t`` to each submit/event using bucketed deltas.

    Returns ``(new_submits, new_events, anchor_orig_ts, anchor_new_ts)``
    where the latter two are sorted, parallel lists giving the
    old→new time mapping. We later use them to interpolate frame times.
    """
    anchors: list[tuple[int, str, int]] = []
    for i, s in enumerate(submits):
        anchors.append((int(s.get("t", 0)), "submit", i))
    for i, e in enumerate(events):
        anchors.append((int(e.get("t", 0)), "event", i))
    # Stable order: submits before events at the same timestamp so a
    # submit that opens a turn always lands first in the compressed clock.
    anchors.sort(key=lambda a: (a[0], 0 if a[1] == "submit" else 1))

    new_by_kind_idx: dict[tuple[str, int], int] = {}
    anchor_orig_ts: list[int] = []
    anchor_new_ts: list[int] = []

    cur = 0
    prev_orig = 0
    for idx, (orig_t, kind, item_idx) in enumerate(anchors):
        if idx == 0:
            cur = 0
        else:
            cur += _bucket_delta(orig_t - prev_orig, rng)
        new_by_kind_idx[(kind, item_idx)] = cur
        anchor_orig_ts.append(orig_t)
        anchor_new_ts.append(cur)
        prev_orig = orig_t

    new_submits = [
        {**s, "t": new_by_kind_idx[("submit", i)]} for i, s in enumerate(submits)
    ]
    new_events = [
        {**e, "t": new_by_kind_idx[("event", i)]} for i, e in enumerate(events)
    ]
    return new_submits, new_events, anchor_orig_ts, anchor_new_ts


def _remap_frames_onto_anchors(
    frames: list[dict[str, Any]],
    anchor_orig_ts: list[int],
    anchor_new_ts: list[int],
    rng: random.Random,
) -> list[dict[str, Any]]:
    """Place each browser frame inside the compressed timeline.

    Strategy is piecewise-linear interpolation between anchors so a
    frame that was 25% into the original ``event[i] → event[i+1]``
    window lands 25% into the *compressed* ``event[i] → event[i+1]``
    window. This keeps the noVNC framebuffer in sync with whatever
    tool call / tool result was being emitted at the time.

    Frames outside the anchor range get scaled proportionally:
      - before the first anchor (e.g. initial framebuffer handshake
        before the agent says anything): linear from 0 → first anchor.
      - after the last anchor (rare; only happens if recorder kept
        capturing after the final event): extended at the same
        compression ratio as the last bucketed segment.
    """
    if not frames:
        return []
    if not anchor_orig_ts:
        # Recording has frames but no submits / events to anchor against.
        # Fall back to bucketing frames against their own deltas so we
        # at least produce a snappy framebuffer-only replay.
        out: list[dict[str, Any]] = []
        cur = 0
        prev_orig = 0
        for i, f in enumerate(frames):
            orig_t = int(f.get("t", 0))
            if i > 0:
                cur += _bucket_delta(orig_t - prev_orig, rng)
            out.append({**f, "t": cur})
            prev_orig = orig_t
        return out

    first_orig = anchor_orig_ts[0]
    first_new = anchor_new_ts[0]
    last_orig = anchor_orig_ts[-1]
    last_new = anchor_new_ts[-1]

    # Tail compression ratio: copy the last segment's old→new ratio so
    # post-trailing-anchor frames still feel like the rest of the run.
    if len(anchor_orig_ts) >= 2:
        seg_o = anchor_orig_ts[-1] - anchor_orig_ts[-2]
        seg_n = anchor_new_ts[-1] - anchor_new_ts[-2]
        tail_ratio = (seg_n / seg_o) if seg_o > 0 else 0.0
    else:
        tail_ratio = 0.0

    out: list[dict[str, Any]] = []
    for f in frames:
        T = int(f.get("t", 0))
        if T <= first_orig:
            new_t = (
                int(round(T / first_orig * first_new)) if first_orig > 0 else 0
            )
        elif T >= last_orig:
            new_t = last_new + int(round((T - last_orig) * tail_ratio))
        else:
            # bisect_right - 1 gives the index of the largest anchor whose
            # orig_t is <= T; the frame lives in segment [j, j+1].
            j = bisect.bisect_right(anchor_orig_ts, T) - 1
            j = max(0, min(j, len(anchor_orig_ts) - 2))
            seg_o = anchor_orig_ts[j + 1] - anchor_orig_ts[j]
            seg_n = anchor_new_ts[j + 1] - anchor_new_ts[j]
            frac = (T - anchor_orig_ts[j]) / seg_o if seg_o > 0 else 0.0
            new_t = anchor_new_ts[j] + int(round(frac * seg_n))
        out.append({**f, "t": new_t})
    return out


def compact(path: Path, target_seconds: int | None, seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    submits = data.get("submits") or []
    events = data.get("events") or []
    frames = (data.get("browser") or {}).get("frames") or []

    # Stage 1 — compact the chat trajectory (submits + events) on its
    # own clock. This is the visible "tool calling" pace.
    new_submits, new_events, anchor_orig_ts, anchor_new_ts = _build_anchor_timeline(
        submits, events, rng
    )

    # Stage 2 — interpolate browser frames so they sit at the same
    # fractional position inside their original event window. This is
    # what keeps the noVNC framebuffer in sync with tool calls.
    new_frames = _remap_frames_onto_anchors(
        frames, anchor_orig_ts, anchor_new_ts, rng
    )

    if target_seconds:
        target_ms = target_seconds * 1000
        last_overall = max(
            [int(it.get("t", 0)) for it in new_submits]
            + [int(it.get("t", 0)) for it in new_events]
            + [int(it.get("t", 0)) for it in new_frames]
            + [0]
        )
        new_submits = _scale_to_target(new_submits, target_ms, last_overall)
        new_events = _scale_to_target(new_events, target_ms, last_overall)
        new_frames = _scale_to_target(new_frames, target_ms, last_overall)

    data["submits"] = new_submits
    data["events"] = new_events
    if "browser" in data and isinstance(data["browser"], dict):
        data["browser"]["frames"] = new_frames

    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path, help="Path to the recording JSON.")
    ap.add_argument(
        "--target-seconds",
        type=int,
        default=None,
        help=(
            "Optional. Linearly scale the compacted timeline so the final "
            "event lands at this time (in seconds). Useful if you want a "
            "deterministic total duration."
        ),
    )
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print stats only; don't overwrite the file.",
    )
    args = ap.parse_args()

    data = compact(args.path, args.target_seconds, args.seed)

    events = data.get("events") or []
    submits = data.get("submits") or []
    frames = (data.get("browser") or {}).get("frames") or []
    last_t = max(
        [int(e.get("t", 0)) for e in events]
        + [int(s.get("t", 0)) for s in submits]
        + [int(f.get("t", 0)) for f in frames]
        + [0]
    )
    print(
        f"compacted {args.path}: events={len(events)} submits={len(submits)} "
        f"frames={len(frames)} duration={last_t/1000:.1f}s"
    )

    if args.dry_run:
        return 0
    with open(args.path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    print(f"wrote {args.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
