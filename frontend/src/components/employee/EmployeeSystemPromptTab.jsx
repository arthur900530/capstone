import { useEffect, useState } from "react";
import { Loader2, Pencil, Sparkles } from "lucide-react";
import ConfirmDialog from "../skills/ConfirmDialog";
import { updateEmployee } from "../../services/employeeStore";

// Label + confirm-dialog copy is keyed by which block the user is editing so
// we only render one dialog instance rather than two duplicated-looking ones.
const FIELD_META = {
  description: {
    label: "Description",
    helper:
      "Your original short hint. Editing this does not regenerate the system prompt — it's purely a note to yourself.",
    confirmTitle: "Edit description?",
    confirmMessage:
      "Changing the description is safe — it won't regenerate the system prompt. You can still edit the prompt separately.",
  },
  task: {
    label: "System Prompt",
    helper:
      "Controls how this employee thinks and responds. Edit carefully — this text is passed to the model on every turn.",
    confirmTitle: "Edit system prompt?",
    confirmMessage:
      "Changing this will affect how your employee responds. Are you sure?",
  },
};

export default function EmployeeSystemPromptTab({ employee, onUpdated }) {
  const [editing, setEditing] = useState(null); // "description" | "task" | null
  const [pending, setPending] = useState(null); // same, while ConfirmDialog open
  const [draft, setDraft] = useState({
    description: employee?.description || "",
    task: employee?.task || "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  // Sync drafts when the parent fetches a fresh employee — but only refresh
  // the field that isn't currently being edited. Otherwise an external save
  // (or a sibling block's save triggering a parent refresh) wipes the user's
  // in-progress textarea content.
  useEffect(() => {
    setDraft((d) => ({
      description:
        editing === "description" ? d.description : employee?.description || "",
      task: editing === "task" ? d.task : employee?.task || "",
    }));
  }, [employee?.id, employee?.description, employee?.task, editing]);

  const beginEdit = (field) => {
    setError(null);
    setPending(field);
  };

  const confirmEdit = () => {
    if (!pending) return;
    setEditing(pending);
    setDraft((d) => ({
      ...d,
      [pending]: employee?.[pending] || "",
    }));
    setPending(null);
  };

  const cancelConfirm = () => setPending(null);

  const cancelEdit = () => {
    // Reset only the block being cancelled so the other block's in-progress
    // draft (if any) stays intact.
    const field = editing;
    setEditing(null);
    setError(null);
    if (field) {
      setDraft((d) => ({ ...d, [field]: employee?.[field] || "" }));
    }
  };

  const save = async (field) => {
    setSaving(true);
    setError(null);
    try {
      const updated = await updateEmployee(employee.id, {
        [field]: draft[field],
      });
      if (!updated) {
        throw new Error("Save failed — server rejected the update.");
      }
      setEditing(null);
      onUpdated?.(updated);
    } catch (err) {
      setError(err?.message || "Failed to save. Try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mx-auto flex max-w-5xl flex-1 flex-col overflow-y-auto px-6 py-6">
      <div className="mb-5">
        <h3 className="text-sm font-semibold text-text-primary">
          System Prompt
        </h3>
        <p className="mt-1 text-xs text-text-muted">
          The system prompt controls how this employee thinks and responds.
          Edit carefully — changes take effect immediately in new chat turns.
        </p>
      </div>

      <PromptBlock
        field="description"
        value={employee?.description || ""}
        draft={draft.description}
        editing={editing === "description"}
        saving={saving && editing === "description"}
        error={editing === "description" ? error : null}
        onBeginEdit={() => beginEdit("description")}
        onChange={(v) => setDraft((d) => ({ ...d, description: v }))}
        onSave={() => save("description")}
        onCancel={cancelEdit}
      />

      <div className="h-5" />

      <PromptBlock
        field="task"
        value={employee?.task || ""}
        draft={draft.task}
        editing={editing === "task"}
        saving={saving && editing === "task"}
        error={editing === "task" ? error : null}
        onBeginEdit={() => beginEdit("task")}
        onChange={(v) => setDraft((d) => ({ ...d, task: v }))}
        onSave={() => save("task")}
        onCancel={cancelEdit}
      />

      <ConfirmDialog
        open={pending !== null}
        title={pending ? FIELD_META[pending].confirmTitle : ""}
        message={pending ? FIELD_META[pending].confirmMessage : ""}
        confirmLabel="Yes, edit"
        confirmColor="teal"
        onConfirm={confirmEdit}
        onCancel={cancelConfirm}
      />
    </div>
  );
}

function PromptBlock({
  field,
  value,
  draft,
  editing,
  saving,
  error,
  onBeginEdit,
  onChange,
  onSave,
  onCancel,
}) {
  const meta = FIELD_META[field];
  const isPrompt = field === "task";
  const textareaRows = isPrompt ? 16 : 4;
  const displayValue = value || (
    <span className="italic text-text-muted">
      {isPrompt
        ? "No system prompt yet — this employee was created before prompt expansion was available."
        : "No description recorded."}
    </span>
  );

  return (
    <section className="rounded-xl border border-border/40 bg-surface">
      <header className="flex items-start justify-between gap-3 border-b border-border/30 px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            {isPrompt ? (
              <Sparkles size={14} className="shrink-0 text-accent-teal" />
            ) : null}
            <h4 className="text-sm font-semibold text-text-primary">
              {meta.label}
            </h4>
          </div>
          <p className="mt-1 text-[11px] text-text-muted">{meta.helper}</p>
        </div>
        {!editing && (
          <button
            onClick={onBeginEdit}
            className="flex shrink-0 items-center gap-1.5 rounded-md border border-border/40 bg-workspace px-2.5 py-1 text-[11px] font-medium text-text-secondary transition-colors hover:border-accent-teal/60 hover:text-accent-teal"
          >
            <Pencil size={11} />
            Edit
          </button>
        )}
      </header>

      <div className="px-4 py-3">
        {editing ? (
          <>
            <textarea
              autoFocus
              rows={textareaRows}
              value={draft}
              onChange={(e) => onChange(e.target.value)}
              disabled={saving}
              className="w-full resize-y rounded-lg border border-border/40 bg-workspace px-3 py-2 font-mono text-xs leading-relaxed text-text-primary placeholder:text-text-muted/60 focus:border-accent-teal/50 focus:outline-none focus:ring-1 focus:ring-accent-teal/30 disabled:opacity-60"
            />
            {error && (
              <div className="mt-2 rounded-md border border-red-500/40 bg-red-500/10 px-2.5 py-1.5 text-[11px] text-red-400">
                {error}
              </div>
            )}
            <div className="mt-3 flex items-center justify-end gap-2">
              <button
                onClick={onCancel}
                disabled={saving}
                className="rounded-md px-3 py-1.5 text-xs text-text-secondary transition-colors hover:bg-surface-hover hover:text-text-primary disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={onSave}
                disabled={saving}
                className="flex items-center gap-1.5 rounded-md bg-accent-teal px-3 py-1.5 text-xs font-medium text-workspace transition-colors hover:bg-accent-teal/90 disabled:opacity-50"
              >
                {saving && <Loader2 size={12} className="animate-spin" />}
                {saving ? "Saving…" : "Save"}
              </button>
            </div>
          </>
        ) : (
          <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-text-secondary">
            {displayValue}
          </pre>
        )}
      </div>
    </section>
  );
}
