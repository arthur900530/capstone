import { useMemo, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Loader2,
  Sparkles,
  Target,
  TrendingUp,
  ListChecks,
} from "lucide-react";
import { backfillRecentAnnotations } from "../../services/api";

/* Bucketize a leaf achievement rate into one of four color tiers.
   The "fully achieved" tier is reserved for a strict 100% — that way a
   top-level goal the LLM flagged "success" but that has one failed
   sub-step falls out of dark-green into light-green and stops hiding it. */
function rateBucket(rate, { unknownTotal, total }) {
  if (!total || total === 0) return "empty";
  // If we truly have no signal on any step, render as unknown (gray).
  if (unknownTotal >= total) return "unknown";
  if (rate >= 1) return "all";
  if (rate >= 0.75) return "mostly";
  if (rate >= 0.5) return "partial";
  return "not";
}

const BUCKET_STYLES = {
  all: {
    bar: "bg-[#639922]",
    solid: "bg-[#639922]",
    swatch: "bg-[#639922]",
    badge: "bg-[#639922]/15 text-[#97C459]",
    text: "text-[#97C459]",
    label: "achieved",
  },
  mostly: {
    bar: "bg-[#97C459]",
    solid: "bg-[#97C459]",
    swatch: "bg-[#97C459]",
    badge: "bg-[#97C459]/15 text-[#97C459]",
    text: "text-[#97C459]",
    label: "mostly achieved",
  },
  partial: {
    bar: "bg-[#EF9F27]",
    solid: "bg-[#EF9F27]",
    swatch: "bg-[#EF9F27]",
    badge: "bg-[#EF9F27]/15 text-[#EF9F27]",
    text: "text-[#EF9F27]",
    label: "partially achieved",
  },
  not: {
    bar: "bg-[#E24B4A]",
    solid: "bg-[#E24B4A]",
    swatch: "bg-[#E24B4A]",
    badge: "bg-[#E24B4A]/15 text-[#E24B4A]",
    text: "text-[#E24B4A]",
    label: "not achieved",
  },
  unknown: {
    bar: "bg-zinc-600",
    solid: "bg-zinc-600",
    swatch: "bg-zinc-600",
    badge: "bg-zinc-500/15 text-zinc-300",
    text: "text-zinc-400",
    label: "not scored",
  },
  empty: {
    bar: "bg-zinc-700/60",
    solid: "bg-zinc-700/60",
    swatch: "bg-zinc-700/60",
    badge: "bg-zinc-700/40 text-text-muted",
    text: "text-text-muted",
    label: "empty",
  },
};

/* Depth-weighted aggregated score.

   For a subtree rooted at depth 0, each node at depth d contributes with
   weight w_d = 0.5^(d+1), so the top level carries 0.5, the second 0.25,
   the third 0.125, and so on. Per level we take the mean of binary
   statuses (success = 1, failure = 0, unknown = skipped), and the final
   score is Σ(w_d · mean_d) / Σ(w_d over levels with signal). Normalising
   by the observed-weight sum keeps the result in [0,1] regardless of how
   deep the tree goes or whether any level is fully "unknown".

   Skipping unknowns (rather than treating them as 0 or 0.5) preserves the
   "honest about what we know" principle: an unannotated leaf pulls no
   weight instead of dragging the color down. */

function statusBit(status) {
  if (status === "success") return 1;
  if (status === "failure") return 0;
  return null; // unknown / undefined — skipped
}

/* Prepend ancestor LLM-verdict bits onto ``levels`` and return the depth
   offset at which the goal itself should enter. The backend attaches a
   ``goal.ancestor_statuses`` chain (root → … → parent) so a session the
   LLM flagged "failure" at the top can't paint a green bar just because
   the immediate goal succeeded. Unknown ancestors still advance the
   offset so deeper layers stay at the right weight. */
function _seedAncestors(levels, ancestorStatuses) {
  const chain = ancestorStatuses || [];
  let offset = 0;
  for (let d = 0; d < chain.length; d += 1) {
    const bit = statusBit(chain[d]);
    if (bit !== null) {
      if (!levels[d]) levels[d] = [];
      levels[d].push(bit);
    }
    offset = d + 1;
  }
  return offset;
}

