import { useEffect, useState } from "react";
import {
  BarChart3,
  Wrench,
  Timer,
  Repeat,
  Activity,
  Loader2,
  AlertCircle,
  ListChecks,
  ChevronRight,
} from "lucide-react";
import { fetchEmployeeMetrics } from "../../services/api";
import TaskTrajectoryDrawer from "./TaskTrajectoryDrawer";

/* ── Tiny primitives ──────────────────────────────────────────────────── */

function KpiCard({ label, value, sub }) {
  return (
    <div className="rounded-lg border border-border/60 bg-[#2a2c31] p-4 shadow-[0_2px_12px_rgba(0,0,0,0.25)]">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">
        {label}
      </p>
      <p className="mt-1.5 text-2xl font-semibold text-text-primary">{value}</p>
      {sub && <p className="mt-0.5 text-[11px] text-text-muted">{sub}</p>}
    </div>
  );
}

function MetricCard({ icon: Icon, label, children }) {
  return (
    <div className="rounded-lg border border-border/60 bg-[#2a2c31] p-4 shadow-[0_2px_12px_rgba(0,0,0,0.25)]">
      <div className="mb-3 flex items-center gap-2">
        <Icon size={15} className="text-accent-teal" />
        <h4 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
          {label}
        </h4>
      </div>
      {children}
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex items-baseline justify-between py-1">
      <span className="text-xs text-text-muted">{label}</span>
      <span className="text-sm font-medium text-text-primary">{value}</span>
    </div>
  );
}

function ToolMixBar({ tool, count, total }) {
  const pct = total > 0 ? (count / total) * 100 : 0;
  return (
    <div className="mb-2.5 last:mb-0">
      <div className="mb-1 flex items-baseline justify-between">
        <span className="truncate pr-2 text-xs text-text-secondary">{tool}</span>
        <span className="shrink-0 text-[11px] text-text-muted tabular-nums">
          {count} · {pct.toFixed(0)}%
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-border/50">
        <div
          className="h-full rounded-full bg-accent-teal transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function RecentTaskRow({ run, onClick }) {
  const when = run.started_at ? new Date(run.started_at) : null;
  const durationSec = (run.duration_ms || 0) / 1000;
  const topTools = Object.entries(run.tool_histogram || {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4);

  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        className="w-full rounded-lg border border-border/40 bg-surface/40 p-3 text-left transition-colors hover:border-accent-teal/30 hover:bg-surface/60"
      >
        <div className="flex items-start justify-between gap-3">
          <p
            className="min-w-0 flex-1 truncate text-sm text-text-primary"
            title={run.prompt_preview}
          >
            {run.prompt_preview || <span className="italic text-text-muted">(empty prompt)</span>}
          </p>
          <div className="flex shrink-0 items-center gap-3 text-[11px] text-text-muted tabular-nums">
            <span>{run.n_tool_calls} tools</span>
            <span>{durationSec.toFixed(1)}s</span>
            {when && <span>{when.toLocaleString()}</span>}
            <ChevronRight size={14} className="text-text-muted" />
          </div>
        </div>
        {topTools.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {topTools.map(([name, n]) => (
              <span
                key={name}
                className="rounded bg-accent-teal/10 px-1.5 py-0.5 text-[10px] font-medium text-accent-teal"
              >
                {name}
                {n > 1 ? ` ×${n}` : ""}
              </span>
            ))}
            {run.n_trials > 1 && (
              <span className="rounded bg-yellow-500/10 px-1.5 py-0.5 text-[10px] font-medium text-yellow-400">
                {run.n_trials} trials
              </span>
            )}
            {run.n_reflections > 0 && (
              <span className="rounded bg-purple-500/10 px-1.5 py-0.5 text-[10px] font-medium text-purple-300">
                {run.n_reflections} reflections
              </span>
            )}
          </div>
        )}
      </button>
    </li>
  );
}

/* ── States ──────────────────────────────────────────────────────────── */

function EmptyState({ employee }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center">
      <BarChart3 size={28} className="mb-3 text-text-muted" />
      <p className="mb-1 text-sm font-medium text-text-primary">
        No performance data yet
      </p>
      <p className="max-w-xs text-center text-xs text-text-muted">
        Start a conversation to generate metrics. The report card will appear
        once {employee.name} has completed some tasks.
      </p>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="flex flex-1 items-center justify-center">
      <Loader2 size={20} className="animate-spin text-accent-teal" />
    </div>
  );
}

