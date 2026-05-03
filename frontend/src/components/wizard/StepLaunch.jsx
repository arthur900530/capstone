import * as Icons from "lucide-react";
import { Loader2 } from "lucide-react";
import PLUGINS from "../../data/plugins";

export default function StepLaunch({
  name,
  onNameChange,
  position,
  onPositionChange,
  description,
  pluginIds,
  skillIds,
  config,
  creating = false,
  error = null,
  onBack,
  onCreate,
}) {
  const selectedPlugins = PLUGINS.filter((p) => pluginIds.includes(p.id));
  const FirstIcon = Icons[selectedPlugins[0]?.icon] || Icons.Bot;

  return (
    <div className="mx-auto max-w-2xl">
      <h2 className="mb-2 text-xl font-semibold text-text-primary">
        Name your employee
      </h2>
      <p className="mb-6 text-sm text-text-muted">
        Give your digital employee a name and review the configuration.
      </p>

      <input
        autoFocus
        value={name}
        onChange={(e) => onNameChange(e.target.value)}
        maxLength={40}
        placeholder="e.g. Sarah"
        className="w-full rounded-xl border border-border/40 bg-surface px-4 py-3 text-lg font-medium text-text-primary placeholder:text-text-muted/60 focus:border-accent-teal/50 focus:outline-none focus:ring-1 focus:ring-accent-teal/30"
      />

      <input
        value={position || ""}
        onChange={(e) => onPositionChange?.(e.target.value)}
        maxLength={120}
        placeholder="Position (e.g. Equity Research Analyst)"
        className="mt-3 w-full rounded-xl border border-border/40 bg-surface px-4 py-3 text-sm text-text-primary placeholder:text-text-muted/60 focus:border-accent-teal/50 focus:outline-none focus:ring-1 focus:ring-accent-teal/30"
      />

      {/* Summary card */}
      <div className="mt-6 rounded-xl border border-border/40 bg-surface p-5 space-y-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent-teal/10">
            <FirstIcon size={20} className="text-accent-teal" />
          </div>
          <div>
            <p className="font-medium text-text-primary">
              {position?.trim() ||
                selectedPlugins.map((p) => p.name).join(", ") ||
                "Custom"}
            </p>
            <p className="text-xs text-text-muted">
              {/* {config.model?.split("/").pop()} */}
              {"openai/gpt-5.5-2026-04-23"}
            </p>
          </div>
        </div>

        <div>
          <p className="mb-1 text-xs font-medium text-text-muted">Description</p>
          <p className="text-sm text-text-secondary">{description}</p>
          <p className="mt-1.5 text-[11px] italic text-text-muted">
            We&apos;ll expand this into a full system prompt after you create
            your employee. You can review and edit it from the System Prompt
            tab.
          </p>
        </div>

        <div>
          <p className="mb-1.5 text-xs font-medium text-text-muted">Skills</p>
          <div className="flex flex-wrap gap-1.5">
            {skillIds.map((sid) => (
              <span
                key={sid}
                className="rounded-full bg-accent-teal/10 px-2.5 py-0.5 text-[11px] font-medium text-accent-teal"
              >
                {sid}
              </span>
            ))}
            {skillIds.length === 0 && (
              <span className="text-xs text-text-muted">No skills selected</span>
            )}
          </div>
        </div>

        {config.useReflexion && (
          <p className="text-xs text-accent-teal">
            Reflexion enabled &middot; {config.maxTrials} max trials &middot;{" "}
            {config.confidenceThreshold} threshold
          </p>
        )}
      </div>

      {error && (
        <div className="mt-4 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-400">
          {error}
        </div>
      )}

      <div className="mt-8 flex justify-between">
        <button
          onClick={onBack}
          disabled={creating}
          className="rounded-lg border border-border/40 px-6 py-2.5 text-sm font-medium text-text-secondary transition-colors hover:bg-surface disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Back
        </button>
        <button
          onClick={onCreate}
          disabled={!name.trim() || creating}
          className="flex items-center gap-2 rounded-lg bg-accent-teal px-6 py-2.5 text-sm font-medium text-workspace transition-colors hover:bg-accent-teal/90 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {creating && <Loader2 size={14} className="animate-spin" />}
          {creating ? "Writing system prompt…" : "Create Employee"}
        </button>
      </div>
    </div>
  );
}
