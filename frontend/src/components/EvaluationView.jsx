import { createElement, useState, useEffect } from "react";
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
  ChevronRight,
  ArrowLeft,
  TrendingUp,
  Play,
} from "lucide-react";
import {
  fetchEvaluations,
  fetchSkillEvals,
  fetchAgentSkills,
  runSkillEval,
} from "../services/api";

function RateBar({ rate }) {
  const pct = (rate ?? 0) * 100;
  const color =
    pct >= 80 ? "bg-emerald-500" : pct >= 60 ? "bg-yellow-500" : "bg-red-500";

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

function MetricCard({ icon, label, children, onViewDetails }) {
  return (
    <div className="rounded-lg border border-border/60 bg-[#2a2c31] p-4 shadow-[0_2px_12px_rgba(0,0,0,0.25)]">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {createElement(icon, { size: 15, className: "text-accent-teal" })}
          <h4 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
            {label}
          </h4>
        </div>
        {onViewDetails && (
          <button
            onClick={onViewDetails}
            className="flex items-center gap-0.5 text-[11px] text-accent-teal hover:text-accent-teal/80 transition-colors"
          >
            View details <ChevronRight size={11} />
          </button>
        )}
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
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-lg font-semibold ${color} ${bgColor}`}
    >
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

function SkillEvalsPage({ skillEvals, onSkillEvalsUpdate, onBack, agentId }) {
  const [running, setRunning] = useState(false);
  const handleRun = async () => {
    setRunning(true);
    try {
      const { ran } = await runSkillEval(agentId);
      if (ran.length === 0) { setRunning(false); return; }
      const initialCount = skillEvals.length;
      const poll = setInterval(async () => {
        try {
          const latest = await fetchSkillEvals();
          if (latest.length > initialCount) {
            clearInterval(poll);
            setRunning(false);
            onSkillEvalsUpdate(latest);
          }
        } catch {
          clearInterval(poll);
          setRunning(false);
        }
      }, 5000);
    } catch (e) {
      console.error(e);
      setRunning(false);
    }
  };

  const rateColor = (v) =>
    v >= 0.8
      ? "text-emerald-400"
      : v >= 0.5
        ? "text-yellow-400"
        : "text-red-400";

  return (
    <div className="flex h-full flex-col">
      {/* Page header */}
      <div className="flex items-center gap-3 border-b border-border/40 px-5 py-3">
        <button
          onClick={onBack}
          className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-text-secondary hover:bg-surface/60 hover:text-text-primary transition-colors"
        >
          <ArrowLeft size={13} /> Back
        </button>
        <div className="flex items-center gap-2">
          <Layers size={15} className="text-accent-teal" />
          <h2 className="text-sm font-semibold text-text-primary">
            Financial Skill Proficiency
          </h2>
        </div>
        <span className="rounded-full bg-surface px-1.5 py-0.5 text-[10px] text-text-muted">
          {skillEvals.length} run{skillEvals.length !== 1 ? "s" : ""}
        </span>
        <button
          onClick={handleRun}
          disabled={running}
          className="ml-auto flex items-center gap-1.5 rounded-md bg-accent-teal px-3 py-1.5 text-xs font-semibold text-black hover:bg-accent-teal/80 transition-colors shadow-sm disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {running ? (
            <Loader2 size={11} className="animate-spin" />
          ) : (
            <Play size={11} fill="currentColor" />
          )}
          {running ? "Running…" : "Run Evaluation"}
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-5">
        {skillEvals.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
            <TrendingUp size={36} className="text-text-muted" />
            <p className="text-sm text-text-muted">
              No skill evaluation runs found.
            </p>
          </div>
        ) : (
          <div className="mx-auto max-w-3xl space-y-6">
            {skillEvals.map((ev) => (
              <div
                key={ev.run_name}
                className="rounded-xl border border-border/60 bg-[#2a2c31] shadow-[0_2px_12px_rgba(0,0,0,0.25)]"
              >
                {/* Run header */}
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/40 px-5 py-3">
                  <div className="flex items-center gap-2">
                    <span className="rounded-md bg-accent-teal/10 px-2 py-0.5 text-xs font-semibold text-accent-teal">
                      {ev.skill_name}
                    </span>
                    <span className="text-xs text-text-muted">
                      {ev.model_name?.split("/").pop()}
                    </span>
                  </div>
                  <span className="text-[11px] text-text-muted">
                    {ev.created_at
                      ? new Date(ev.created_at).toLocaleString()
                      : ev.run_name}
                  </span>
                </div>

                <div className="p-5 space-y-5">
                  {/* Pass-rate comparison */}
                  <div className="grid grid-cols-2 gap-4">
                    <div className="rounded-lg border border-border/40 bg-surface/40 p-4 text-center">
                      <p className="mb-1 text-[11px] uppercase tracking-wider text-text-muted">
                        With Skill
                      </p>
                      <p
                        className={`text-3xl font-bold ${rateColor(ev.mean_reward)}`}
                      >
                        {ev.mean_reward != null
                          ? `${(ev.mean_reward * 100).toFixed(1)}%`
                          : "—"}
                      </p>
                      <p className="mt-1 text-[11px] text-text-muted">
                        {ev.n_trials} trial{ev.n_trials !== 1 ? "s" : ""}
                      </p>
                    </div>
                    <div className="rounded-lg border border-border/40 bg-surface/40 p-4 text-center">
                      <p className="mb-1 text-[11px] uppercase tracking-wider text-text-muted">
                        Without Skill
                      </p>
                      <p
                        className={`text-3xl font-bold ${rateColor(ev.mean_reward_no_skills)}`}
                      >
                        {ev.mean_reward_no_skills != null
                          ? `${(ev.mean_reward_no_skills * 100).toFixed(1)}%`
                          : "—"}
                      </p>
                      <p className="mt-1 text-[11px] text-text-muted">
                        baseline
                      </p>
                    </div>
                  </div>

                  {/* Selected tasks */}
                  {ev.selected_tasks?.length > 0 && (
                    <div>
                      <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wider text-text-muted">
                        Tasks
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {ev.selected_tasks.map((t) => (
                          <span
                            key={t}
                            className="rounded bg-surface px-2 py-0.5 text-[11px] text-text-secondary"
                          >
                            {t}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Trials table */}
                  {ev.trials?.length > 0 && (
                    <div>
                      <p className="mb-2 text-[11px] font-medium uppercase tracking-wider text-text-muted">
                        Trial Results
                      </p>
                      <div className="overflow-x-auto rounded-lg border border-border/40">
                        <table className="w-full text-xs">
                          <thead className="bg-surface/60">
                            <tr className="text-left text-text-muted">
                              <th className="px-3 py-2 font-medium">Task</th>
                              <th className="px-3 py-2 font-medium">Reward</th>
                              <th className="px-3 py-2 font-medium">
                                Duration
                              </th>
                              <th className="px-3 py-2 font-medium">
                                Input Tokens
                              </th>
                              <th className="px-3 py-2 font-medium">
                                Output Tokens
                              </th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border/20">
                            {ev.trials.map((t) => {
                              const reward = Number(t.reward);
                              const rewardColor =
                                reward >= 1
                                  ? "text-emerald-400"
                                  : reward > 0
                                    ? "text-yellow-400"
                                    : "text-red-400";
                              return (
                                <tr
                                  key={t.trial_name}
                                  className="hover:bg-surface/30 transition-colors"
                                >
                                  <td className="px-3 py-2 text-text-secondary">
                                    {t.task_name}
                                  </td>
                                  <td
                                    className={`px-3 py-2 font-semibold ${rewardColor}`}
                                  >
                                    {reward.toFixed(1)}
                                  </td>
                                  <td className="px-3 py-2 text-text-muted">
                                    {Number(t.duration_sec).toFixed(1)}s
                                  </td>
                                  <td className="px-3 py-2 text-text-muted">
                                    {Number(t.n_input_tokens).toLocaleString()}
                                  </td>
                                  <td className="px-3 py-2 text-text-muted">
                                    {Number(t.n_output_tokens).toLocaleString()}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function RunDetail({
  run,
  agent,
  agentSkillMap,
  skillEvals,
  onViewSkillEvals,
}) {
  const agentEntry = agentSkillMap?.[run.agent_id];
  const skillDetails = agentEntry?.skill_details ?? [];
  // For each skill, find the latest eval result by matching skill name
  const skillRows = skillDetails.map((s) => {
    const latest = skillEvals.find((e) => e.skill_name === s.name);
    return { name: s.name, rate: latest?.mean_reward ?? null };
  });

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
                {run.task_success?.passed}/{run.task_success?.total} queries
                resolved
              </p>
            </MetricCard>

            <MetricCard icon={ListChecks} label="Workflow Completion">
              <RateBar rate={run.step_success?.rate} />
              <p className="mt-1.5 text-right text-xs text-text-muted">
                {run.step_success?.passed}/{run.step_success?.total} steps
                completed
              </p>
            </MetricCard>

            <MetricCard
              icon={Layers}
              label="Financial Skill Proficiency"
              onViewDetails={onViewSkillEvals}
            >
              {skillRows.length > 0 ? (
                <div className="space-y-2.5">
                  {skillRows.map((s) => (
                    <div key={s.name}>
                      <div className="mb-0.5 flex items-center justify-between">
                        <span className="text-xs text-text-muted">
                          {s.name}
                        </span>
                        <span className="text-xs text-text-muted">
                          {s.rate != null
                            ? `${(s.rate * 100).toFixed(1)}%`
                            : "—"}
                        </span>
                      </div>
                      <RateBar rate={s.rate} />
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-text-muted">No skills mapped</p>
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
                      {run.hallucination?.hallucinated} /{" "}
                      {run.hallucination?.total_claims} claims flagged
                    </p>
                  </div>
                  <HallucinationBadge rate={run.hallucination?.rate} />
                </div>
              </MetricCard>
            </div>
          </div>

          <div className="text-xs text-text-muted">
            <span className="font-medium text-text-secondary">Run ID:</span>{" "}
            <code className="rounded bg-surface px-1.5 py-0.5 text-accent-teal">
              {run.run_id}
            </code>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function EvaluationView({
  agentMap = {},
  focusAgentId,
  onClearFocus,
}) {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedAgentId, setSelectedAgentId] = useState(null);
  const [search, setSearch] = useState("");
  const [skillEvals, setSkillEvals] = useState([]);
  const [showSkillEvals, setShowSkillEvals] = useState(false);
  const [agentSkills, setAgentSkills] = useState({});

  useEffect(() => {
    let cancelled = false;
    fetchEvaluations()
      .then((data) => {
        if (!cancelled) {
          setRuns(data);
          setSelectedAgentId(
            (prev) => prev ?? (data.length > 0 ? data[0].agent_id : null),
          );
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchSkillEvals()
      .then((data) => {
        if (!cancelled) setSkillEvals(data);
      })
      .catch(() => {});
    fetchAgentSkills()
      .then((data) => {
        if (!cancelled) setAgentSkills(data);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (focusAgentId && runs.length > 0) {
      const match = runs.find((r) => r.agent_id === focusAgentId);
      if (match) {
        const selectTimer = setTimeout(() => setSelectedAgentId(focusAgentId), 0);
        const clearTimer = setTimeout(() => onClearFocus?.(), 1000);
        return () => {
          clearTimeout(selectTimer);
          clearTimeout(clearTimer);
        };
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
          <p className="text-sm font-medium text-text-primary">
            No evaluation runs yet
          </p>
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
              <h2 className="text-sm font-semibold text-text-primary">
                Evaluations
              </h2>
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
        {showSkillEvals ? (
          <SkillEvalsPage
            skillEvals={skillEvals.filter((e) => {
              const names =
                agentSkills[selectedAgentId]?.skill_details?.map(
                  (s) => s.name,
                ) ?? [];
              return names.length === 0 || names.includes(e.skill_name);
            })}
            onSkillEvalsUpdate={setSkillEvals}
            onBack={() => setShowSkillEvals(false)}
            agentId={selectedAgentId}
          />
        ) : selectedRun ? (
          <RunDetail
            key={selectedRun.run_id}
            run={selectedRun}
            agent={agentMap[selectedRun.agent_id]}
            agentSkillMap={agentSkills}
            skillEvals={skillEvals}
            onViewSkillEvals={() => setShowSkillEvals(true)}
          />
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center">
            <BarChart3 size={40} className="text-text-muted" />
            <div>
              <p className="text-sm font-medium text-text-primary">
                Select an agent
              </p>
              <p className="mt-1 text-xs text-text-muted">
                Choose a digital employee from the list to view evaluation
                results.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
