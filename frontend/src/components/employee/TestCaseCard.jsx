import {
  ChevronDown,
  ChevronRight,
  Loader2,
  Play,
  Sparkles,
  Trash2,
} from "lucide-react";
import { useMemo, useState } from "react";

function VerdictPill({ run }) {
  const verdict = run?.verdict;
  if (verdict === "pass") return <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs text-emerald-400">pass</span>;
  if (verdict === "fail") return <span className="rounded-full bg-red-500/15 px-2 py-0.5 text-xs text-red-400">fail</span>;
  if (verdict === "error" || verdict === "timeout") return <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-xs text-amber-400">{verdict}</span>;
  return <span className="rounded-full bg-surface px-2 py-0.5 text-xs text-text-muted">unrun</span>;
}

export default function TestCaseCard({
  testCase,
  latestRun,
  runLoading,
  availableSkills = [],
  onRun,
  onDelete,
  onUpdate,
  onOpenRun,
}) {
  const [expanded, setExpanded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({
    title: testCase.title,
    prompt: testCase.prompt,
    success_criteria: testCase.success_criteria,
    // Empty string in the form means "no linked skill"; we send "" to
    // the backend on save so it explicitly clears the column.
    skill_id: testCase.skill_id || "",
  });

  const snippet = useMemo(() => (testCase.prompt || "").slice(0, 120), [testCase.prompt]);

  const linkedSkillLabel = useMemo(() => {
    if (testCase.skill_name) return testCase.skill_name;
    if (testCase.skill_slug) return testCase.skill_slug;
    if (!testCase.skill_id) return null;
    const match = availableSkills.find(
      (s) => s.id === testCase.skill_id || s.slug === testCase.skill_id,
    );
    return match?.name || match?.display_name || match?.slug || testCase.skill_id;
  }, [
    testCase.skill_id,
    testCase.skill_name,
    testCase.skill_slug,
    availableSkills,
  ]);

  return (
    <div className="rounded-xl border border-border/40 bg-surface">
      <button
        type="button"
        className="flex w-full items-start justify-between gap-3 p-4 text-left"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-text-primary">{testCase.title}</p>
          <p className="mt-1 text-xs text-text-muted">{snippet}{testCase.prompt?.length > 120 ? "..." : ""}</p>
        </div>
        <div className="flex items-center gap-2">
          <VerdictPill run={latestRun} />
          {expanded ? <ChevronDown size={16} className="text-text-muted" /> : <ChevronRight size={16} className="text-text-muted" />}
        </div>
      </button>

      {expanded ? (
        <div className="space-y-3 border-t border-border/30 p-4">
          {editing ? (
            <div className="space-y-2">
              <input
                className="w-full rounded border border-border/50 bg-workspace px-3 py-2 text-sm"
                value={draft.title}
                onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))}
              />
              <textarea
                className="h-24 w-full rounded border border-border/50 bg-workspace px-3 py-2 text-sm"
                value={draft.prompt}
                onChange={(e) => setDraft((d) => ({ ...d, prompt: e.target.value }))}
              />
              <textarea
                className="h-20 w-full rounded border border-border/50 bg-workspace px-3 py-2 text-sm"
                value={draft.success_criteria}
                onChange={(e) => setDraft((d) => ({ ...d, success_criteria: e.target.value }))}
              />
              <label className="flex flex-col gap-1 text-xs text-text-muted">
                <span className="font-medium text-text-secondary">
                  Target skill (optional)
                </span>
                <select
                  className="rounded border border-border/50 bg-workspace px-3 py-2 text-sm"
                  value={draft.skill_id || ""}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, skill_id: e.target.value }))
                  }
                >
                  <option value="">— None —</option>
                  {availableSkills.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name || s.display_name || s.slug}
                    </option>
                  ))}
                </select>
                <span className="text-[11px] text-text-muted">
                  Pick a skill to score per-step workflow adherence in the LLM
                  judge.
                </span>
              </label>
              <div className="flex gap-2">
                <button
                  type="button"
                  className="rounded-lg bg-accent-teal px-3 py-1.5 text-xs font-medium text-workspace"
                  onClick={async () => {
                    await onUpdate(testCase.id, draft);
                    setEditing(false);
                  }}
                >
                  Save
                </button>
                <button type="button" className="rounded-lg border border-border/60 px-3 py-1.5 text-xs" onClick={() => setEditing(false)}>
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <>
              <p className="whitespace-pre-wrap text-xs text-text-secondary">{testCase.prompt}</p>
              <p className="text-xs text-text-muted">
                <span className="font-medium text-text-secondary">Success criteria:</span> {testCase.success_criteria}
              </p>
              {linkedSkillLabel ? (
                <p className="inline-flex items-center gap-1 rounded-md bg-accent-teal/10 px-2 py-0.5 text-[11px] font-medium text-accent-teal">
                  <Sparkles size={10} />
                  Skill: {linkedSkillLabel}
                </p>
              ) : null}
              {latestRun?.judge_rationale ? (
                <p className="rounded bg-accent-teal/10 px-2 py-1 text-xs text-text-secondary">
                  {latestRun.judge_rationale}
                </p>
              ) : null}
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="inline-flex items-center gap-1 rounded-lg bg-accent-teal px-3 py-1.5 text-xs font-medium text-workspace"
                  onClick={() => onRun(testCase.id)}
                  disabled={runLoading}
                >
                  {runLoading ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
                  Run
                </button>
                <button type="button" className="rounded-lg border border-border/60 px-3 py-1.5 text-xs" onClick={() => setEditing(true)}>
                  Edit
                </button>
                <button type="button" className="inline-flex items-center gap-1 rounded-lg border border-red-500/40 px-3 py-1.5 text-xs text-red-400" onClick={() => onDelete(testCase.id)}>
                  <Trash2 size={12} />
                  Delete
                </button>
                {latestRun ? (
                  <button type="button" className="rounded-lg border border-border/60 px-3 py-1.5 text-xs" onClick={() => onOpenRun(latestRun)}>
                    View run details
                  </button>
                ) : null}
              </div>
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}
