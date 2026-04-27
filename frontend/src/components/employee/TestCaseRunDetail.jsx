import { ExternalLink, X } from "lucide-react";

function VerdictPill({ verdict }) {
  if (verdict === "pass") {
    return <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs text-emerald-400">pass</span>;
  }
  if (verdict === "fail") {
    return <span className="rounded-full bg-red-500/15 px-2 py-0.5 text-xs text-red-400">fail</span>;
  }
  if (verdict === "timeout") {
    return <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-xs text-amber-400">timeout</span>;
  }
  return <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-xs text-amber-400">error</span>;
}

export default function TestCaseRunDetail({ run, onClose, onOpenTrajectory }) {
  if (!run) return null;
  const checks = run.deterministic_checks || {};

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-3xl rounded-xl border border-border/40 bg-workspace">
        <div className="flex items-center justify-between border-b border-border/30 px-4 py-3">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-text-primary">Test run details</h3>
            <VerdictPill verdict={run.verdict} />
            <span className="text-xs text-text-muted">{run.verdict_source}</span>
          </div>
          <button type="button" onClick={onClose} className="rounded p-1 text-text-muted hover:bg-surface">
            <X size={16} />
          </button>
        </div>

        <div className="max-h-[70vh] space-y-4 overflow-y-auto p-4 text-sm">
          <div className="rounded-lg border border-border/40 bg-surface p-3">
            <p className="text-xs uppercase tracking-wide text-text-muted">Deterministic checks</p>
            <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
              <span>Finished cleanly: {String(Boolean(checks.finished_cleanly))}</span>
              <span>Non-empty output: {String(Boolean(checks.non_empty_output))}</span>
              <span>Latency budget: {String(Boolean(checks.latency_within_budget))}</span>
              {checks.used_tools?.length > 0 && (
                <span className="col-span-2 text-text-muted">
                  Tools used: {checks.used_tools.join(", ")}
                </span>
              )}
            </div>
          </div>

          {run.judge_rationale ? (
            <div className="rounded-lg border border-border/40 bg-surface p-3">
              <p className="text-xs uppercase tracking-wide text-text-muted">Judge rationale</p>
              <p className="mt-2 text-text-secondary">{run.judge_rationale}</p>
              {run.judge_evidence_quote ? (
                <blockquote className="mt-2 border-l-2 border-accent-teal/40 pl-3 text-xs text-text-muted">
                  {run.judge_evidence_quote}
                </blockquote>
              ) : null}
            </div>
          ) : null}

          {run.failure_reason ? (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-red-400">
              {run.failure_reason}
            </div>
          ) : null}

          <div className="rounded-lg border border-border/40 bg-surface p-3">
            <p className="text-xs uppercase tracking-wide text-text-muted">Raw output</p>
            <pre className="mt-2 whitespace-pre-wrap break-words text-xs text-text-secondary">
              {run.raw_output || "(empty)"}
            </pre>
          </div>

          {run.agent_session_id ? (
            <button
              type="button"
              className="inline-flex items-center gap-1 text-xs text-accent-teal hover:underline"
              onClick={() => onOpenTrajectory?.(run)}
            >
              <ExternalLink size={12} />
              View trajectory
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
