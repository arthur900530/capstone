import * as Icons from "lucide-react";

export default function PluginCard({ plugin, selected, onClick }) {
  const IconComp = Icons[plugin.icon] || Icons.Bot;

  return (
    <button
      onClick={onClick}
      className={`flex flex-col gap-3 rounded-xl border p-5 text-left transition-all ${
        selected
          ? "border-accent-teal bg-accent-teal/5"
          : "border-border/40 bg-surface hover:border-text-muted/40 hover:bg-surface-hover"
      }`}
    >
      <div className="flex items-center gap-3">
        <div
          className={`flex h-10 w-10 items-center justify-center rounded-lg ${
            selected ? "bg-accent-teal/20" : "bg-accent-teal/10"
          }`}
        >
          <IconComp size={20} className="text-accent-teal" />
        </div>
        <h3 className="font-semibold text-text-primary">{plugin.name}</h3>
      </div>

      <p className="text-sm text-text-secondary">{plugin.description}</p>

      <p className="text-xs text-text-muted">
        <span className="font-medium">Best for:</span> {plugin.bestFor}
      </p>

      {plugin.skillIds.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {plugin.skillIds.map((sid) => (
            <span
              key={sid}
              className="rounded-full bg-surface-hover px-2 py-0.5 text-[11px] text-text-muted"
            >
              {sid}
            </span>
          ))}
        </div>
      )}
    </button>
  );
}
