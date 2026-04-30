import {
  AlertCircle,
  Bot,
  ChevronDown,
  ChevronRight,
  Eye,
  Loader2,
  ListTree,
  MessageSquare,
  PanelRightClose,
  ScrollText,
  Sparkles,
  Terminal,
  User,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { fetchSkillWorkflow, fetchTestCaseRunEvents } from "../../services/api";
import WorkflowTree from "../workflow/WorkflowTree";
import { formatRate } from "../workflow/workflowScore";

export default function TestCaseRunEventsDrawer({
  employeeId,
  caseId,
  runId,
  run = null,
  testCase = null,
  onClose,
}) {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [workflow, setWorkflow] = useState(null);
  const [workflowLoading, setWorkflowLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("trajectory");

  useEffect(() => {
    if (!runId) return undefined;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);

    fetchTestCaseRunEvents(employeeId, caseId, runId)
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || "Failed to load run events");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [employeeId, caseId, runId]);

  const skillId = testCase?.skill_id || null;
  const alignment = run?.workflow_alignment || null;

  useEffect(() => {
    if (!alignment || !skillId) {
      setWorkflow(null);
      return undefined;
    }
    let cancelled = false;
    setWorkflowLoading(true);
    fetchSkillWorkflow(skillId)
      .then((wf) => {
        if (!cancelled) setWorkflow(wf);
      })
      .catch(() => {
        if (!cancelled) setWorkflow(null);
      })
      .finally(() => {
        if (!cancelled) setWorkflowLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [skillId, alignment]);

  // When alignment data lands, surface it by switching to the workflow
  // tab so the user sees the new view immediately. Default back to
  // trajectory if alignment goes away (run without a linked skill).
  useEffect(() => {
    setActiveTab(alignment ? "workflow" : "trajectory");
  }, [alignment, runId]);

  const completion = run?.workflow_completion || null;

  const completionLabel = useMemo(() => {
    if (!completion || completion.total === 0) return null;
    return `Workflow: ${completion.passed}/${completion.total} · ${formatRate(
      completion.rate,
    )}`;
  }, [completion]);

  if (!runId) return null;

  const available = data?.available !== false;
  const transcript = data?.transcript || "";
  const sections = available && transcript ? parseTranscript(transcript) : [];
  const showWorkflowTab = Boolean(alignment);

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/50 backdrop-blur-[1px]">
      <button
        type="button"
        onClick={onClose}
        className="flex-1 cursor-default"
        aria-label="Close events drawer"
      />
      <div className="flex h-full w-full max-w-3xl flex-col border-l border-border/40 bg-workspace shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b border-border/30 px-6 py-5">
          <div className="min-w-0">
            <div className="mb-2 flex items-center gap-2">
              <ScrollText size={16} className="text-accent-teal" />
              <h2 className="text-base font-semibold text-text-primary">
                Agent trajectory
              </h2>
              {completionLabel ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-accent-teal/10 px-2 py-0.5 text-[11px] font-medium text-accent-teal">
                  <Sparkles size={11} />
                  {completionLabel}
                </span>
              ) : null}
            </div>
            <p className="text-xs text-text-muted">
              Step-by-step reasoning and actions from this auto-test run.
              {sections.length > 0
                ? ` ${sections.length} step${sections.length === 1 ? "" : "s"}.`
                : ""}
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

        {showWorkflowTab ? (
          <div className="flex gap-2 border-b border-border/20 px-6 py-3">
            <TabButton
              active={activeTab === "workflow"}
              icon={ListTree}
              label="Workflow adherence"
              onClick={() => setActiveTab("workflow")}
            />
            <TabButton
              active={activeTab === "trajectory"}
              icon={ScrollText}
              label="Trajectory"
              onClick={() => setActiveTab("trajectory")}
            />
          </div>
        ) : null}

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

          {!loading && !error && showWorkflowTab && activeTab === "workflow" ? (
            <div className="space-y-3">
              {workflowLoading ? (
                <div className="flex items-center gap-2 text-xs text-text-muted">
                  <Loader2 size={14} className="animate-spin" />
                  Loading expected workflow…
                </div>
              ) : workflow ? (
                <WorkflowTree
                  nodes={workflow.root_steps || []}
                  mode="alignment"
                  alignment={alignment}
                  emptyMessage="The expected workflow for this skill has no steps."
                />
              ) : (
                <div className="rounded-xl border border-border/40 bg-[#2a2c31] px-5 py-6 text-sm text-text-muted">
                  Could not load the expected workflow for the linked skill.
                  The judge graded against an internal copy of the workflow,
                  but it is not available for display here.
                </div>
              )}
            </div>
          ) : null}

          {!loading && !error && (!showWorkflowTab || activeTab === "trajectory") ? (
            <>
              {!available ? (
                <div className="rounded-xl border border-border/40 bg-[#2a2c31] px-5 py-6">
                  <div className="mb-2 flex items-center gap-2 text-text-primary">
                    <AlertCircle size={16} className="text-yellow-400" />
                    <p className="font-medium">Trajectory unavailable</p>
                  </div>
                  <p className="text-sm text-text-muted">
                    No trajectory is in memory for this run. Trajectories are
                    kept only until the server restarts; re-run the test case to
                    capture a fresh one.
                  </p>
                </div>
              ) : sections.length === 0 ? (
                <div className="rounded-xl border border-border/40 bg-[#2a2c31] px-5 py-6 text-sm text-text-muted">
                  The agent did not produce any trajectory steps during this
                  run.
                </div>
              ) : (
                <div className="space-y-2">
                  {sections.map((section, i) => (
                    <TrajectorySection key={i} section={section} index={i} />
                  ))}
                </div>
              )}
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function TabButton({ active, icon, label, onClick }) {
  const Icon = icon;
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
        active
          ? "bg-accent-teal text-charcoal"
          : "bg-surface text-text-secondary hover:text-text-primary"
      }`}
    >
      <Icon size={12} />
      {label}
    </button>
  );
}

const SECTION_STYLES = {
  action: {
    icon: Terminal,
    iconColor: "text-blue-400",
    pillBg: "bg-blue-500/10",
    pillText: "text-blue-400",
    label: "ACTION",
  },
  reasoning: {
    icon: Bot,
    iconColor: "text-purple-400",
    pillBg: "bg-purple-500/10",
    pillText: "text-purple-400",
    label: "REASONING",
  },
  observation: {
    icon: Eye,
    iconColor: "text-amber-400",
    pillBg: "bg-amber-500/10",
    pillText: "text-amber-400",
    label: "OBSERVATION",
  },
  message: {
    icon: MessageSquare,
    iconColor: "text-accent-teal",
    pillBg: "bg-accent-teal/10",
    pillText: "text-accent-teal",
    label: "MESSAGE",
  },
  user: {
    icon: User,
    iconColor: "text-text-muted",
    pillBg: "bg-workspace",
    pillText: "text-text-secondary",
    label: "USER",
  },
  error: {
    icon: XCircle,
    iconColor: "text-red-400",
    pillBg: "bg-red-500/10",
    pillText: "text-red-400",
    label: "ERROR",
  },
};

function TrajectorySection({ section, index }) {
  const style = SECTION_STYLES[section.type] || SECTION_STYLES.message;
  const Icon = style.icon;

  // Observation sections are collapsed by default (they can be very long)
  const [expanded, setExpanded] = useState(section.type !== "observation");

  const hasBody = section.body && section.body.trim().length > 0;

  return (
    <div className="rounded-xl border border-border/40 bg-surface px-4 py-3">
      <div className="flex items-start gap-2">
        <Icon size={14} className={`mt-0.5 shrink-0 ${style.iconColor}`} />
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-2 text-xs">
            <span className="font-mono text-text-muted">#{index + 1}</span>
            <span
              className={`rounded-md px-2 py-0.5 font-medium ${style.pillBg} ${style.pillText}`}
            >
              {style.label}
            </span>
            {section.turn ? (
              <span className="text-text-muted">Turn {section.turn}</span>
            ) : null}
            {section.toolName ? (
              <span className="rounded-md bg-workspace px-2 py-0.5 font-mono text-text-secondary">
                {section.toolName}
              </span>
            ) : null}
            {section.role ? (
              <span className="text-text-muted">{section.role}</span>
            ) : null}
          </div>

          {section.headline ? (
            <p className="mb-1 text-xs font-medium text-text-primary">
              {section.headline}
            </p>
          ) : null}

          {hasBody ? (
            <>
              {section.type === "observation" ? (
                <button
                  type="button"
                  onClick={() => setExpanded((prev) => !prev)}
                  className="mb-1 inline-flex items-center gap-1 text-[11px] font-medium text-text-muted transition-colors hover:text-text-primary"
                >
                  {expanded ? (
                    <ChevronDown size={12} />
                  ) : (
                    <ChevronRight size={12} />
                  )}
                  {expanded ? "Hide output" : "Show output"}
                </button>
              ) : null}

              {expanded ? (
                <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-border/30 bg-workspace px-3 py-2 text-[11px] leading-relaxed text-text-secondary">
                  {section.body}
                </pre>
              ) : null}
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function parseTranscript(text) {
  const sections = [];
  const lines = text.split("\n");
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // [Turn N] [ACTION] tool_name
    const actionMatch = line.match(/^\[Turn (\d+)\] \[ACTION\] (.+)$/);
    if (actionMatch) {
      const turn = actionMatch[1];
      const toolName = actionMatch[2];
      let args = "";
      let reasoning = "";
      let j = i + 1;
      while (j < lines.length && /^  /.test(lines[j])) {
        const stripped = lines[j].replace(/^  /, "");
        if (stripped.startsWith("[Agent reasoning] ")) {
          reasoning = stripped.replace("[Agent reasoning] ", "");
        } else if (stripped.startsWith("Arguments: ")) {
          args = stripped.replace("Arguments: ", "");
        }
        j++;
      }
      const bodyParts = [];
      if (args) bodyParts.push(args);
      sections.push({
        type: "action",
        turn,
        toolName,
        headline: null,
        body: bodyParts.join("\n") || null,
      });
      if (reasoning) {
        sections.push({
          type: "reasoning",
          turn: null,
          toolName: null,
          headline: null,
          body: reasoning,
        });
      }
      i = j;
      continue;
    }

    // [OBSERVATION] tool_name: content
    const obsMatch = line.match(/^\[OBSERVATION\](?: (.+?):)? ?(.*)$/);
    if (obsMatch) {
      const toolName = obsMatch[1] || null;
      let content = obsMatch[2] || "";
      let j = i + 1;
      while (j < lines.length && /^  /.test(lines[j])) {
        content += "\n" + lines[j].replace(/^  /, "");
        j++;
      }
      sections.push({
        type: "observation",
        turn: null,
        toolName,
        headline: null,
        body: content.trim() || null,
      });
      i = j;
      continue;
    }

    // [ERROR] message
    const errorMatch = line.match(/^\[ERROR\] (.+)$/);
    if (errorMatch) {
      sections.push({
        type: "error",
        turn: null,
        toolName: null,
        headline: null,
        body: errorMatch[1],
      });
      i++;
      continue;
    }

    // [ROLE] text  (e.g. [USER], [ASSISTANT])
    const roleMatch = line.match(/^\[([A-Z]+)\] (.+)$/);
    if (roleMatch) {
      const role = roleMatch[1];
      const content = roleMatch[2];
      const isUser = role === "USER";
      sections.push({
        type: isUser ? "user" : "message",
        turn: null,
        toolName: null,
        role,
        headline: null,
        body: content,
      });
      i++;
      continue;
    }

    i++;
  }

  return sections;
}
