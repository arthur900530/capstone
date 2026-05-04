import { createElement, useEffect, useMemo, useState } from "react";
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  GitCompareArrows,
  Loader2,
  Sparkles,
  Target,
  TrendingUp,
  ListChecks,
} from "lucide-react";
import { backfillRecentAnnotations } from "../../services/api";
import {
  alignmentForPath,
  formatRate,
  leafPaths,
  subtreeCompletion,
} from "../workflow/workflowScore";

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

   Prefers the backend-computed ``effective_task_score`` so workflow
   alignment (when the user has compared this run against a skill
   workflow in the trajectory drawer's Workflow tab) drives the
   headline %, tooltip and aggregate tile. Falls back to ``task_score``
   (the LLM-goal weighted score) and finally to the in-page recomputation
   for older payloads. */
function aggregatedTaskScore(run) {
  if (run && typeof run.effective_task_score === "number") {
    return run.effective_task_score;
  }
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

function workflowBest(run) {
  return run?.workflow_summary?.best || null;
}

function isWorkflowAligned(run) {
  return Boolean(run?.workflow_summary?.aligned);
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

// Workflow-aware bar that replaces ``GoalBar`` for aligned runs.
//
// One segment per TOP-LEVEL workflow step. Width is proportional to the
// number of leaf steps under that subtree so a complex top-level step
// doesn't visually weigh the same as a single-leaf one. Color is the
// score bucket of ``subtreeCompletion(rate)``: a step where every leaf
// satisfied is green, a half-failed step is amber, all-missed is red.
//
// Tooltip surfaces the step title + ``passed/total · rate%`` so the
// underlying alignment numbers are still discoverable on hover.
function WorkflowBar({ workflow, alignment }) {
  const [hoveredIdx, setHoveredIdx] = useState(null);

  const segments = useMemo(() => {
    const roots = workflow?.root_steps || [];
    return roots.map((step, i) => {
      const path = [i];
      const completion = subtreeCompletion(step, path, alignment);
      const leaves = leafPaths([step]);
      // Equal-fallback width keeps a step with zero leaves (degenerate
      // workflow) visible rather than collapsing the segment to 0.
      const units = Math.max(1, leaves.length || 1);
      const bucket =
        completion.total === 0 ? "empty" : scoreBucket(completion.rate);
      return { step, path, completion, units, bucket };
    });
  }, [workflow, alignment]);

  if (!segments.length) {
    return <div className="h-3 w-full rounded bg-zinc-700/40" />;
  }

  const totalUnits = segments.reduce((s, seg) => s + seg.units, 0);

  const laidOut = segments.reduce(
    (acc, seg, i) => {
      const widthPct = (seg.units / totalUnits) * 100;
      const leftPct = acc.total;
      acc.items.push({ ...seg, i, widthPct, leftPct });
      acc.total += widthPct;
      return acc;
    },
    { items: [], total: 0 },
  ).items;

  const hovered = hoveredIdx != null ? laidOut[hoveredIdx] : null;

  return (
    <div className="relative" onMouseLeave={() => setHoveredIdx(null)}>
      <div className="flex h-3 w-full overflow-hidden rounded border border-border/40">
        {laidOut.map((seg) => {
          const style = BUCKET_STYLES[seg.bucket] || BUCKET_STYLES.unknown;
          const isHovered = hoveredIdx === seg.i;
          const dim = hoveredIdx != null && !isHovered;
          return (
            <div
              key={seg.path.join(".")}
              role="button"
              tabIndex={0}
              aria-label={`${seg.step?.title || "Step"}, ${seg.completion.passed}/${seg.completion.total} satisfied`}
              onMouseEnter={() => setHoveredIdx(seg.i)}
              onFocus={() => setHoveredIdx(seg.i)}
              onBlur={() => setHoveredIdx((prev) => (prev === seg.i ? null : prev))}
              className={`h-full cursor-pointer transition-[filter,opacity] duration-150 ${style.bar} ${
                seg.i > 0 ? "border-l border-[#2a2c31]" : ""
              } ${isHovered ? "brightness-125" : dim ? "opacity-60" : ""}`}
              style={{ width: `${seg.widthPct}%` }}
            />
          );
        })}
      </div>
      {hovered ? (
        <div
          className="pointer-events-none absolute bottom-full z-20 mb-2 -translate-x-1/2 rounded-md border border-border/70 bg-[#1a1c1f] px-2.5 py-1.5 shadow-[0_6px_24px_rgba(0,0,0,0.45)]"
          style={{ left: `${hovered.leftPct + hovered.widthPct / 2}%` }}
        >
          <WorkflowBarTooltip segment={hovered} alignment={alignment} />
          <span
            className="absolute left-1/2 top-full -translate-x-1/2 border-x-4 border-t-4 border-x-transparent border-t-[#1a1c1f]"
            aria-hidden
          />
        </div>
      ) : null}
    </div>
  );
}

function WorkflowBarTooltip({ segment, alignment }) {
  const style = BUCKET_STYLES[segment.bucket] || BUCKET_STYLES.unknown;
  const ratePct = formatRate(segment.completion.rate);
  const isLeafSegment =
    !Array.isArray(segment.step?.children) || segment.step.children.length === 0;
  const leafEntry = isLeafSegment
    ? alignmentForPath(alignment, segment.path)
    : null;
  const evidence = leafEntry?.evidence;
  return (
    <div className="pointer-events-none w-56 space-y-1.5">
      <div className="flex items-start gap-1.5">
        <span className={`mt-0.5 h-2 w-2 shrink-0 rounded-sm ${style.swatch}`} />
        <span className="text-[12px] font-medium leading-snug text-text-primary">
          {segment.step?.title || "Step"}
        </span>
      </div>
      <div className="flex items-center justify-between gap-2 text-[11px]">
        <span className="text-text-muted">
          {segment.completion.passed}/{segment.completion.total}
          {isLeafSegment ? " (leaf step)" : " leaf steps"}
        </span>
        <span className={`font-semibold tabular-nums ${style.text}`}>
          {ratePct}
        </span>
      </div>
      <div className="flex items-center justify-between gap-2">
        <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${style.badge}`}>
          {style.label}
        </span>
      </div>
      {evidence ? (
        <p className="border-t border-border/40 pt-1 text-[10px] italic leading-snug text-text-muted">
          {evidence}
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

  const segments = goals.reduce((acc, goal, i) => {
    const units = Math.max(1, goal.leaf_total || 1);
    const widthPct = (units / totalUnits) * 100;
    const leftPct = acc.total;
    acc.items.push({ goal, i, widthPct, leftPct });
    acc.total += widthPct;
    return acc;
  }, { items: [], total: 0 }).items;

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
  // and the bar color always tell the same story — and now prefers the
  // workflow-alignment rate when the user has compared this run against
  // a skill workflow in the trajectory drawer's Workflow tab.
  const score = aggregatedTaskScore(run);
  const bucket = taskBucket(run);
  const hasSignal = score != null || (leaf.total || 0) > 0;
  const pct =
    score != null ? Math.round(score * 100) : Math.round((leaf.rate || 0) * 100);
  const pctColor = hasSignal
    ? BUCKET_STYLES[bucket]?.text || "text-text-primary"
    : "text-text-muted";

  const aligned = isWorkflowAligned(run);
  const wfBest = workflowBest(run);
  const wfPct = wfBest ? Math.round((wfBest.rate || 0) * 100) : null;
  const wfAccent =
    wfBest != null ? BUCKET_STYLES[scoreBucket(wfBest.rate)] : null;
  const isAutotest = run.source === "autotest";
  // Until the LLM annotates a run we have no per-goal verdicts, so the
  // multi-segment GoalBar would just render a row of muted greys with
  // confusing dividers. Collapse to a single grey bar and pin the
  // headline % to 0 so unannotated tasks read as "no signal · 0%"
  // instead of "—". Once ``run.annotated`` flips true the rest of the
  // row falls back to the normal score-driven rendering.
  const isUnannotated = !run.annotated;

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
        {isAutotest ? (
          <span
            className="mt-0.5 shrink-0 rounded bg-yellow-500/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-yellow-400"
            title="Mirrored from an autotest run"
          >
            Autotest
          </span>
        ) : null}
        <button
          type="button"
          onClick={onOpenTrajectory}
          className="min-w-0 flex-1 truncate text-left text-[13px] text-text-primary hover:underline"
          title={title}
        >
          {title}
        </button>
        {aligned && wfBest ? (
          <span
            className={`inline-flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium ${
              wfAccent?.badge || "bg-surface text-text-muted"
            }`}
            title={`Workflow alignment vs. ${wfBest.skill_slug || wfBest.skill_id}: ${wfBest.passed}/${wfBest.total} steps`}
          >
            <GitCompareArrows size={10} />
            workflow {wfPct}%
          </span>
        ) : null}
        <span
          className={`shrink-0 text-[13px] font-semibold tabular-nums ${
            isUnannotated ? "text-text-muted" : pctColor
          }`}
          title={isUnannotated ? "Not yet annotated — score defaults to 0%" : undefined}
        >
          {isUnannotated ? "0%" : hasSignal ? `${pct}%` : "0%"}
        </span>
      </div>

      <div className="mt-2 pl-10">
        {isUnannotated ? (
          // Single muted bar so an unscored run reads as "empty" at a
          // glance instead of a row of GoalBar segments that all happen
          // to fall into the empty bucket.
          <div
            className="h-3 w-full rounded border border-border/40 bg-zinc-700/60"
            role="img"
            aria-label="Not yet annotated"
            title="Not yet annotated — run the LLM to score this task"
          />
        ) : aligned && wfBest?.workflow ? (
          // For workflow-aligned runs the bar reflects the chosen
          // skill's workflow steps and the LLM's per-leaf alignment so
          // the visual matches the score the user just saw in the
          // drawer's Workflow tab.
          <WorkflowBar
            workflow={wfBest.workflow}
            alignment={wfBest.workflow_alignment}
          />
        ) : (
          <GoalBar goals={goals} />
        )}
        {isUnannotated ? (
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

function defaultTrendMetric(task) {
  // Default per-task metric: depth-weighted aggregated score so an LLM
  // "failure" at the top level visibly drags the trend line down even
  // when every leaf step passed. Falls back to the raw leaf rate when
  // there's no annotation signal yet.
  const rate = task.leaf_summary?.rate ?? 0;
  const hasData = (task.leaf_summary?.total ?? 0) > 0;
  const bucket = taskBucket(task);
  const score = aggregatedTaskScore(task);
  return { rate, hasData, bucket, score };
}

function TrendChart({ tasks, onPointClick, getMetric, hoverContextLabel }) {
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

  const metricFn = getMetric || defaultTrendMetric;
  const points = ordered.map((task, i) => {
    const m = metricFn(task) || {};
    const rate = m.rate ?? 0;
    const hasData = Boolean(m.hasData);
    const bucket = m.bucket || "unknown";
    const score = m.score ?? null;
    const yValue = score != null ? score : hasData ? rate : 0;
    return {
      i,
      task,
      rate,
      hasData,
      bucket,
      score,
      passed: m.passed ?? null,
      total: m.total ?? null,
      x: xFor(i),
      y: yFor(yValue),
      label: `T${i + 1}`,
    };
  });

  // Build the line as one or more subpaths so trajectories without data
  // (e.g. when a workflow step is selected and a task wasn't aligned to
  // that skill) leave a gap rather than artificially dragging the line
  // down to 0%.
  const linePath = (() => {
    let d = "";
    let inSegment = false;
    for (const p of points) {
      if (!p.hasData) {
        inSegment = false;
        continue;
      }
      d += `${inSegment ? "L" : "M"} ${p.x} ${p.y} `;
      inSegment = true;
    }
    return d.trim();
  })();

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
                  p.hasData
                    ? `${Math.round(
                        (p.score != null ? p.score : p.rate) * 100,
                      )}%${hoverContextLabel ? ` ${hoverContextLabel}` : p.score != null ? " weighted" : " leaf rate"}`
                    : "not scored"
                }`}
              </title>
            </rect>
          </g>
        ))}
      </svg>

      {/* Hover card */}
      {hovered ? (
        <TrendHoverCard
          point={hovered}
          chartWidth={W}
          padL={padL}
          padR={padR}
          contextLabel={hoverContextLabel}
        />
      ) : null}
    </div>
  );
}

