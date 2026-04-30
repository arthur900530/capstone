import { createElement, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  BarChart3,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Circle,
  CircleDot,
  GitCompareArrows,
  ListTree,
  Loader2,
  PanelRightClose,
  Rows3,
  ScrollText,
  Sparkles,
  XCircle,
} from "lucide-react";
import {
  alignTaskTrajectoryWithWorkflow,
  annotateTaskTrajectory,
  fetchSkills,
  fetchTaskTrajectory,
} from "../../services/api";
import TrajectoryNodeCard from "./TrajectoryNodeCard";
import WorkflowTree from "../workflow/WorkflowTree";
import { formatRate } from "../workflow/workflowScore";

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

// Adapt a SequenceNode/ActionNode tree (from /trajectory) into the
// {title, description, start_time, end_time, children} shape that
// WorkflowTree renders. Used for the hierarchical view so the
// trajectory drawer and workflow-review drawer share one visual idiom.
function trajectoryTreeToWorkflowNodes(tree) {
  if (!tree) return [];
  const startMs = earliestActionMs(tree);
  return [adaptTrajectoryNode(tree, startMs)];
}

function earliestActionMs(node) {
  if (!node) return null;
  if (node.node_type === "action") {
    const t = Date.parse(node?.time?.before || "");
    return Number.isNaN(t) ? null : t;
  }
  let earliest = null;
  for (const child of node.nodes || []) {
    const m = earliestActionMs(child);
    if (m !== null && (earliest === null || m < earliest)) earliest = m;
  }
  return earliest;
}

function relativeSeconds(iso, baseMs) {
  const t = Date.parse(iso || "");
  if (Number.isNaN(t) || baseMs === null) return null;
  return Math.max(0, (t - baseMs) / 1000);
}

function adaptTrajectoryNode(node, baseMs) {
  if (!node) return null;
  if (node.node_type === "action") {
    const tool = node?.state?.extra?.category || node?.state?.extra?.event_type;
    const description = [node.goal, tool ? `(${tool})` : null]
      .filter(Boolean)
      .join(" ");
    return {
      title: node.action || "Action",
      description,
      start_time: relativeSeconds(node?.time?.before, baseMs),
      end_time: relativeSeconds(node?.time?.after, baseMs),
      children: [],
    };
  }
  const children = (node.nodes || [])
    .map((c) => adaptTrajectoryNode(c, baseMs))
    .filter(Boolean);
  return {
    title: node.goal || "Sequence",
    description: node.status_reason || "",
    start_time: null,
    end_time: null,
    children,
  };
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

function ViewButton({ active, icon, label, onClick }) {
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
      {createElement(icon, { size: 14 })}
      {label}
    </button>
  );
}

function SequenceStatusBadge({ status }) {
  if (status === "success") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-emerald-300">
        <CheckCircle2 size={12} />
        achieved
      </span>
    );
  }
  if (status === "failure") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-red-500/40 bg-red-500/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-red-300">
        <XCircle size={12} />
        not achieved
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-border/50 bg-surface px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-text-muted">
      unknown
    </span>
  );
}

