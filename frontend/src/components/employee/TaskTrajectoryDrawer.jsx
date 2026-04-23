import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  BarChart3,
  ChevronDown,
  ChevronRight,
  ListTree,
  Loader2,
  PanelRightClose,
  Rows3,
  ScrollText,
} from "lucide-react";
import { fetchTaskTrajectory } from "../../services/api";
import TrajectoryNodeCard from "./TrajectoryNodeCard";

function formatMs(ms) {
  if (!ms) return "0ms";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function flattenActions(node) {
  if (!node) return [];
  if (node.node_type === "action") return [node];
  return (node.nodes || []).flatMap(flattenActions);
}

function StatPill({ label, value }) {
  return (
    <div className="rounded-lg border border-border/50 bg-surface/40 px-3 py-2">
      <p className="text-[10px] font-medium uppercase tracking-wider text-text-muted">
        {label}
      </p>
      <p className="mt-1 text-sm font-semibold text-text-primary">{value}</p>
    </div>
  );
}

function ViewButton({ active, icon: Icon, label, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors ${
        active
          ? "bg-accent-teal text-charcoal"
          : "bg-surface text-text-secondary hover:text-text-primary"
      }`}
    >
      <Icon size={14} />
      {label}
    </button>
  );
}

function TreeNode({ node, depth = 0 }) {
  const [open, setOpen] = useState(depth < 2);

  if (!node) return null;
  if (node.node_type === "action") {
    return <TrajectoryNodeCard node={node} />;
  }

  return (
    <div className="space-y-3">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center justify-between rounded-xl border border-border/50 bg-[#2a2c31] px-4 py-3 text-left"
      >
        <div>
          <p className="text-sm font-semibold text-text-primary">
            {node.goal || "Sequence"}
          </p>
          <p className="mt-1 text-xs text-text-muted">
            {(node.nodes || []).length} item{(node.nodes || []).length !== 1 ? "s" : ""}
          </p>
        </div>
        <div className="text-text-muted">
          {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </div>
      </button>
      {open ? (
        <div className="ml-4 space-y-3 border-l border-border/40 pl-4">
          {(node.nodes || []).map((child, index) => (
            <TreeNode key={`${child.node_type}-${index}`} node={child} depth={depth + 1} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

export default function TaskTrajectoryDrawer({ employeeId, task, onClose }) {
  const [view, setView] = useState("hierarchical");
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!task) return undefined;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);

    fetchTaskTrajectory(employeeId, task.sessionId, task.taskIndex)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || "Failed to load trajectory");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [employeeId, task]);

  const linearNodes = useMemo(() => flattenActions(data?.tree), [data?.tree]);

  if (!task) return null;

  const summary = data?.summary;

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/50 backdrop-blur-[1px]">
      <button
        type="button"
        onClick={onClose}
        className="flex-1 cursor-default"
        aria-label="Close trajectory drawer"
      />
      <div className="flex h-full w-full max-w-3xl flex-col border-l border-border/40 bg-workspace shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b border-border/30 px-6 py-5">
          <div className="min-w-0">
            <div className="mb-2 flex items-center gap-2">
              <BarChart3 size={16} className="text-accent-teal" />
              <h2 className="text-base font-semibold text-text-primary">
                Task trajectory
              </h2>
            </div>
            <p className="text-sm text-text-secondary whitespace-pre-wrap break-words">
              {data?.prompt || task.run?.prompt_preview || "(prompt unavailable)"}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-text-muted transition-colors hover:bg-surface hover:text-text-primary"
          >
            <PanelRightClose size={18} />
          </button>
        </div>

        <div className="border-b border-border/20 px-6 py-4">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <StatPill label="Duration" value={formatMs(summary?.duration_ms ?? task.run?.duration_ms)} />
            <StatPill label="Trials" value={summary?.n_trials ?? task.run?.n_trials ?? 1} />
            <StatPill label="Tools" value={summary?.n_tool_calls ?? task.run?.n_tool_calls ?? 0} />
            <StatPill label="Status" value={summary?.status || "unknown"} />
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <ViewButton
              active={view === "linear"}
              icon={Rows3}
              label="Linear"
              onClick={() => setView("linear")}
            />
            <ViewButton
              active={view === "hierarchical"}
              icon={ListTree}
              label="Hierarchical"
              onClick={() => setView("hierarchical")}
            />
            <ViewButton
              active={view === "raw"}
              icon={ScrollText}
              label="Raw"
              onClick={() => setView("raw")}
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          {loading ? (
            <div className="flex h-full items-center justify-center">
              <Loader2 size={20} className="animate-spin text-accent-teal" />
            </div>
          ) : null}

          {!loading && error ? (
            <div className="flex items-center gap-2 rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
              <AlertCircle size={16} />
              {error}
            </div>
          ) : null}

          {!loading && !error && data?.available === false ? (
            <div className="rounded-xl border border-border/40 bg-[#2a2c31] px-5 py-6">
              <div className="mb-2 flex items-center gap-2 text-text-primary">
                <AlertCircle size={16} className="text-yellow-400" />
                <p className="font-medium">Trajectory unavailable</p>
              </div>
              <p className="text-sm text-text-muted">
                No stored trajectory exists for this task yet. Runs recorded before
                trajectory persistence was added cannot be replayed.
              </p>
            </div>
          ) : null}

          {!loading && !error && data?.available !== false ? (
            <>
              {view === "linear" ? (
                <div className="space-y-3">
                  {linearNodes.map((node, index) => (
                    <TrajectoryNodeCard key={`${node.action}-${index}`} node={node} />
                  ))}
                </div>
              ) : null}

              {view === "hierarchical" ? (
                <div className="space-y-3">
                  <TreeNode node={data?.tree} />
                </div>
              ) : null}

              {view === "raw" ? (
                <pre className="overflow-x-auto rounded-xl border border-border/40 bg-[#2a2c31] p-4 text-xs leading-relaxed text-text-secondary">
                  {JSON.stringify(data?.raw_events || [], null, 2)}
                </pre>
              ) : null}
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