function _collectLevels(goal, levels, depth) {
  const bit = statusBit(goal?.status);
  if (bit !== null) {
    if (!levels[depth]) levels[depth] = [];
    levels[depth].push(bit);
  }

  const subs = goal?.subgoals || [];
  if (subs.length > 0) {
    for (const sg of subs) _collectLevels(sg, levels, depth + 1);
    return;
  }

  // Leaf goal — its action steps live one level deeper than the goal.
  const steps = goal?.leaf_steps || [];
  for (const step of steps) {
    const sv = statusBit(step?.status);
    if (sv !== null) {
      const d = depth + 1;
      if (!levels[d]) levels[d] = [];
      levels[d].push(sv);
    }
  }
}

function _scoreFromLevels(levels) {
  const depths = Object.keys(levels).map(Number).sort((a, b) => a - b);
  let num = 0;
  let den = 0;
  for (const d of depths) {
    const arr = levels[d];
    if (!arr || arr.length === 0) continue;
    const w = Math.pow(0.5, d + 1);
    const mean = arr.reduce((s, x) => s + x, 0) / arr.length;
    num += w * mean;
    den += w;
  }
  return den > 0 ? num / den : null;
}

function aggregatedGoalScore(goal) {
  // Prefer the backend-computed ``weighted_rate`` so the segment color,
  // the headline %, and the KPI tile all derive from the same numbers
  // the server persists alongside the LLM annotations. Falling back to
  // the local recomputation keeps old payloads rendering without a
  // deploy-window "—".
  if (goal && typeof goal.weighted_rate === "number") return goal.weighted_rate;
  const levels = {};
  const offset = _seedAncestors(levels, goal?.ancestor_statuses);
  _collectLevels(goal, levels, offset);
  return _scoreFromLevels(levels);
}

/* Task-level score: aggregated mean of level averages across the whole
   task. Top-level goals enter at depth 0 so they carry weight 0.5, their
   sub-goals at 0.25, leaf steps at 0.125, and so on — matching the
   "overall success rate = 0.5·L1_avg + 0.25·L2_avg + …" spec.

   Prefers the backend-computed ``task_score`` (shared with the employee
   aggregate KPI) so the headline %, tooltip and aggregate tile can't
   drift out of sync; falls back to the in-page recomputation when the
   field is absent (older payloads). */
function aggregatedTaskScore(run) {
  if (run && typeof run.task_score === "number") return run.task_score;
  const goals = run?.top_level_goals || [];
  if (goals.length === 0) return null;
  // Best-effort fallback: seed the shared ancestor prefix from the first
  // top-level goal so the root/trial LLM verdicts aren't dropped when the
  // payload predates ``task_score``.
  const levels = {};
  const offset = _seedAncestors(levels, goals[0]?.ancestor_statuses);
  for (const g of goals) _collectLevels(g, levels, offset);
  return _scoreFromLevels(levels);
}

function scoreBucket(score) {
  if (score == null) return "unknown";
  if (score >= 1.0) return "all";
  if (score >= 0.75) return "mostly";
  if (score >= 0.5) return "partial";
  return "not";
}

function goalBucket(goal) {
  // No status signal anywhere in the subtree and no leaf steps → "empty"
  // (muted gray) so unrendered tasks don't get a wrong-looking green bar.
  const score = aggregatedGoalScore(goal);
  if (score == null && (goal?.leaf_total ?? 0) === 0) return "empty";
  return scoreBucket(score);
}

function taskBucket(run) {
  return scoreBucket(aggregatedTaskScore(run));
}