function ErrorState({ message }) {
  return (
    <div className="flex flex-1 items-center justify-center">
      <div className="flex items-center gap-2 text-sm text-red-400">
        <AlertCircle size={16} />
        {message}
      </div>
    </div>
  );
}

/* ── Main ────────────────────────────────────────────────────────────── */

function formatMs(ms) {
  if (!ms) return "0ms";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export default function EmployeeReportCard({ employee }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedTask, setSelectedTask] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchEmployeeMetrics(employee.id)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || "Failed to load metrics");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [employee.id]);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} />;

  const a = data?.aggregate;
  if (!a || a.tasks === 0) return <EmptyState employee={employee} />;

  const totalToolCalls = (a.tool_mix || []).reduce((s, [, n]) => s + n, 0);

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-5xl space-y-5 p-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-text-primary">
              Performance summary
            </h2>
            <p className="mt-0.5 text-xs text-text-muted">
              Across {a.tasks} task{a.tasks !== 1 ? "s" : ""}
              {employee.lastActiveAt && (
                <>
                  {" "}· last active{" "}
                  {new Date(employee.lastActiveAt).toLocaleString()}
                </>
              )}
            </p>
          </div>
        </div>

        {/* KPI strip */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <KpiCard label="Tasks completed" value={a.tasks} />
          <KpiCard
            label="Avg tool calls / task"
            value={a.avg_tool_calls.toFixed(1)}
            sub={`${totalToolCalls} total calls`}
          />
          <KpiCard
            label="Avg latency"
            value={formatMs(a.avg_latency_ms)}
            sub={`p95 ${formatMs(a.p95_latency_ms)}`}
          />
          <KpiCard
            label="Avg trials / task"
            value={a.avg_trials.toFixed(2)}
            sub={`${(a.reflexion_rate * 100).toFixed(0)}% retried`}
          />
        </div>

        {/* Detail grid */}
        <div className="grid gap-4 lg:grid-cols-2">
          <MetricCard icon={Timer} label="Response latency">
            <Row label="Average" value={formatMs(a.avg_latency_ms)} />
            <Row label="P50" value={formatMs(a.p50_latency_ms)} />
            <Row label="P95" value={formatMs(a.p95_latency_ms)} />
          </MetricCard>

          <MetricCard icon={Repeat} label="Reflexion behavior">
            <Row label="Avg trials" value={a.avg_trials.toFixed(2)} />
            <Row label="Avg reflections" value={a.avg_reflections.toFixed(2)} />
            <Row
              label="Tasks needing retry"
              value={`${(a.reflexion_rate * 100).toFixed(0)}%`}
            />
          </MetricCard>

          <MetricCard icon={Wrench} label="Tool mix">
            {a.tool_mix.length === 0 ? (
              <p className="text-xs text-text-muted">No tools used yet.</p>
            ) : (
              a.tool_mix.map(([tool, n]) => (
                <ToolMixBar
                  key={tool}
                  tool={tool}
                  count={n}
                  total={totalToolCalls}
                />
              ))
            )}
          </MetricCard>

          <MetricCard icon={Activity} label="Throughput">
            <Row label="Total tasks" value={a.tasks} />
            <Row
              label="Total tool invocations"
              value={totalToolCalls.toLocaleString()}
            />
            <Row
              label="Unique tools used"
              value={a.tool_mix.length}
            />
          </MetricCard>
        </div>

        {/* Recent tasks */}
        <div>
          <div className="mb-2 flex items-center gap-2">
            <ListChecks size={15} className="text-accent-teal" />
            <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
              Recent tasks
            </h3>
            <span className="rounded-full bg-surface px-1.5 py-0.5 text-[10px] text-text-muted">
              {data.recent?.length ?? 0}
            </span>
          </div>
          {data.recent && data.recent.length > 0 ? (
            <ul className="space-y-2">
              {data.recent.map((r) => (
                <RecentTaskRow
                  key={`${r.session_id}-${r.task_index}`}
                  run={r}
                  onClick={() =>
                    setSelectedTask({
                      sessionId: r.session_id,
                      taskIndex: r.task_index,
                      run: r,
                    })
                  }
                />
              ))}
            </ul>
          ) : (
            <p className="rounded-lg border border-border/40 bg-surface/40 p-4 text-center text-xs text-text-muted">
              No recent tasks recorded.
            </p>
          )}
        </div>
      </div>
      {selectedTask ? (
        <TaskTrajectoryDrawer
          employeeId={employee.id}
          task={selectedTask}
          onClose={() => setSelectedTask(null)}
        />
      ) : null}
    </div>
  );
}