function TreeNode({ node, depth = 0, processed = false }) {
  const [open, setOpen] = useState(depth < 2);

  if (!node) return null;
  if (node.node_type === "action") {
    return <TrajectoryNodeCard node={node} />;
  }

  const llm = processed ? node.llm : null;
  const displayGoal = (llm?.goal || node.goal || "Sequence").trim();
  const displayStatus = llm?.status || node.status || "unknown";
  const showLlmAccent = processed && Boolean(llm?.goal);

  return (
    <div className="space-y-3">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className={`flex w-full items-center justify-between rounded-xl border px-4 py-3 text-left transition-colors ${
          showLlmAccent
            ? "border-accent-teal/40 bg-accent-teal/[0.04]"
            : "border-border/50 bg-[#2a2c31]"
        }`}
      >
        <div className="min-w-0">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            {showLlmAccent ? (
              <span className="inline-flex items-center gap-1 rounded-full border border-accent-teal/40 bg-accent-teal/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-accent-teal">
                <Sparkles size={10} />
                LLM goal
              </span>
            ) : null}
            <SequenceStatusBadge status={displayStatus} />
            <span className="text-[10px] uppercase tracking-wider text-text-muted">
              {(node.nodes || []).length} item{(node.nodes || []).length !== 1 ? "s" : ""}
            </span>
          </div>
          <p className="text-sm font-semibold text-text-primary break-words">
            {displayGoal}
          </p>
          {llm?.status_reason ? (
            <p className="mt-1 text-xs text-text-muted break-words">
              {llm.status_reason}
            </p>
          ) : null}
        </div>
        <div className="ml-3 shrink-0 text-text-muted">
          {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </div>
      </button>
      {open ? (
        <div className="ml-4 space-y-3 border-l border-border/40 pl-4">
          {(node.nodes || []).map((child, index) => (
            <TreeNode
              key={`${child.node_type}-${index}`}
              node={child}
              depth={depth + 1}
              processed={processed}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

export default function TaskTrajectoryDrawer({ employeeId, task, onClose, onAnnotated }) {
  // Workflow view is the default so the user lands directly on the
  // alignment-driven success view. Cached alignments (rehydrated from
  // the trajectory GET below) populate the picker automatically; if no
  // alignment exists yet, the tab still renders an empty-state CTA.
  const [view, setView] = useState("workflow");
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [annotating, setAnnotating] = useState(false);
  const [annotationError, setAnnotationError] = useState(null);
  // Workflow comparison state. The user picks a skill from `skills`,
  // clicks Align, and the backend runs the LLM-driven mapping. The result
  // (workflow + per-action assignments + per-leaf-step alignment) lives
  // in `alignment` and drives the new "Workflow" view.
  //
  // `cachedAligns` is the keyed-by-skill_id map of alignments the backend
  // has previously persisted for this task run. We hydrate it on drawer
  // open from the trajectory GET so reopening the drawer restores prior
  // workflow comparisons without re-paying the LLM. Fresh alignments
  // computed in this session are merged into the same map so re-picking
  // the same skill in the dropdown is instant.
  const [skills, setSkills] = useState([]);
  const [selectedSkillId, setSelectedSkillId] = useState("");
  const [alignment, setAlignment] = useState(null);
  const [aligning, setAligning] = useState(false);
  const [alignError, setAlignError] = useState(null);
  const [cachedAligns, setCachedAligns] = useState({});

  useEffect(() => {
    if (!task) return undefined;
    let cancelled = false;
    setView("workflow");
    setLoading(true);
    setError(null);
    setAnnotationError(null);
    setData(null);
    setAlignment(null);
    setAlignError(null);
    setSelectedSkillId("");
    setCachedAligns({});

    fetchTaskTrajectory(employeeId, task.sessionId, task.taskIndex)
      .then((result) => {
        if (cancelled) return;
        setData(result);
        // Rehydrate prior workflow alignments persisted on the task run
        // so the Workflow tab can render the result from a previous
        // session without forcing the user to re-pick + re-align.
        const aligns = Array.isArray(result?.workflow_aligns)
          ? result.workflow_aligns
          : [];
        if (aligns.length > 0) {
          const byId = {};
          for (const entry of aligns) {
            if (entry?.skill_id) byId[entry.skill_id] = { ...entry, source: "cache" };
          }
          setCachedAligns(byId);
          // Default to the highest-completion alignment so the tab
          // shows something meaningful immediately on reopen. Backend
          // already sorted descending by rate.
          const best = aligns[0];
          if (best?.skill_id) {
            setSelectedSkillId(best.skill_id);
            setAlignment({ ...best, source: "cache" });
          }
        }
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

  // Load the skill catalog once per drawer open so the picker has options.
  // We don't filter by "has workflow" here — the backend returns 404 for
  // skills without one, which the UI surfaces inline.
  useEffect(() => {
    if (!task) return undefined;
    let cancelled = false;
    fetchSkills()
      .then((all) => {
        if (!cancelled) setSkills(Array.isArray(all) ? all : []);
      })
      .catch(() => {
        if (!cancelled) setSkills([]);
      });
    return () => {
      cancelled = true;
    };
  }, [task]);

  const linearNodes = useMemo(() => flattenActions(data?.tree), [data?.tree]);
  const workflowNodes = useMemo(
    () => trajectoryTreeToWorkflowNodes(data?.tree),
    [data?.tree],
  );
  const annotated = Boolean(data?.annotated);
  const canAnnotate = data?.available !== false && Array.isArray(data?.raw_events) && data.raw_events.length > 0;

  // Index assignments by action_index so the per-action UI is O(1).
  const assignmentsByAction = useMemo(() => {
    const map = new Map();
    for (const entry of alignment?.action_assignments || []) {
      if (typeof entry?.action_index === "number") {
        map.set(entry.action_index, entry);
      }
    }
    return map;
  }, [alignment]);

  // Resolve a workflow_step_path back to its title so action chips read
  // "Step 1.2: Login" rather than a numeric path.
  const stepTitleByPath = useMemo(() => {
    const out = new Map();
    if (!alignment?.workflow?.root_steps) return out;
    const walk = (steps, prefix) => {
      steps.forEach((step, i) => {
        const path = [...prefix, i];
        out.set(path.join("."), {
          title: step?.title || "(untitled)",
          label: path.map((n) => n + 1).join("."),
        });
        if (Array.isArray(step?.children) && step.children.length > 0) {
          walk(step.children, path);
        }
      });
    };
    walk(alignment.workflow.root_steps, []);
    return out;
  }, [alignment]);

  const completion = alignment?.workflow_completion;
  const completionLabel =
    completion && completion.total > 0
      ? `Workflow: ${completion.passed}/${completion.total} · ${formatRate(completion.rate)}`
      : null;

  const handleAlign = async ({ force = false } = {}) => {
    if (!task || !selectedSkillId) return;
    setAligning(true);
    setAlignError(null);
    try {
      const result = await alignTaskTrajectoryWithWorkflow(
        employeeId,
        task.sessionId,
        task.taskIndex,
        selectedSkillId,
        { force },
      );
      setAlignment(result);
      // Mirror the freshly-computed alignment into the local cache so
      // toggling away and back to the same skill is instant, and so
      // any aggregate views the parent re-renders see what's now in
      // the DB without an extra round trip.
      if (result?.skill_id) {
        setCachedAligns((prev) => ({
          ...prev,
          [result.skill_id]: { ...result },
        }));
      }
      // Tell the parent (report card) the trajectory's annotations
      // changed so its KPIs / trend / task list re-fetch and pick up
      // the new effective_task_score / workflow_summary fields. We
      // reuse the existing onAnnotated callback because the parent
      // simply triggers a metrics refresh either way.
      if (onAnnotated) {
        Promise.resolve(
          onAnnotated({
            sessionId: task.sessionId,
            taskIndex: task.taskIndex,
            alignment: result,
          }),
        ).catch(() => {
          /* parent refresh shouldn't surface in the drawer */
        });
      }
    } catch (err) {
      setAlignError(err.message || "Failed to align with workflow");
    } finally {
      setAligning(false);
    }
  };

  const handleAnnotate = async ({ force = false } = {}) => {
    if (!task) return;
    setAnnotating(true);
    setAnnotationError(null);
    try {
      const result = await annotateTaskTrajectory(
        employeeId,
        task.sessionId,
        task.taskIndex,
        { force },
      );
      setData(result);
      setView("processed");
      // Notify the parent so any aggregated views (report card's Task
      // Performance section + trend chart) re-fetch and stay in sync with
      // what the drawer is now showing. Fire-and-forget; never blocks.
      if (onAnnotated) {
        Promise.resolve(
          onAnnotated({
            sessionId: task.sessionId,
            taskIndex: task.taskIndex,
            annotations: result?.annotations,
          }),
        ).catch(() => {
          /* parent refresh shouldn't surface in the drawer */
        });
      }
    } catch (err) {
      setAnnotationError(err.message || "Failed to annotate trajectory");
    } finally {
      setAnnotating(false);
    }
  };

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
              active={view === "workflow"}
              icon={GitCompareArrows}
              label="Workflow"
              onClick={() => setView("workflow")}
            />
            <ViewButton
              active={view === "processed"}
              icon={Sparkles}
              label={annotated ? "Processed" : "Processed (LLM)"}
              onClick={() => setView("processed")}
            />
            <ViewButton
              active={view === "hierarchical"}
              icon={ListTree}
              label="Hierarchical"
              onClick={() => setView("hierarchical")}
            />
            <ViewButton
              active={view === "linear"}
              icon={Rows3}
              label="Linear"
              onClick={() => setView("linear")}
            />
            <ViewButton
              active={view === "raw"}
              icon={ScrollText}
              label="Raw"
              onClick={() => setView("raw")}
            />
          </div>
          {view === "workflow" && completionLabel ? (
            <div className="mt-3 inline-flex items-center gap-2 rounded-full border border-accent-teal/30 bg-accent-teal/[0.08] px-3 py-1 text-xs font-medium text-accent-teal">
              <CheckCircle2 size={12} />
              {completionLabel}
            </div>
          ) : null}
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
                  <WorkflowTree
                    nodes={workflowNodes}
                    mode="trajectory"
                    emptyMessage="No trajectory steps recorded for this run."
                  />
                </div>
              ) : null}

              {view === "processed" ? (
                <div className="space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-accent-teal/20 bg-accent-teal/[0.04] px-4 py-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 text-sm font-medium text-text-primary">
                        <Sparkles size={14} className="text-accent-teal" />
                        Induced workflow
                      </div>
                      <p className="mt-1 text-xs text-text-muted">
                        {annotated
                          ? "Each sequence shows an LLM-summarized goal and whether the action sequence achieved it."
                          : "Run LLM annotation to summarize goals and judge success for each sequence node."}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      {annotated ? (
                        <button
                          type="button"
                          onClick={() => handleAnnotate({ force: true })}
                          disabled={annotating}
                          className="inline-flex items-center gap-2 rounded-lg border border-border/50 bg-surface px-3 py-2 text-xs font-medium text-text-secondary transition-colors hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          {annotating ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
                          Re-annotate
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => handleAnnotate()}
                          disabled={annotating || !canAnnotate}
                          className="inline-flex items-center gap-2 rounded-lg bg-accent-teal px-3 py-2 text-xs font-semibold text-charcoal transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          {annotating ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
                          Annotate with LLM
                        </button>
                      )}
                    </div>
                  </div>

                  {annotationError ? (
                    <div className="flex items-center gap-2 rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
                      <AlertCircle size={16} />
                      {annotationError}
                    </div>
                  ) : null}

                  {annotating && !annotated ? (
                    <div className="flex items-center gap-2 rounded-xl border border-border/40 bg-[#2a2c31] px-4 py-6 text-sm text-text-muted">
                      <Loader2 size={16} className="animate-spin text-accent-teal" />
                      Summarizing goals and judging status across the trajectory…
                    </div>
                  ) : (
                    <div className="space-y-3">
                      <TreeNode node={data?.tree} processed />
                    </div>
                  )}
                </div>
              ) : null}

              {view === "workflow" ? (
                <WorkflowComparisonView
                  skills={skills}
                  selectedSkillId={selectedSkillId}
                  onSelectSkill={(value) => {
                    setSelectedSkillId(value);
                    setAlignError(null);
                    // If we have a cached alignment for this skill
                    // (either persisted from a previous session or
                    // just computed in this one), show it immediately
                    // — no extra LLM call needed. Otherwise clear so
                    // the user sees "click Align".
                    if (value && cachedAligns[value]) {
                      setAlignment(cachedAligns[value]);
                    } else {
                      setAlignment(null);
                    }
                  }}
                  alignment={alignment}
                  aligning={aligning}
                  alignError={alignError}
                  canAlign={canAnnotate}
                  onAlign={handleAlign}
                  linearNodes={linearNodes}
                  assignmentsByAction={assignmentsByAction}
                  stepTitleByPath={stepTitleByPath}
                  cachedAligns={cachedAligns}
                />
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

// New "Workflow" tab body. Lets the user pick a skill whose workflow.json
// to compare this trajectory against, runs an LLM alignment, and renders
// the result as (a) the workflow tree with per-leaf satisfied/missed
// badges and (b) the agent's actions, each chip-tagged with the
// workflow step it most closely advanced. The existing "Processed" view
// continues to show per-sequence success the way it always has.
function WorkflowComparisonView({
  skills,
  selectedSkillId,
  onSelectSkill,
  alignment,
  aligning,
  alignError,
  canAlign,
  onAlign,
  linearNodes,
  assignmentsByAction,
  stepTitleByPath,
  cachedAligns = {},
}) {
  const hasResult = Boolean(alignment?.workflow);
  const cachedCount = Object.keys(cachedAligns || {}).length;

  // Surface skills that already have a saved alignment first in the
  // dropdown and tag them with ✓ so the user can tell at a glance which
  // workflows are already on file for this run.
  const orderedSkills = (() => {
    const aligned = [];
    const rest = [];
    for (const s of skills) {
      if (cachedAligns[s.id]) aligned.push(s);
      else rest.push(s);
    }
    return [...aligned, ...rest];
  })();

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-accent-teal/20 bg-accent-teal/[0.04] px-4 py-3">
        <div className="flex items-center gap-2 text-sm font-medium text-text-primary">
          <GitCompareArrows size={14} className="text-accent-teal" />
          Compare with workflow
        </div>
        <p className="mt-1 text-xs text-text-muted">
          Pick a skill — the LLM will map every action in this trajectory to
          a workflow step and grade each leaf step as satisfied or missed.
          {cachedCount > 0 ? (
            <>
              {" "}
              <span className="text-text-secondary">
                {cachedCount} saved alignment{cachedCount !== 1 ? "s" : ""}
                {" "}for this run.
              </span>
            </>
          ) : null}
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <select
            value={selectedSkillId}
            onChange={(e) => onSelectSkill(e.target.value)}
            className="min-w-[14rem] rounded-lg border border-border/50 bg-surface px-3 py-2 text-sm text-text-primary focus:border-accent-teal focus:outline-none"
            disabled={aligning}
          >
            <option value="">Select a skill…</option>
            {orderedSkills.map((s) => {
              const cached = cachedAligns[s.id];
              const rate = cached?.workflow_completion?.rate;
              const ratePct =
                typeof rate === "number" ? ` · ${Math.round(rate * 100)}%` : "";
              return (
                <option key={s.id} value={s.id}>
                  {cached ? "✓ " : ""}
                  {s.name || s.slug || s.id}
                  {cached ? ratePct : ""}
                </option>
              );
            })}
          </select>
          <button
            type="button"
            onClick={() => onAlign({ force: hasResult })}
            disabled={!selectedSkillId || aligning || !canAlign}
            className="inline-flex items-center gap-2 rounded-lg bg-accent-teal px-3 py-2 text-xs font-semibold text-charcoal transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {aligning ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Sparkles size={12} />
            )}
            {hasResult ? "Re-align" : "Align with LLM"}
          </button>
          {alignment?.source ? (
            <span className="text-[10px] uppercase tracking-wider text-text-muted">
              source: {alignment.source}
            </span>
          ) : null}
        </div>
      </div>

      {alignError ? (
        <div className="flex items-center gap-2 rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          <AlertCircle size={16} />
          {alignError}
        </div>
      ) : null}

      {aligning && !hasResult ? (
        <div className="flex items-center gap-2 rounded-xl border border-border/40 bg-[#2a2c31] px-4 py-6 text-sm text-text-muted">
          <Loader2 size={16} className="animate-spin text-accent-teal" />
          Mapping actions to workflow steps and grading each leaf…
        </div>
      ) : null}

      {!aligning && !hasResult && !alignError ? (
        <div className="rounded-xl border border-dashed border-border/40 bg-charcoal/30 px-4 py-6 text-center text-xs text-text-muted">
          No workflow comparison yet. Pick a skill above and click
          <span className="px-1 font-medium">Align with LLM</span>.
        </div>
      ) : null}

      {hasResult ? (
        <>
          <div className="rounded-xl border border-border/40 bg-[#2a2c31] p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="text-sm font-semibold text-text-primary">
                {alignment.workflow.title || alignment.workflow.skill_name || "Workflow"}
              </div>
              {alignment.workflow.summary ? (
                <p className="max-w-xs truncate text-xs text-text-muted">
                  {alignment.workflow.summary}
                </p>
              ) : null}
            </div>
            <WorkflowTree
              nodes={alignment.workflow.root_steps || []}
              mode="alignment"
              alignment={alignment.workflow_alignment}
              emptyMessage="This skill's workflow has no steps yet."
            />
          </div>

          <div className="space-y-2">
            <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-text-muted">
              <ListTree size={12} />
              Action → step mapping
            </div>
            {linearNodes.length === 0 ? (
              <div className="rounded-xl border border-dashed border-border/40 bg-charcoal/30 px-4 py-6 text-center text-xs text-text-muted">
                This trajectory has no recorded actions.
              </div>
            ) : (
              <div className="space-y-2">
                {linearNodes.map((node, index) => (
                  <ActionAssignmentCard
                    key={`${node.action}-${index}`}
                    index={index}
                    node={node}
                    assignment={assignmentsByAction.get(index)}
                    stepTitleByPath={stepTitleByPath}
                  />
                ))}
              </div>
            )}
          </div>
        </>
      ) : null}
    </div>
  );
}

function ActionAssignmentCard({ index, node, assignment, stepTitleByPath }) {
  const stepKey = (assignment?.workflow_step_path || []).join(".");
  const stepInfo = stepKey ? stepTitleByPath.get(stepKey) : null;
  const isUnassigned =
    !assignment ||
    !Array.isArray(assignment.workflow_step_path) ||
    assignment.workflow_step_path.length === 0;

  return (
    <div className="rounded-xl border border-border/40 bg-[#2a2c31] px-4 py-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-border/50 bg-surface px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-text-muted">
          #{index + 1}
        </span>
        {isUnassigned ? (
          <span className="inline-flex items-center gap-1 rounded-full border border-border/50 bg-surface px-2 py-0.5 text-[10px] font-medium text-text-muted">
            <Circle size={10} />
            unassigned
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 rounded-full border border-accent-teal/30 bg-accent-teal/[0.08] px-2 py-0.5 text-[10px] font-medium text-accent-teal">
            <CircleDot size={10} />
            Step {stepInfo?.label || stepKey}
            {stepInfo?.title ? `: ${stepInfo.title}` : ""}
          </span>
        )}
      </div>
      <p className="text-sm font-medium text-text-primary break-words">
        {(node.goal || node.action || "(action)").trim()}
      </p>
      {assignment?.rationale ? (
        <p className="mt-1.5 text-xs text-text-muted break-words">
          {assignment.rationale}
        </p>
      ) : null}
    </div>
  );
}