function BarTooltip({ goal }) {
  const bucket = goalBucket(goal);
  const style = BUCKET_STYLES[bucket];
  const score = aggregatedGoalScore(goal);
  const scorePct = score == null ? null : Math.round(score * 100);
  const leafPct = Math.round((goal.leaf_rate || 0) * 100);
  return (
    <div className="pointer-events-none w-56 space-y-1.5">
      <div className="flex items-start gap-1.5">
        <span className={`mt-0.5 h-2 w-2 shrink-0 rounded-sm ${style.swatch}`} />
        <span className="text-[12px] font-medium leading-snug text-text-primary">
          {goal.goal || "Sub-goal"}
        </span>
      </div>
      <div className="flex items-center justify-between gap-2 text-[11px]">
        <span
          className="text-text-muted"
          title="Depth-weighted score: 0.5·top + 0.25·L2 + 0.125·L3 + …"
        >
          weighted score
        </span>
        <span className={`font-semibold tabular-nums ${style.text}`}>
          {scorePct == null ? "—" : `${scorePct}%`}
        </span>
      </div>
      <div className="flex items-center justify-between gap-2 text-[11px]">
        <span className="text-text-muted">
          {goal.leaf_achieved}/{goal.leaf_total} leaf steps
        </span>
        <span className="font-medium tabular-nums text-text-secondary">
          {leafPct}%
        </span>
      </div>
      <div className="flex items-center justify-between gap-2">
        <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${style.badge}`}>
          {style.label}
        </span>
        {goal.subgoals && goal.subgoals.length > 0 ? (
          <span className="text-[10px] text-text-muted">
            {goal.subgoals.length} sub-goal{goal.subgoals.length !== 1 ? "s" : ""}
          </span>
        ) : null}
      </div>
      {goal.status_reason ? (
        <p className="border-t border-border/40 pt-1 text-[10px] italic leading-snug text-text-muted">
          {goal.status_reason}
        </p>
      ) : null}
    </div>
  );
}

function GoalBar({ goals }) {
  const [hoveredIdx, setHoveredIdx] = useState(null);

  if (!goals.length) {
    return <div className="h-3 w-full rounded bg-zinc-700/40" />;
  }

  const totalUnits = goals.reduce(
    (s, g) => s + Math.max(1, g.leaf_total || 1),
    0,
  );

  let cum = 0;
  const segments = goals.map((goal, i) => {
    const units = Math.max(1, goal.leaf_total || 1);
    const widthPct = (units / totalUnits) * 100;
    const leftPct = cum;
    cum += widthPct;
    return { goal, i, widthPct, leftPct };
  });

  const hovered = hoveredIdx != null ? segments[hoveredIdx] : null;

  return (
    <div
      className="relative"
      onMouseLeave={() => setHoveredIdx(null)}
    >
      <div className="flex h-3 w-full overflow-hidden rounded border border-border/40">
        {segments.map(({ goal, i, widthPct }) => {
          const bucket = goalBucket(goal);
          const style = BUCKET_STYLES[bucket];
          const isHovered = hoveredIdx === i;
          const dim = hoveredIdx != null && !isHovered;
          return (
            <div
              key={`${goal.path}-${i}`}
              role="button"
              tabIndex={0}
              aria-label={`${goal.goal}, ${Math.round((goal.leaf_rate || 0) * 100)}%`}
              onMouseEnter={() => setHoveredIdx(i)}
              onFocus={() => setHoveredIdx(i)}
              onBlur={() => setHoveredIdx((prev) => (prev === i ? null : prev))}
              className={`h-full cursor-pointer transition-[filter,opacity] duration-150 ${style.bar} ${
                i > 0 ? "border-l border-[#2a2c31]" : ""
              } ${isHovered ? "brightness-125" : dim ? "opacity-60" : ""}`}
              style={{ width: `${widthPct}%` }}
            />
          );
        })}
      </div>

      {/* Floating tooltip anchored to the hovered segment's center. */}
      {hovered ? (
        <div
          className="pointer-events-none absolute bottom-full z-20 mb-2 -translate-x-1/2 rounded-md border border-border/70 bg-[#1a1c1f] px-2.5 py-1.5 shadow-[0_6px_24px_rgba(0,0,0,0.45)]"
          style={{ left: `${hovered.leftPct + hovered.widthPct / 2}%` }}
        >
          <BarTooltip goal={hovered.goal} />
          <span
            className="absolute left-1/2 top-full -translate-x-1/2 border-x-4 border-t-4 border-x-transparent border-t-[#1a1c1f]"
            aria-hidden
          />
        </div>
      ) : null}
    </div>
  );
}

function StatusBadge({ goal, compact = false }) {
  const bucket = goalBucket(goal);
  const style = BUCKET_STYLES[bucket];
  const score = aggregatedGoalScore(goal);
  const pct =
    score != null
      ? Math.round(score * 100)
      : Math.round((goal?.leaf_rate || 0) * 100);
  return (
    <span
      className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium ${style.badge}`}
    >
      {compact ? style.label : `${pct}% · ${style.label}`}
    </span>
  );
}

