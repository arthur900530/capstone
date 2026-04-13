export default function VersionTabs({ versions, activeVersion, onSelect }) {
  if (!versions || versions.length <= 1) return null;

  const latest = versions[versions.length - 1].version;

  return (
    <div className="flex items-center gap-1 border-b border-border/30 px-5 py-2">
      <span className="mr-1.5 text-[10px] font-medium text-text-muted">Versions</span>
      {versions.map((v) => {
        const isActive = v.version === activeVersion;
        const isLatest = v.version === latest;
        return (
          <button
            key={v.version}
            onClick={() => onSelect(v.version)}
            className={`relative flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium transition-colors ${
              isActive
                ? "bg-accent-teal text-charcoal"
                : "bg-surface text-text-muted hover:text-text-secondary"
            }`}
          >
            v{v.version}
            {isLatest && !isActive && (
              <span className="text-[9px] text-accent-teal">latest</span>
            )}
            {!v.submitted && (
              <span className="absolute -right-0.5 -top-0.5 h-1.5 w-1.5 rounded-full bg-amber-400" />
            )}
          </button>
        );
      })}
    </div>
  );
}