function TrendHoverCard({ point, chartWidth, padL, padR, contextLabel }) {
  const leftFrac = point.x / chartWidth;
  const clampedLeftFrac = Math.max(padL / chartWidth, Math.min(1 - padR / chartWidth, leftFrac));
  const title =
    point.task.prompt_preview?.trim() || "(empty prompt)";
  const bucketStyle = BUCKET_STYLES[point.bucket] || BUCKET_STYLES.unknown;
  const aligned = isWorkflowAligned(point.task);
  const stepCtx = contextLabel || null;
  const inferredLabel = aligned ? "workflow" : "weighted";
  const inferredTooltip = aligned
    ? "Workflow alignment rate: passed leaf steps / total leaf steps"
    : "Depth-weighted score: 0.5·top + 0.25·L2 + 0.125·L3 + …";
  // When the parent passed step-specific passed/total (i.e. a workflow
  // step is selected in the dropdown) prefer that summary line over the
  // task-wide leaf summary so the tooltip matches the dot.
  const stepHasCounts =
    point.total != null && point.passed != null && point.total > 0;
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
          title={
            stepCtx
              ? "Workflow step alignment rate: passed leaf steps / total leaf steps under this step"
              : inferredTooltip
          }
        >
          {stepCtx || inferredLabel}
        </span>
      </div>
      {stepHasCounts ? (
        <div className="mt-0.5 flex items-center gap-1 text-[10px] text-text-muted">
          <span>
            {point.passed}/{point.total} step leaves
          </span>
          <span className="text-text-muted">
            · {Math.round((point.rate || 0) * 100)}%
          </span>
        </div>
      ) : point.task.leaf_summary?.total ? (
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

function Kpi({ icon, label, value, sub, accent }) {
  return (
    <div className="rounded-lg border border-border/60 bg-[#2a2c31] p-4 shadow-[0_2px_12px_rgba(0,0,0,0.25)]">
      <div className="flex items-center gap-2">
        {createElement(icon, { size: 14, className: "text-accent-teal" })}
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
  const [page, setPage] = useState(0);
  // null = "All". `recent` is newest-first, so slicing from the head
  // keeps the chart focused on the most recent N sessions.
  const [trendWindow, setTrendWindow] = useState(10);
  // null = "Overall" (existing depth-weighted/score behaviour). When a
  // workflow step is picked from the dropdown the trend chart instead
  // plots the per-task success rate of that one step across all
  // trajectories the user is looking at.
  const [selectedStepKey, setSelectedStepKey] = useState(null);

  const trendTasks = useMemo(() => {
    if (trendWindow == null) return recent;
    return recent.slice(0, trendWindow);
  }, [recent, trendWindow]);

  // Walk every task's cached workflow alignments to discover the set of
  // top-level workflow steps the user can drill into. We key by
  // ``<skill>::<rootIndex>`` so two skills that happen to share a step
  // title stay distinct, and we count how many trajectories surfaced
  // each step so the dropdown can show "step (4)" hints.
  const stepOptions = useMemo(() => {
    const map = new Map();
    for (const task of recent) {
      const skills = task?.workflow_summary?.skills || [];
      for (const s of skills) {
        const wf = s?.workflow;
        if (!wf || !Array.isArray(wf.root_steps)) continue;
        const skillKey = s.skill_slug || s.skill_id || "_unknown";
        const skillTitle = wf.title || s.skill_slug || s.skill_id || "Skill";
        wf.root_steps.forEach((step, idx) => {
          const key = `${skillKey}::${idx}`;
          const existing = map.get(key);
          if (existing) {
            existing.taskCount += 1;
          } else {
            map.set(key, {
              key,
              skillKey,
              skillSlug: s.skill_slug || null,
              skillId: s.skill_id || null,
              skillTitle,
              path: [idx],
              stepTitle: step?.title || `Step ${idx + 1}`,
              taskCount: 1,
            });
          }
        });
      }
    }
    return Array.from(map.values()).sort((a, b) => {
      if (a.skillTitle !== b.skillTitle) {
        return a.skillTitle.localeCompare(b.skillTitle);
      }
      return a.path[0] - b.path[0];
    });
  }, [recent]);

  // Group options by skill so the <select> can render <optgroup> headers
  // when multiple skills are aligned.
  const stepGroups = useMemo(() => {
    const groups = new Map();
    for (const opt of stepOptions) {
      if (!groups.has(opt.skillKey)) {
        groups.set(opt.skillKey, { title: opt.skillTitle, options: [] });
      }
      groups.get(opt.skillKey).options.push(opt);
    }
    return Array.from(groups.values());
  }, [stepOptions]);

  // If the underlying recent list shrinks/changes (e.g. annotation
  // refresh) and the previously-selected step is no longer present, fall
  // back to "Overall" so the chart never references a stale option.
  useEffect(() => {
    if (
      selectedStepKey != null &&
      !stepOptions.some((o) => o.key === selectedStepKey)
    ) {
      setSelectedStepKey(null);
    }
  }, [selectedStepKey, stepOptions]);

  const selectedStep = useMemo(() => {
    if (!selectedStepKey) return null;
    return stepOptions.find((o) => o.key === selectedStepKey) || null;
  }, [selectedStepKey, stepOptions]);

  // Resolve the step within a single task's cached alignment and return
  // the same {score, rate, hasData, bucket} shape the default trend
  // metric uses, plus passed/total so the hover card can show step
  // counts. Tasks that weren't aligned to this step's skill come back
  // ``hasData: false`` so the chart renders an unknown gray dot and the
  // line skips the gap.
  const buildStepMetric = (step) => (task) => {
    if (!step) return { score: null, rate: 0, hasData: false, bucket: "unknown" };
    const skills = task?.workflow_summary?.skills || [];
    const skill = skills.find(
      (s) =>
        (step.skillSlug && s.skill_slug === step.skillSlug) ||
        (step.skillId && s.skill_id === step.skillId),
    );
    if (!skill || !skill.workflow || !skill.workflow_alignment) {
      return { score: null, rate: 0, hasData: false, bucket: "unknown" };
    }
    let node = skill.workflow.root_steps?.[step.path[0]];
    for (let d = 1; d < step.path.length; d += 1) {
      node = node?.children?.[step.path[d]];
    }
    if (!node) {
      return { score: null, rate: 0, hasData: false, bucket: "unknown" };
    }
    const completion = subtreeCompletion(node, step.path, skill.workflow_alignment);
    if (!completion || completion.total === 0) {
      return { score: null, rate: 0, hasData: false, bucket: "unknown" };
    }
    const rate = completion.rate ?? 0;
    return {
      score: rate,
      rate,
      hasData: true,
      bucket: scoreBucket(rate),
      passed: completion.passed,
      total: completion.total,
    };
  };

  const trendMetricFn = useMemo(() => {
    if (!selectedStep) return null;
    return buildStepMetric(selectedStep);
  }, [selectedStep]);

  // Average step success rate across the currently-windowed trajectories
  // that actually had this step aligned. Used for the small summary line
  // above the chart so the user sees a single number alongside the
  // per-trajectory plot.
  const stepSummary = useMemo(() => {
    if (!selectedStep || !trendMetricFn) return null;
    let sum = 0;
    let count = 0;
    let passed = 0;
    let total = 0;
    for (const task of trendTasks) {
      const m = trendMetricFn(task);
      if (m.hasData) {
        sum += m.rate;
        count += 1;
        passed += m.passed || 0;
        total += m.total || 0;
      }
    }
    if (count === 0) return { count, total: 0, passed: 0, avg: null, microRate: null };
    return {
      count,
      total,
      passed,
      avg: sum / count,
      microRate: total > 0 ? passed / total : null,
    };
  }, [selectedStep, trendMetricFn, trendTasks]);

  const PAGE_SIZE = 5;
  const pageCount = Math.max(1, Math.ceil(recent.length / PAGE_SIZE));
  // Clamp the current page if the underlying list shrinks (e.g. filters
  // applied upstream) so we don't end up stranded on an empty page.
  useEffect(() => {
    if (page > pageCount - 1) setPage(pageCount - 1);
  }, [pageCount, page]);
  const pageStart = page * PAGE_SIZE;
  const pageEnd = Math.min(pageStart + PAGE_SIZE, recent.length);
  const pageItems = recent.slice(pageStart, pageEnd);

  const unannotated = aggregate?.unannotated_tasks ?? 0;
  const annotated = aggregate?.annotated_tasks ?? 0;

  // The headline KPI uses the depth-weighted aggregated mean (0.5·L1_avg
  // + 0.25·L2_avg + …) so it honours the spec. ``avg_task_score`` is
  // provided by the backend and now prefers workflow-alignment rate for
  // any run the user has compared against a skill workflow, with
  // ``avg_task_score_goal_only`` and ``avg_leaf_rate`` kept around for
  // diagnostics / parity checks.
  const weightedRate =
    typeof aggregate?.avg_task_score === "number"
      ? aggregate.avg_task_score
      : aggregate?.avg_leaf_rate;
  const leafPct = Math.round((weightedRate || 0) * 100);
  const leafAccent = accentForRate(weightedRate);
  const tasksWorkflowAligned = aggregate?.tasks_workflow_aligned ?? 0;
  const goalOnlyRate = aggregate?.avg_task_score_goal_only ?? null;
  const workflowRate = aggregate?.avg_workflow_rate ?? null;
  const workflowSteps = {
    total: aggregate?.total_workflow_steps ?? 0,
    passed: aggregate?.total_workflow_steps_passed ?? 0,
  };
  const workflowMicroPct =
    workflowSteps.total > 0
      ? Math.round((workflowSteps.passed / workflowSteps.total) * 100)
      : 0;

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

  // "Tasks achieved" is a pure workflow-alignment KPI — a task counts iff
  // the user has aligned it against a skill workflow AND every workflow
  // step is satisfied. The denominator is therefore the number of
  // workflow-aligned runs, not all annotated runs, so unaligned tasks
  // don't quietly drag the ratio down or pad the denominator.
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
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
        <Kpi
          icon={TrendingUp}
          label="Avg success rate"
          value={annotatedTasks > 0 ? `${leafPct}%` : "—"}
          sub={
            tasksWorkflowAligned > 0
              ? `workflow alignment for ${tasksWorkflowAligned} task${
                  tasksWorkflowAligned !== 1 ? "s" : ""
                }${
                  typeof goalOnlyRate === "number"
                    ? ` · LLM-goal only ${Math.round(goalOnlyRate * 100)}%`
                    : ""
                }`
              : "depth-weighted mean (0.5·L1 + 0.25·L2 + …)"
          }
          accent={annotatedTasks > 0 ? leafAccent : undefined}
        />
        {/* Always render so the layout doesn't shift the moment the first
            alignment lands. Shows ``—/—`` until the user aligns at least
            one task in the trajectory drawer's Workflow tab. */}
        <Kpi
          icon={GitCompareArrows}
          label="Workflow alignment"
          value={
            workflowSteps.total > 0 ? (
              <>
                <span>{workflowSteps.passed}</span>
                <span className="text-lg font-normal text-text-muted">
                  {" / "}
                  {workflowSteps.total}
                </span>
              </>
            ) : (
              <>
                <span className="text-text-muted">—</span>
                <span className="text-lg font-normal text-text-muted">
                  {" / "}
                  —
                </span>
              </>
            )
          }
          sub={
            tasksWorkflowAligned > 0
              ? workflowSteps.total > 0
                ? `${workflowMicroPct}% of workflow steps · avg ${Math.round(
                    (workflowRate || 0) * 100,
                  )}% per task`
                : "no leaf-step signal yet"
              : "align a task in the trajectory drawer to populate"
          }
          accent={
            tasksWorkflowAligned > 0 ? accentForRate(workflowRate) : undefined
          }
        />
        <Kpi
          icon={Target}
          label="Tasks achieved"
          value={
            tasksWorkflowAligned > 0 ? (
              <>
                <span>{tasksFullyAchieved}</span>
                <span className="text-lg font-normal text-text-muted">
                  {" / "}
                  {tasksWorkflowAligned}
                </span>
              </>
            ) : (
              "—"
            )
          }
          sub={
            tasksWorkflowAligned > 0
              ? "workflow alignment = 100%"
              : "align a task against a skill workflow to populate"
          }
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
          <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <TrendingUp size={14} className="text-accent-teal" />
              <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
                Goal achievement trend
              </h3>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {stepOptions.length > 0 ? (
                <label className="flex items-center gap-1.5 text-[11px] text-text-muted">
                  <span className="uppercase tracking-wider">Inspect</span>
                  <select
                    value={selectedStepKey || ""}
                    onChange={(e) => setSelectedStepKey(e.target.value || null)}
                    className="max-w-[220px] truncate rounded border border-border/50 bg-surface/60 px-1.5 py-0.5 text-[11px] text-text-secondary hover:border-accent-teal/40 hover:text-text-primary focus:border-accent-teal/60 focus:outline-none"
                    aria-label="Inspect a specific workflow step"
                  >
                    <option value="">Overall</option>
                    {stepGroups.map((g) => (
                      <optgroup key={g.title} label={g.title}>
                        {g.options.map((opt) => (
                          <option key={opt.key} value={opt.key}>
                            {opt.stepTitle}
                            {opt.taskCount > 1 ? ` (${opt.taskCount})` : ""}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                </label>
              ) : null}
              <div
                className="flex items-center gap-1"
                role="group"
                aria-label="Trend window"
              >
                {[
                  { label: "5", value: 5 },
                  { label: "10", value: 10 },
                  { label: "All", value: null },
                ].map((opt) => {
                  const active = trendWindow === opt.value;
                  const disabled =
                    opt.value != null && opt.value >= recent.length;
                  return (
                    <button
                      key={opt.label}
                      type="button"
                      onClick={() => setTrendWindow(opt.value)}
                      disabled={disabled && !active}
                      className={`rounded border px-2 py-0.5 text-[11px] tabular-nums transition-colors ${
                        active
                          ? "border-accent-teal/50 bg-accent-teal/15 text-accent-teal"
                          : "border-border/50 bg-surface/60 text-text-muted hover:border-accent-teal/30 hover:text-text-primary"
                      } ${
                        disabled && !active
                          ? "cursor-not-allowed opacity-40 hover:border-border/50 hover:text-text-muted"
                          : ""
                      }`}
                    >
                      {opt.label}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
          {selectedStep ? (
            <p className="mb-1 text-[11px] text-text-muted">
              <span className="text-text-secondary">{selectedStep.stepTitle}</span>
              {" "}· per-task success rate of this workflow step across {trendTasks.length} task
              {trendTasks.length !== 1 ? "s" : ""}
              {stepSummary && stepSummary.count > 0 ? (
                <>
                  {" · avg "}
                  <span
                    className={`font-semibold tabular-nums ${accentForRate(stepSummary.avg)}`}
                  >
                    {Math.round(stepSummary.avg * 100)}%
                  </span>
                  {" over "}
                  {stepSummary.count} aligned trajector{stepSummary.count === 1 ? "y" : "ies"}
                  {stepSummary.total > 0 ? (
                    <>
                      {" · "}
                      {stepSummary.passed}/{stepSummary.total} leaf steps
                    </>
                  ) : null}
                </>
              ) : (
                " · no aligned trajectories in this window"
              )}
              {onOpenTrajectory ? " · click a point to open" : ""}
            </p>
          ) : (
            <p className="mb-1 text-[11px] text-text-muted">
              Leaf-step achievement across the most recent {trendTasks.length} task
              {trendTasks.length !== 1 ? "s" : ""} · dots colored by bucket · hover for details
              {onOpenTrajectory ? " · click a point to open" : ""}
            </p>
          )}
          <TrendChart
            tasks={trendTasks}
            getMetric={trendMetricFn}
            hoverContextLabel={selectedStep ? "step rate" : undefined}
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
          <>
            <ul className="space-y-2">
              {pageItems.map((run, i) => {
                const key = `${run.session_id}-${run.task_index}`;
                return (
                  <TaskRow
                    key={key}
                    index={pageStart + i}
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
            {pageCount > 1 ? (
              <div className="mt-3 flex items-center justify-between text-[11px] text-text-muted">
                <span className="tabular-nums">
                  Showing {pageStart + 1}–{pageEnd} of {recent.length}
                </span>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    disabled={page === 0}
                    className="inline-flex items-center gap-1 rounded border border-border/50 bg-surface/60 px-2 py-1 text-[11px] text-text-secondary hover:border-accent-teal/40 hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-40"
                    aria-label="Previous page"
                  >
                    <ChevronLeft size={12} />
                    Prev
                  </button>
                  <span className="tabular-nums">
                    Page {page + 1} / {pageCount}
                  </span>
                  <button
                    type="button"
                    onClick={() =>
                      setPage((p) => Math.min(pageCount - 1, p + 1))
                    }
                    disabled={page >= pageCount - 1}
                    className="inline-flex items-center gap-1 rounded border border-border/50 bg-surface/60 px-2 py-1 text-[11px] text-text-secondary hover:border-accent-teal/40 hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-40"
                    aria-label="Next page"
                  >
                    Next
                    <ChevronRight size={12} />
                  </button>
                </div>
              </div>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
