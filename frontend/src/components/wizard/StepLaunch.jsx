import * as Icons from "lucide-react";
import PLUGINS from "../../data/plugins";

export default function StepLaunch({
  name,
  onNameChange,
  task,
  pluginIds,
  skillIds,
  config,
  files,
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

      {/* Summary card */}
      <div className="mt-6 rounded-xl border border-border/40 bg-surface p-5 space-y-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent-teal/10">
            <FirstIcon size={20} className="text-accent-teal" />
          </div>
          <div>
            <p className="font-medium text-text-primary">
              {selectedPlugins.map((p) => p.name).join(", ") || "Custom"}
            </p>
            <p className="text-xs text-text-muted">
              {config.model?.split("/").pop()}
            </p>
          </div>
        </div>

        <div>
          <p className="mb-1 text-xs font-medium text-text-muted">Task</p>
          <p className="text-sm text-text-secondary">{task}</p>
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

        {files.length > 0 && (
          <div>
            <p className="mb-1 text-xs font-medium text-text-muted">
              Files ({files.length})
            </p>
            <p className="text-sm text-text-secondary">
              {files.map((f) => f.name).join(", ")}
            </p>
          </div>
        )}

        {config.useReflexion && (
          <p className="text-xs text-accent-teal">
            Reflexion enabled &middot; {config.maxTrials} max trials &middot;{" "}
            {config.confidenceThreshold} threshold
          </p>
        )}
      </div>

      <div className="mt-8 flex justify-between">
        <button
          onClick={onBack}
          className="rounded-lg border border-border/40 px-6 py-2.5 text-sm font-medium text-text-secondary transition-colors hover:bg-surface"
        >
          Back
        </button>
        <button
          onClick={onCreate}
          disabled={!name.trim()}
          className="rounded-lg bg-accent-teal px-6 py-2.5 text-sm font-medium text-workspace transition-colors hover:bg-accent-teal/90 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Create Employee
        </button>
      </div>
    </div>
  );
}
