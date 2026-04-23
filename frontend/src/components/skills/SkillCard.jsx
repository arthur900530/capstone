import { Wrench, Cloud, CheckCircle, Paperclip } from "lucide-react";

function timeAgo(dateStr) {
  if (!dateStr) return "";
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(dateStr).toLocaleDateString();
}

export default function SkillCard({ skill, isSelected, onClick, viewMode = "grid" }) {
  const isCloudOnly = skill.is_cloud_only;
  const files = skill.files ?? [];
  const typeBadge = skill.is_builtin || skill.type === "builtin" ? "builtin" : "user";

  if (viewMode === "list") {
    return (
      <button
        onClick={onClick}
        className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left transition-colors ${
          isSelected
            ? "bg-surface border border-accent-teal/30"
            : "border border-transparent hover:bg-surface/50"
        } ${isCloudOnly ? "opacity-60" : ""}`}
      >
        <div className="shrink-0 rounded-md bg-accent-teal/10 p-1.5 text-accent-teal">
          <Wrench size={14} />
        </div>
        <p className="min-w-0 flex-1 truncate text-sm font-medium text-text-primary">{skill.name}</p>
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ${
          typeBadge === "builtin"
            ? "bg-blue-500/10 text-blue-400"
            : "bg-purple-500/10 text-purple-400"
        }`}>
          {typeBadge}
        </span>
        {isCloudOnly ? (
          <Cloud size={12} className="shrink-0 text-text-muted" />
        ) : (
          <CheckCircle size={12} className="shrink-0 text-green-400" />
        )}
        <span className="shrink-0 text-[10px] text-text-muted">{timeAgo(skill.updated_at)}</span>
      </button>
    );
  }

  // Grid card
  return (
    <button
      onClick={onClick}
      className={`flex h-full min-w-0 flex-col overflow-hidden rounded-xl border p-4 text-left transition-all ${
        isSelected
          ? "border-accent-teal/40 bg-surface"
          : "border-border/40 bg-surface hover:border-accent-teal/30 hover:bg-surface-hover"
      } ${isCloudOnly ? "opacity-60" : ""}`}
    >
      <div className="flex min-w-0 items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="shrink-0 rounded-lg bg-accent-teal/10 p-2 text-accent-teal">
            <Wrench size={16} />
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-text-primary">{skill.name}</p>
            <p className="mt-0.5 truncate text-[11px] text-text-muted">{skill.id}</p>
          </div>
        </div>
        {isCloudOnly ? (
          <span className="flex shrink-0 items-center gap-1 rounded-full bg-surface px-2 py-0.5 text-[10px] text-text-muted">
            <Cloud size={10} />
            Cloud
          </span>
        ) : (
          <CheckCircle size={14} className="shrink-0 text-green-400" />
        )}
      </div>

      <p className="mt-2.5 line-clamp-2 text-xs leading-relaxed text-text-secondary">
        {skill.description || "No description"}
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
          typeBadge === "builtin"
            ? "bg-blue-500/10 text-blue-400"
            : "bg-purple-500/10 text-purple-400"
        }`}>
          {typeBadge}
        </span>
        {(skill.tags ?? []).slice(0, 3).map((tag) => (
          <span key={tag} className="rounded-full bg-accent-teal/10 px-2 py-0.5 text-[10px] text-accent-teal">
            {tag}
          </span>
        ))}
      </div>

      <div className="mt-3 flex items-center gap-3 text-[10px] text-text-muted">
        {files.length > 0 && (
          <span className="flex items-center gap-1">
            <Paperclip size={10} />
            {files.length} file{files.length !== 1 ? "s" : ""}
          </span>
        )}
        <span>{timeAgo(skill.updated_at)}</span>
      </div>
    </button>
  );
}
