import { useState, useEffect } from "react";
import {
  BarChart3,
  Loader2,
  AlertCircle,
  Clock,
  Cpu,
  CheckCircle2,
  ListChecks,
  Layers,
  Timer,
  ShieldAlert,
  Search,
  Bot,
  Wrench,
} from "lucide-react";
import { fetchEvaluations } from "../services/api";

function RateBar({ rate }) {
  const pct = (rate ?? 0) * 100;
  const color =
    pct >= 80
      ? "bg-emerald-500"
      : pct >= 60
        ? "bg-yellow-500"
        : "bg-red-500";

  return (
    <div className="flex items-center gap-3">
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-border/50">
        <div
          className={`h-full rounded-full transition-all duration-500 ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="shrink-0 text-sm font-medium text-text-primary">
        {pct.toFixed(1)}%
      </span>
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

function LatencyValue({ label, ms }) {
  const seconds = (ms / 1000).toFixed(1);
  return (
    <div className="flex items-baseline justify-between">
      <span className="text-xs text-text-muted">{label}</span>
      <span className="text-sm font-medium text-text-primary">{seconds}s</span>
    </div>
  );
}

function HallucinationBadge({ rate }) {
  const pct = (rate ?? 0) * 100;
  const color =
    pct <= 5
      ? "text-emerald-400"
      : pct <= 10
        ? "text-yellow-400"
        : "text-red-400";
  const bgColor =
    pct <= 5
      ? "bg-emerald-500/10"
      : pct <= 10
        ? "bg-yellow-500/10"
        : "bg-red-500/10";

  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-lg font-semibold ${color} ${bgColor}`}>
      {pct.toFixed(1)}%
    </span>
  );
}

function AgentListItem({ agent, run, isSelected, onSelect }) {
  const taskRate = run.task_success?.rate ?? 0;
  const pct = (taskRate * 100).toFixed(0);
  const rateColor =
    taskRate >= 0.8
      ? "text-emerald-400"
      : taskRate >= 0.6
        ? "text-yellow-400"
        : "text-red-400";

  return (
    <li>
      <button
        onClick={() => onSelect(run.agent_id)}
        className={`flex w-full items-start gap-2.5 rounded-lg px-3 py-2.5 text-left transition-colors ${
          isSelected
            ? "bg-surface text-text-primary"
            : "text-text-secondary hover:bg-surface/50 hover:text-text-primary"
        }`}
      >
        <div className="mt-0.5 shrink-0 rounded-md bg-accent-teal/10 p-1.5 text-accent-teal">
          <Bot size={13} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">
            {agent?.name ?? run.agent_id}
          </p>
          <p className="mt-0.5 truncate text-[11px] text-text-muted">
            {agent?.model?.split("/").pop() ?? "unknown model"}
          </p>
        </div>
        <span className={`mt-0.5 shrink-0 text-xs font-semibold ${rateColor}`}>
          {pct}%
        </span>
      </button>
    </li>
  );
}