function LeafStep({ step }) {
  const status = step.status;
  const dot =
    status === "success"
      ? "bg-[#639922]"
      : status === "failure"
        ? "bg-[#E24B4A]"
        : "bg-zinc-500";
  return (
    <li className="flex items-center gap-2 py-0.5 text-[12px] text-text-secondary">
      <span className={`h-1.5 w-1.5 shrink-0 rounded-sm ${dot}`} />
      <span className="min-w-0 flex-1 truncate" title={step.action}>
        {step.action}
      </span>
      <span
        className={`shrink-0 text-[10px] uppercase tracking-wide ${
          status === "success"
            ? "text-[#97C459]"
            : status === "failure"
              ? "text-[#E24B4A]"
              : "text-text-muted"
        }`}
      >
        {status === "success"
          ? "ok"
          : status === "failure"
            ? "fail"
            : "—"}
      </span>
    </li>
  );
}

function GoalBreakdown({ goal, level = 0 }) {
  const bucket = goalBucket(goal);
  const style = BUCKET_STYLES[bucket];
  const hasSub = goal.subgoals && goal.subgoals.length > 0;
  const score = aggregatedGoalScore(goal);
  const pct =
    score != null
      ? Math.round(score * 100)
      : Math.round((goal.leaf_rate || 0) * 100);

  return (
    <div
      className="rounded-md border border-border/30 bg-surface/40 p-2"
      style={{ marginLeft: level * 14 }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <span className={`h-2 w-2 shrink-0 rounded-sm ${style.swatch}`} />
          <span
            className={`truncate text-[13px] ${
              level === 0 ? "font-medium text-text-primary" : "text-text-secondary"
            }`}
            title={goal.goal}
          >
            {goal.goal || "Sub-goal"}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className={`text-[12px] font-semibold tabular-nums ${style.text}`}>
            {pct}%
          </span>
          <StatusBadge goal={goal} compact />
        </div>
      </div>

      {goal.status_reason ? (
        <p className="mt-1 text-[11px] italic text-text-muted">
          {goal.status_reason}
        </p>
      ) : null}

      {hasSub ? (
        <div className="mt-2 space-y-1.5">
          {goal.subgoals.map((sg) => (
            <GoalBreakdown key={sg.path} goal={sg} level={level + 1} />
          ))}
        </div>
      ) : null}

      {!hasSub && goal.leaf_steps && goal.leaf_steps.length > 0 ? (
        <ul className="mt-1.5 space-y-0.5 pl-3.5">
          {goal.leaf_steps.map((s) => (
            <LeafStep key={s.path} step={s} />
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function TaskRow({ index, run, expanded, onToggle, onOpenTrajectory }) {
  const goals = run.top_level_goals || [];
  const leaf = run.leaf_summary || { total: 0, achieved: 0, rate: 0 };
  // The headline % is the depth-weighted aggregated score so the number
  // and the bar color always tell the same story. A 100%-leaf trace with
  // an LLM "failure" at the top will correctly read ~33% in red instead
  // of 100% in red. Raw leaf rate is still available in the tooltip and
  // the expanded breakdown.
  const score = aggregatedTaskScore(run);
  const bucket = taskBucket(run);
  const hasSignal = score != null || (leaf.total || 0) > 0;
  const pct =
    score != null ? Math.round(score * 100) : Math.round((leaf.rate || 0) * 100);
  const pctColor = hasSignal
    ? BUCKET_STYLES[bucket]?.text || "text-text-primary"
    : "text-text-muted";

  const title =
    run.prompt_preview?.trim() ||
    "(empty prompt)";

  return (
    <li className="group rounded-lg border border-border/40 bg-surface/40 p-3 transition-colors hover:border-accent-teal/30 hover:bg-surface/60">
      <div className="flex items-start gap-2">
        <button
          type="button"
          onClick={onToggle}
          className="mt-0.5 shrink-0 rounded p-0.5 text-text-muted hover:bg-border/40 hover:text-text-primary"
          aria-label={expanded ? "Collapse task details" : "Expand task details"}
        >
          {expanded ? (
            <ChevronDown size={14} />
          ) : (
            <ChevronRight size={14} />
          )}
        </button>
        <span className="mt-0.5 w-4 shrink-0 text-right text-[11px] tabular-nums text-text-muted">
          {index + 1}
        </span>
        <button
          type="button"
          onClick={onOpenTrajectory}
          className="min-w-0 flex-1 truncate text-left text-[13px] text-text-primary hover:underline"
          title={title}
        >
          {title}
        </button>
        <span
          className={`shrink-0 text-[13px] font-semibold tabular-nums ${pctColor}`}
        >
          {hasSignal ? `${pct}%` : "—"}
        </span>
      </div>

      <div className="mt-2 pl-10">
        <GoalBar goals={goals} />
        {!hasSignal && !run.annotated ? (
          <p className="mt-1 text-[11px] italic text-text-muted">
            Not yet annotated — run the LLM to score this task.
          </p>
        ) : null}
      </div>

      {expanded ? (
        <div className="mt-3 space-y-2 border-t border-border/30 pt-3">
          {goals.length === 0 ? (
            <p className="text-[12px] text-text-muted">No goals extracted.</p>
          ) : (
            goals.map((g) => <GoalBreakdown key={g.path} goal={g} />)
          )}
        </div>
      ) : null}
    </li>
  );
}

/* ── Goal-achievement trend (inline SVG sparkline) ───────────────────────── */

const BUCKET_HEX = {
  all: "#639922",      // dark green — achieved
  mostly: "#97C459",   // light green — mostly achieved
  partial: "#EF9F27",  // amber — partially achieved
  not: "#E24B4A",      // red — not achieved
  unknown: "#52525b",  // zinc-600
  empty: "#3f3f46",    // zinc-700
};

function TrendChart({ tasks, onPointClick }) {
  // `tasks` is newest-first; flip to chronological (T1 = oldest → Tn = newest).
  const ordered = useMemo(() => [...tasks].reverse(), [tasks]);
  const [hoveredIdx, setHoveredIdx] = useState(null);

  // viewBox coords. We render responsively via width="100%".
  const W = 1000;
  const H = 160;
  const padL = 44;
  const padR = 20;
  const padT = 16;
  const padB = 28;
  const chartW = W - padL - padR;
  const chartH = H - padT - padB;

  if (ordered.length === 0) return null;

  const n = ordered.length;
  const xFor = (i) =>
    n === 1 ? padL + chartW / 2 : padL + (chartW * i) / (n - 1);
  const yFor = (rate) =>
    padT + chartH * (1 - Math.max(0, Math.min(1, rate)));

  const points = ordered.map((task, i) => {
    const rate = task.leaf_summary?.rate ?? 0;
    const hasData = (task.leaf_summary?.total ?? 0) > 0;
    // Y-position and color both track the depth-weighted aggregated
    // score so an LLM "failure" at the top level visibly drags the trend
    // line down even when every leaf step passed. Falls back to raw leaf
    // rate if there's no annotation signal at all.
    const bucket = taskBucket(task);
    const score = aggregatedTaskScore(task);
    const yValue = score != null ? score : hasData ? rate : 0;
    return {
      i,
      task,
      rate,
      hasData,
      bucket,
      score,
      x: xFor(i),
      y: yFor(yValue),
      label: `T${i + 1}`,
    };
  });

  const linePath = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`)
    .join(" ");

  // Space labels out if there are many points; every-other label above ~10.
  const labelStride = n > 10 ? 2 : 1;
  const hovered = hoveredIdx != null ? points[hoveredIdx] : null;

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        className="h-[160px] w-full"
      >
        {/* Horizontal gridlines at 0 / 50 / 100% */}
        {[0, 0.5, 1].map((v) => (
          <g key={v}>
            <line
              x1={padL}
              x2={W - padR}
              y1={yFor(v)}
              y2={yFor(v)}
              stroke="#3f3f46"
              strokeDasharray="3,4"
              strokeWidth="1"
            />
            <text
              x={padL - 8}
              y={yFor(v) + 3}
              textAnchor="end"
              fontSize="11"
              fill="#8b8f96"
            >
              {Math.round(v * 100)}%
            </text>
          </g>
        ))}

        {/* Line connecting the points (drawn before dots so dots overlay). */}
        <path
          d={linePath}
          fill="none"
          stroke="#60a5fa"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Points + x-axis labels + invisible hit targets */}
        {points.map((p) => (
          <g key={p.i}>
            <circle
              cx={p.x}
              cy={p.y}
              r={hoveredIdx === p.i ? 7.5 : 6}
              fill={p.hasData ? BUCKET_HEX[p.bucket] : "#2a2c31"}
              stroke={p.hasData ? "#1a1c1f" : BUCKET_HEX.unknown}
              strokeWidth="2"
              style={{ transition: "r 120ms" }}
            />
            {p.i % labelStride === 0 ? (
              <text
                x={p.x}
                y={H - 8}
                textAnchor="middle"
                fontSize="11"
                fill="#8b8f96"
              >
                {p.label}
              </text>
            ) : null}
            {/* Hit target: wider than the dot so hover/click feels generous. */}
            <rect
              x={p.x - 18}
              y={padT - 4}
              width={36}
              height={chartH + 10}
              fill="transparent"
              onMouseEnter={() => setHoveredIdx(p.i)}
              onMouseLeave={() => setHoveredIdx(null)}
              onClick={() => onPointClick?.(p.task)}
              style={{ cursor: onPointClick ? "pointer" : "default" }}
            >
              <title>
                {`${p.label} — ${
                  p.score != null
                    ? `${Math.round(p.score * 100)}% weighted`
                    : p.hasData
                      ? `${Math.round(p.rate * 100)}% leaf rate`
                      : "not scored"
                }`}
              </title>
            </rect>
          </g>
        ))}
      </svg>

      {/* Hover card */}
      {hovered ? (
        <TrendHoverCard point={hovered} chartWidth={W} padL={padL} padR={padR} />
      ) : null}
    </div>
  );
}

function TrendHoverCard({ point, chartWidth, padL, padR }) {
  const leftFrac = point.x / chartWidth;
  const clampedLeftFrac = Math.max(padL / chartWidth, Math.min(1 - padR / chartWidth, leftFrac));
  const title =
    point.task.prompt_preview?.trim() || "(empty prompt)";
  const bucketStyle = BUCKET_STYLES[point.bucket] || BUCKET_STYLES.unknown;
  return (
    <div
      className="pointer-events-none absolute top-2 z-20 -translate-x-1/2 rounded-md border border-border/70 bg-[#1a1c1f] px-2.5 py-1.5 text-[11px] shadow-[0_6px_24px_rgba(0,0,0,0.45)]"
      style={{ left: `${clampedLeftFrac * 100}%` }}
    >
      <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
        {point.label}
      </div>
      <div className="mb-1 max-w-[220px] truncate text-[12px] font-medium text-text-primary">
        {title}
      </div>
      <div className="flex items-center gap-2">
        <span className={`h-2 w-2 rounded-sm ${bucketStyle.swatch}`} />
        <span className={`font-semibold tabular-nums ${bucketStyle.text}`}>
          {point.score != null
            ? `${Math.round(point.score * 100)}%`
            : point.hasData
              ? `${Math.round(point.rate * 100)}%`
              : "not scored"}
        </span>
        <span
          className="text-[10px] uppercase tracking-wider text-text-muted"
          title="Depth-weighted score: 0.5·top + 0.25·L2 + 0.125·L3 + …"
        >
          weighted
        </span>
      </div>
      {point.task.leaf_summary?.total ? (
        <div className="mt-0.5 flex items-center gap-1 text-[10px] text-text-muted">
          <span>
            {point.task.leaf_summary.achieved}/{point.task.leaf_summary.total} leaf steps
          </span>
          <span className="text-text-muted">
            · {Math.round((point.task.leaf_summary.rate || 0) * 100)}%
          </span>
        </div>
      ) : null}
    </div>
  );
}

function Kpi({ icon: Icon, label, value, sub, accent }) {
  return (
    <div className="rounded-lg border border-border/60 bg-[#2a2c31] p-4 shadow-[0_2px_12px_rgba(0,0,0,0.25)]">
      <div className="flex items-center gap-2">
        <Icon size={14} className="text-accent-teal" />
        <p className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">
          {label}
        </p>
      </div>
      <p
        className={`mt-1.5 text-2xl font-semibold tabular-nums ${
          accent ?? "text-text-primary"
        }`}
      >
        {value}
      </p>
      {sub ? (
        <p className="mt-0.5 text-[11px] text-text-muted">{sub}</p>
      ) : null}
    </div>
  );
}

function Legend() {
  const tiers = [
    ["all", "all achieved"],
    ["mostly", "mostly achieved"],
    ["partial", "partially achieved"],
    ["not", "not achieved"],
  ];
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-text-muted">
      {tiers.map(([k, label]) => (
        <span key={k} className="flex items-center gap-1.5">
          <span className={`h-2 w-2 rounded-sm ${BUCKET_STYLES[k].swatch}`} />
          {label}
        </span>
      ))}
      <span className="ml-auto text-[11px] text-text-muted">
        width = subtree size · click to expand
      </span>
    </div>
  );
}

function accentForRate(rate) {
  if (rate == null) return "text-text-primary";
  if (rate >= 1) return "text-[#639922]";
  if (rate >= 0.75) return "text-[#97C459]";
  if (rate >= 0.5) return "text-[#EF9F27]";
  return "text-[#E24B4A]";
}

export default function TaskPerformanceSection({
  employeeId,
  aggregate,
  recent = [],
  onOpenTrajectory,
  onRefresh,
}) {
  const [expanded, setExpanded] = useState(() => new Set());
  const [backfilling, setBackfilling] = useState(false);
  const [backfillError, setBackfillError] = useState(null);

  const unannotated = aggregate?.unannotated_tasks ?? 0;
  const annotated = aggregate?.annotated_tasks ?? 0;

  // The headline KPI uses the depth-weighted aggregated mean (0.5·L1_avg
  // + 0.25·L2_avg + …) so it honours the spec. ``avg_task_score`` is
  // provided by the backend; falling back to ``avg_leaf_rate`` keeps old
  // payloads from rendering "—" during a deploy window.
  const weightedRate =
    typeof aggregate?.avg_task_score === "number"
      ? aggregate.avg_task_score
      : aggregate?.avg_leaf_rate;
  const leafPct = Math.round((weightedRate || 0) * 100);
  const leafAccent = accentForRate(weightedRate);

  const leafTotals = useMemo(
    () => ({
      total: aggregate?.total_leaf_steps ?? 0,
      achieved: aggregate?.total_leaf_achieved ?? 0,
    }),
    [aggregate?.total_leaf_steps, aggregate?.total_leaf_achieved],
  );
  const leafMicroPct =
    leafTotals.total > 0
      ? Math.round((leafTotals.achieved / leafTotals.total) * 100)
      : 0;

  // Task-level "fully achieved" — a task counts iff every depth of the
  // weighted score was success (``task_score === 1``), and the
  // denominator is annotated tasks. The per-goal counts the old field
  // exposed double-credited sessions with multiple surfaced sub-goals
  // and let a root-level "failure" annotation slip through unseen.
  const annotatedTasks = aggregate?.annotated_tasks ?? 0;
  const tasksFullyAchieved = aggregate?.tasks_fully_achieved ?? 0;

  async function handleBackfill() {
    if (backfilling) return;
    setBackfilling(true);
    setBackfillError(null);
    try {
      await backfillRecentAnnotations(employeeId, { limit: Math.max(recent.length, 10) });
      if (onRefresh) await onRefresh();
    } catch (err) {
      setBackfillError(err?.message || "Backfill failed");
    } finally {
      setBackfilling(false);
    }
  }

  function toggle(key) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <div className="space-y-4">
      {/* Goal-oriented KPI tiles */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Kpi
          icon={TrendingUp}
          label="Avg success rate"
          value={annotatedTasks > 0 ? `${leafPct}%` : "—"}
          sub="depth-weighted mean (0.5·L1 + 0.25·L2 + …)"
          accent={annotatedTasks > 0 ? leafAccent : undefined}
        />
        <Kpi
          icon={Target}
          label="Tasks achieved"
          value={
            annotatedTasks > 0 ? (
              <>
                <span>{tasksFullyAchieved}</span>
                <span className="text-lg font-normal text-text-muted">
                  {" / "}
                  {annotatedTasks}
                </span>
              </>
            ) : (
              "—"
            )
          }
          sub="LLM top-level verdict = success"
        />
        <Kpi
          icon={ListChecks}
          label="Leaf steps"
          value={
            leafTotals.total > 0 ? (
              <>
                <span>{leafTotals.achieved}</span>
                <span className="text-lg font-normal text-text-muted">
                  {" / "}
                  {leafTotals.total}
                </span>
              </>
            ) : (
              "—"
            )
          }
          sub={
            leafTotals.total > 0
              ? `${leafMicroPct}% succeeded overall`
              : "run annotation to populate"
          }
        />
      </div>

      {/* Backfill prompt when we have un-annotated tasks */}
      {unannotated > 0 ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-[12px]">
          <div className="flex items-center gap-2 text-amber-200">
            <Sparkles size={14} />
            <span>
              {unannotated} task{unannotated !== 1 ? "s" : ""} not yet scored by the LLM.{" "}
              {annotated > 0 ? `${annotated} already annotated.` : null}
            </span>
          </div>
          <div className="flex items-center gap-2">
            {backfillError ? (
              <span className="text-red-300">{backfillError}</span>
            ) : null}
            <button
              type="button"
              onClick={handleBackfill}
              disabled={backfilling}
              className="inline-flex items-center gap-1.5 rounded border border-amber-400/40 bg-amber-400/10 px-2 py-1 text-[11px] font-medium text-amber-100 hover:bg-amber-400/20 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {backfilling ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <Sparkles size={12} />
              )}
              {backfilling ? "Annotating…" : "Annotate recent"}
            </button>
          </div>
        </div>
      ) : null}

      {/* Goal achievement trend (T1 = oldest → Tn = newest) */}
      {recent.length > 0 ? (
        <div className="rounded-lg border border-border/60 bg-[#2a2c31] p-4 shadow-[0_2px_12px_rgba(0,0,0,0.25)]">
          <div className="mb-1 flex items-center gap-2">
            <TrendingUp size={14} className="text-accent-teal" />
            <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
              Goal achievement trend
            </h3>
          </div>
          <p className="mb-1 text-[11px] text-text-muted">
            Leaf-step achievement across the most recent {recent.length} task
            {recent.length !== 1 ? "s" : ""} · dots colored by bucket · hover for details
            {onOpenTrajectory ? " · click a point to open" : ""}
          </p>
          <TrendChart
            tasks={recent}
            onPointClick={
              onOpenTrajectory
                ? (task) =>
                    onOpenTrajectory({
                      sessionId: task.session_id,
                      taskIndex: task.task_index,
                      run: task,
                    })
                : undefined
            }
          />
        </div>
      ) : null}

      {/* Task performance list */}
      <div>
        <div className="mb-2 flex items-center gap-2">
          <Target size={15} className="text-accent-teal" />
          <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
            Task performance
          </h3>
          <span className="rounded-full bg-surface px-1.5 py-0.5 text-[10px] text-text-muted">
            {recent.length}
          </span>
        </div>
        <div className="mb-2">
          <Legend />
        </div>
        {recent.length === 0 ? (
          <p className="rounded-lg border border-border/40 bg-surface/40 p-4 text-center text-xs text-text-muted">
            No recent tasks recorded.
          </p>
        ) : (
          <ul className="space-y-2">
            {recent.map((run, i) => {
              const key = `${run.session_id}-${run.task_index}`;
              return (
                <TaskRow
                  key={key}
                  index={i}
                  run={run}
                  expanded={expanded.has(key)}
                  onToggle={() => toggle(key)}
                  onOpenTrajectory={() =>
                    onOpenTrajectory?.({
                      sessionId: run.session_id,
                      taskIndex: run.task_index,
                      run,
                    })
                  }
                />
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
