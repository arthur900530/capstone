import { useMemo, useState } from "react";
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Circle,
  CircleDot,
  XCircle,
} from "lucide-react";
import {
  alignmentForPath,
  formatRate,
  formatTimestamp,
  subtreeCompletion,
} from "./workflowScore";

// Shared workflow / trajectory tree renderer.
//
// Modes:
// - "workflow"   : ingest review (steps + timestamps + active step sync)
// - "alignment"  : test-case judge results (per-step satisfied / missed badge)
// - "trajectory" : agent run trajectory (timestamps optional, no badges)
//
// Props:
// - nodes         : array of { title, description, start_time?, end_time?, children? }
// - mode          : "workflow" | "alignment" | "trajectory"
// - alignment     : { steps: [{path, satisfied, evidence}] } when mode="alignment"
// - currentTime   : number (seconds) used to highlight the active leaf in "workflow" mode
// - onSeek        : (seconds: number) => void; clicking a step seeks to its start_time
// - emptyMessage  : optional override of the empty-state copy

export default function WorkflowTree({
  nodes,
  mode = "workflow",
  alignment = null,
  currentTime = null,
  onSeek = null,
  emptyMessage = "No workflow steps recorded.",
}) {
  if (!Array.isArray(nodes) || nodes.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border/40 bg-charcoal/30 px-4 py-6 text-center text-xs text-text-muted">
        {emptyMessage}
      </div>
    );
  }
  return (
    <ul className="space-y-1.5">
      {nodes.map((node, index) => (
        <WorkflowNode
          key={index}
          node={node}
          path={[index]}
          depth={0}
          mode={mode}
          alignment={alignment}
          currentTime={currentTime}
          onSeek={onSeek}
        />
      ))}
    </ul>
  );
}

function WorkflowNode({
  node,
  path,
  depth,
  mode,
  alignment,
  currentTime,
  onSeek,
}) {
  const hasChildren = Array.isArray(node?.children) && node.children.length > 0;
  const [open, setOpen] = useState(depth < 2);

  const startLabel = formatTimestamp(node?.start_time);
  const endLabel = formatTimestamp(node?.end_time);
  const range = startLabel
    ? endLabel
      ? `${startLabel} – ${endLabel}`
      : startLabel
    : null;

  const isLeaf = !hasChildren;
  const active = useMemo(() => {
    if (mode !== "workflow") return false;
    if (currentTime === null || currentTime === undefined) return false;
    if (node?.start_time === null || node?.start_time === undefined) return false;
    const end = node?.end_time ?? Number.POSITIVE_INFINITY;
    return currentTime >= node.start_time && currentTime <= end;
  }, [mode, currentTime, node?.start_time, node?.end_time]);

  const alignmentEntry =
    mode === "alignment" && isLeaf ? alignmentForPath(alignment, path) : null;
  const subtreeStats =
    mode === "alignment" && hasChildren
      ? subtreeCompletion(node, path, alignment)
      : null;

  const seekTarget =
    typeof onSeek === "function" && typeof node?.start_time === "number"
      ? node.start_time
      : null;

  const handleHeaderClick = () => {
    if (seekTarget !== null) onSeek(seekTarget);
    if (hasChildren) setOpen((v) => !v);
  };

  const ringClass = active
    ? "ring-1 ring-accent-teal/60 bg-accent-teal/5"
    : "ring-1 ring-transparent hover:ring-border/40";

  return (
    <li>
      <div
        onClick={handleHeaderClick}
        className={`group flex cursor-pointer items-start gap-2 rounded-md border border-border/30 bg-charcoal/40 px-2.5 py-2 transition-colors ${ringClass}`}
      >
        <ChevronAffordance hasChildren={hasChildren} open={open} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            {mode === "alignment" && isLeaf ? (
              <AlignmentBadge entry={alignmentEntry} />
            ) : null}
            <span className="min-w-0 flex-1 truncate text-sm font-medium text-text-primary">
              {node?.title || "(untitled step)"}
            </span>
            {range ? (
              <span className="shrink-0 rounded bg-charcoal/70 px-1.5 py-0.5 font-mono text-[10px] text-text-muted">
                {range}
              </span>
            ) : null}
            {subtreeStats ? <SubtreeChip stats={subtreeStats} /> : null}
          </div>
          {node?.description ? (
            <p className="mt-1 line-clamp-2 text-xs text-text-muted whitespace-pre-wrap">
              {node.description}
            </p>
          ) : null}
          {alignmentEntry?.evidence ? (
            <p className="mt-1 text-[11px] italic text-text-muted">
              <span className="text-text-secondary not-italic">Evidence:</span>{" "}
              {alignmentEntry.evidence}
            </p>
          ) : null}
        </div>
      </div>
      {hasChildren && open ? (
        <ul className="mt-1.5 space-y-1.5 border-l border-border/30 pl-3">
          {node.children.map((child, idx) => (
            <WorkflowNode
              key={idx}
              node={child}
              path={[...path, idx]}
              depth={depth + 1}
              mode={mode}
              alignment={alignment}
              currentTime={currentTime}
              onSeek={onSeek}
            />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

function ChevronAffordance({ hasChildren, open }) {
  if (!hasChildren) {
    return <Circle size={10} className="mt-1.5 shrink-0 text-text-muted/60" />;
  }
  const Icon = open ? ChevronDown : ChevronRight;
  return <Icon size={14} className="mt-0.5 shrink-0 text-text-secondary" />;
}

function AlignmentBadge({ entry }) {
  if (!entry) {
    return (
      <span
        title="Not graded by judge"
        className="inline-flex shrink-0 items-center gap-1 rounded-md bg-text-muted/10 px-1.5 py-0.5 text-[10px] font-medium text-text-muted"
      >
        <CircleDot size={10} />
        n/a
      </span>
    );
  }
  if (entry.satisfied === true) {
    return (
      <span
        title={entry.evidence || "Satisfied"}
        className="inline-flex shrink-0 items-center gap-1 rounded-md bg-emerald-400/10 px-1.5 py-0.5 text-[10px] font-medium text-emerald-300"
      >
        <CheckCircle2 size={10} />
        ok
      </span>
    );
  }
  return (
    <span
      title={entry.evidence || "Not satisfied"}
      className="inline-flex shrink-0 items-center gap-1 rounded-md bg-rose-400/10 px-1.5 py-0.5 text-[10px] font-medium text-rose-300"
    >
      <XCircle size={10} />
      miss
    </span>
  );
}

function SubtreeChip({ stats }) {
  if (!stats || stats.total === 0) return null;
  return (
    <span className="shrink-0 rounded-md bg-charcoal/70 px-1.5 py-0.5 font-mono text-[10px] text-text-secondary">
      {stats.passed}/{stats.total} · {formatRate(stats.rate)}
    </span>
  );
}