function RunDetail({ run, agent }) {
  const categoryEntries = Object.entries(run.category_success || {});

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border/40 px-5 py-3">
        <div className="flex items-center gap-2">
          <Cpu size={15} className="text-accent-teal" />
          <h3 className="text-sm font-medium text-text-primary">
            {agent?.name ?? run.agent_id}
          </h3>
        </div>
        <div className="flex items-center gap-1.5 text-xs text-text-muted">
          <Clock size={11} />
          {run.timestamp}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-5">
        <div className="mx-auto max-w-2xl space-y-5">
          {/* Agent info */}
          <div className="flex items-center gap-3 rounded-lg border border-border/60 bg-[#2a2c31] px-4 py-3 shadow-[0_2px_12px_rgba(0,0,0,0.25)]">
            <div className="text-xs text-text-muted">
              <span className="font-medium text-text-secondary">Model:</span>{" "}
              <code className="rounded bg-surface px-1.5 py-0.5 text-accent-teal">
                {agent?.model ?? "N/A"}
              </code>
            </div>
          </div>

          {/* Skills Used */}
          {agent?.skills?.length > 0 && (
            <div className="rounded-lg border border-border/60 bg-[#2a2c31] px-4 py-3 shadow-[0_2px_12px_rgba(0,0,0,0.25)]">
              <div className="mb-2 flex items-center gap-2">
                <Wrench size={13} className="text-accent-teal" />
                <span className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
                  Skills Used
                </span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {agent.skills.map((skill) => (
                  <span
                    key={skill}
                    className="rounded-md bg-accent-teal/10 px-2 py-1 text-xs font-medium text-accent-teal"
                  >
                    {skill}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <MetricCard icon={CheckCircle2} label="Analysis Accuracy">
              <RateBar rate={run.task_success?.rate} />
              <p className="mt-1.5 text-right text-xs text-text-muted">
                {run.task_success?.passed}/{run.task_success?.total} queries resolved
              </p>
            </MetricCard>

            <MetricCard icon={ListChecks} label="Workflow Completion">
              <RateBar rate={run.step_success?.rate} />
              <p className="mt-1.5 text-right text-xs text-text-muted">
                {run.step_success?.passed}/{run.step_success?.total} steps completed
              </p>
            </MetricCard>

            <MetricCard icon={Layers} label="Financial Skill Proficiency">
              {categoryEntries.length > 0 ? (
                <div className="space-y-2.5">
                  {categoryEntries.map(([category, stats]) => (
                    <div key={category}>
                      <div className="mb-0.5 flex items-center justify-between">
                        <span className="text-xs text-text-muted">{category}</span>
                        <span className="text-xs text-text-muted">
                          {stats.passed}/{stats.total}
                        </span>
                      </div>
                      <RateBar rate={stats.rate} />
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-text-muted">No category data</p>
              )}
            </MetricCard>

            <div className="flex flex-col gap-4">
              <MetricCard icon={Timer} label="Response Latency">
                <div className="space-y-1.5">
                  <LatencyValue label="Average" ms={run.latency?.avg_ms} />
                  <LatencyValue label="P50" ms={run.latency?.p50_ms} />
                  <LatencyValue label="P95" ms={run.latency?.p95_ms} />
                  <LatencyValue label="P99" ms={run.latency?.p99_ms} />
                </div>
              </MetricCard>

              <MetricCard icon={ShieldAlert} label="Factual Reliability">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs text-text-muted">
                      {run.hallucination?.hallucinated} / {run.hallucination?.total_claims} claims flagged
                    </p>
                  </div>
                  <HallucinationBadge rate={run.hallucination?.rate} />
                </div>
              </MetricCard>
            </div>
          </div>

          <div className="text-xs text-text-muted">
            <span className="font-medium text-text-secondary">Run ID:</span>{" "}
            <code className="rounded bg-surface px-1.5 py-0.5 text-accent-teal">{run.run_id}</code>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function EvaluationView({ agentMap = {}, focusAgentId, onClearFocus }) {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedAgentId, setSelectedAgentId] = useState(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetchEvaluations()
      .then((data) => {
        if (!cancelled) {
          setRuns(data);
          setSelectedAgentId((prev) => prev ?? (data.length > 0 ? data[0].agent_id : null));
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (focusAgentId && runs.length > 0) {
      const match = runs.find((r) => r.agent_id === focusAgentId);
      if (match) {
        setSelectedAgentId(focusAgentId);
        const timer = setTimeout(() => onClearFocus?.(), 1000);
        return () => clearTimeout(timer);
      }
    }
  }, [focusAgentId, runs, onClearFocus]);

  const filtered = runs.filter((r) => {
    if (!search) return true;
    const q = search.toLowerCase();
    const agent = agentMap[r.agent_id];
    return (
      r.agent_id.toLowerCase().includes(q) ||
      (agent?.name ?? "").toLowerCase().includes(q) ||
      (agent?.model ?? "").toLowerCase().includes(q)
    );
  });

  const selectedRun = runs.find((r) => r.agent_id === selectedAgentId);

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <Loader2 size={24} className="animate-spin text-accent-teal" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="flex items-center gap-2 text-sm text-red-400">
          <AlertCircle size={16} />
          {error}
        </div>
      </div>
    );
  }

  if (runs.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center">
        <BarChart3 size={40} className="text-text-muted" />
        <div>
          <p className="text-sm font-medium text-text-primary">No evaluation runs yet</p>
          <p className="mt-1 text-xs text-text-muted">
            Run the benchmark to generate evaluation scores.
          </p>
          <code className="mt-2 inline-block rounded-lg bg-charcoal px-3 py-1.5 text-xs text-accent-teal">
            python -m src.main --question-file data/public.txt
          </code>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 overflow-hidden pt-12 lg:pt-0">
      {/* Agent list panel */}
      <div className="flex w-[280px] shrink-0 flex-col border-r border-border/40 bg-charcoal/30">
        <div className="border-b border-border/40 p-3">
          <div className="mb-2.5 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <BarChart3 size={15} className="text-accent-teal" />
              <h2 className="text-sm font-semibold text-text-primary">Evaluations</h2>
              <span className="rounded-full bg-surface px-1.5 py-0.5 text-[10px] text-text-muted">
                {runs.length}
              </span>
            </div>
          </div>
          <div className="relative">
            <Search
              size={14}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted"
            />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search agents…"
              className="w-full rounded-lg border border-border/40 bg-charcoal py-1.5 pl-8 pr-3 text-xs text-text-primary placeholder:text-text-muted outline-none transition-colors focus:border-accent-teal"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-2">
          {filtered.length === 0 ? (
            <p className="px-3 py-6 text-center text-xs text-text-muted">
              {search ? "No matching agents" : "No evaluations"}
            </p>
          ) : (
            <ul className="space-y-0.5">
              {filtered.map((run) => (
                <AgentListItem
                  key={run.run_id}
                  agent={agentMap[run.agent_id]}
                  run={run}
                  isSelected={run.agent_id === selectedAgentId}
                  onSelect={setSelectedAgentId}
                />
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Evaluation detail */}
      <div className="flex flex-1 flex-col bg-workspace">
        {selectedRun ? (
          <RunDetail
            key={selectedRun.run_id}
            run={selectedRun}
            agent={agentMap[selectedRun.agent_id]}
          />
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center">
            <BarChart3 size={40} className="text-text-muted" />
            <div>
              <p className="text-sm font-medium text-text-primary">Select an agent</p>
              <p className="mt-1 text-xs text-text-muted">
                Choose a digital employee from the list to view evaluation results.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
