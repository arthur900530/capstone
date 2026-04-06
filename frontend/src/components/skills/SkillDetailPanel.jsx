import { useState } from "react";
import {
  X, Download, Trash2, Cloud, CheckCircle, Paperclip,
  ChevronDown, ChevronRight, ExternalLink,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import { fileIcon } from "./utils";
import FileViewer from "./FileViewer";

export default function SkillDetailPanel({ skill, onClose, onInstall, onUninstall }) {
  const [viewingFile, setViewingFile] = useState(null);
  const [filesExpanded, setFilesExpanded] = useState(false);

  const files = skill.files ?? [];
  const isCloudOnly = skill.is_cloud_only;
  const isBuiltin = skill.is_builtin || skill.type === "builtin";
  const tags = skill.tags ?? [];

  if (viewingFile) {
    return (
      <FileViewer
        skillId={skill.id}
        skillName={skill.name}
        filename={viewingFile}
        onClose={() => setViewingFile(null)}
      />
    );
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border/40 px-5 py-3">
        <h3 className="text-sm font-semibold text-text-primary">{skill.name}</h3>
        <button
          onClick={onClose}
          className="rounded-md p-1 text-text-muted transition-colors hover:bg-surface hover:text-text-secondary"
        >
          <X size={16} />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-5">
        <div className="space-y-5">
          {/* Badges */}
          <div className="flex flex-wrap items-center gap-2">
            <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium ${
              isBuiltin
                ? "bg-blue-500/10 text-blue-400"
                : "bg-purple-500/10 text-purple-400"
            }`}>
              {isBuiltin ? "builtin" : "user"}
            </span>
            {skill.status && skill.status !== "published" && (
              <span className="rounded-full bg-yellow-500/10 px-2.5 py-0.5 text-[11px] text-yellow-400">
                {skill.status}
              </span>
            )}
            {isCloudOnly ? (
              <span className="flex items-center gap-1 rounded-full bg-surface px-2.5 py-0.5 text-[11px] text-text-muted">
                <Cloud size={11} />
                Cloud only
              </span>
            ) : (
              <span className="flex items-center gap-1 rounded-full bg-green-500/10 px-2.5 py-0.5 text-[11px] text-green-400">
                <CheckCircle size={11} />
                Installed
              </span>
            )}
            {tags.map((tag) => (
              <span key={tag} className="rounded-full bg-accent-teal/10 px-2 py-0.5 text-[10px] text-accent-teal">
                {tag}
              </span>
            ))}
          </div>

          {/* Description */}
          {skill.description && (
            <p className="text-sm leading-relaxed text-text-secondary">{skill.description}</p>
          )}

          {/* Install / Uninstall action */}
          {isCloudOnly ? (
            <button
              onClick={() => onInstall?.(skill.id)}
              className="flex items-center gap-2 rounded-lg bg-accent-teal px-4 py-2 text-sm font-medium text-charcoal transition-colors hover:bg-accent-light"
            >
              <Download size={15} />
              Install Skill
            </button>
          ) : !isBuiltin && (
            <button
              onClick={() => onUninstall?.(skill.id)}
              className="flex items-center gap-2 rounded-lg border border-border/40 px-4 py-2 text-sm text-text-secondary transition-colors hover:bg-surface"
            >
              <Trash2 size={14} />
              Uninstall
            </button>
          )}

          {/* Files */}
          {files.length > 0 && (
            <div>
              <button
                onClick={() => setFilesExpanded(!filesExpanded)}
                className="flex items-center gap-1.5 text-xs font-medium text-text-secondary"
              >
                {filesExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                <Paperclip size={12} />
                {files.length} file{files.length !== 1 ? "s" : ""}
              </button>
              {filesExpanded && (
                <div className="mt-2 rounded-lg border border-border/40 bg-charcoal/50">
                  {files.map((file, i) => {
                    const { Icon, color } = fileIcon(file.name);
                    return (
                      <button
                        key={file.name}
                        onClick={() => setViewingFile(file.name)}
                        className={`flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-surface/60 ${
                          i > 0 ? "border-t border-border/20" : ""
                        }`}
                      >
                        <Icon size={13} className={`shrink-0 ${color}`} />
                        <span className="min-w-0 flex-1 truncate text-xs text-text-secondary">
                          {file.name}
                        </span>
                        <ExternalLink size={11} className="shrink-0 text-text-muted" />
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* Rendered SKILL.md */}
          {skill.definition && (
            <div className="rounded-lg border border-border/40 bg-charcoal/30 p-4">
              <div className="prose prose-invert prose-sm max-w-none
                prose-headings:text-text-primary prose-headings:font-semibold
                prose-p:text-text-secondary prose-p:leading-relaxed
                prose-a:text-accent-teal prose-a:no-underline hover:prose-a:underline
                prose-code:rounded prose-code:bg-surface prose-code:px-1.5 prose-code:py-0.5 prose-code:text-accent-teal prose-code:text-xs
                prose-pre:rounded-lg prose-pre:border prose-pre:border-border/40 prose-pre:bg-[#2a2c31]
                prose-li:text-text-secondary
                prose-strong:text-text-primary
              ">
                <ReactMarkdown>{skill.definition}</ReactMarkdown>
              </div>
            </div>
          )}

          {/* Metadata footer */}
          <div className="flex items-center gap-3 text-[11px] text-text-muted">
            <span>
              <span className="font-medium text-text-secondary">ID:</span>{" "}
              <code className="rounded bg-surface px-1.5 py-0.5 text-accent-teal">{skill.id}</code>
            </span>
            {skill.version && (
              <>
                <span>&middot;</span>
                <span>v{skill.version}</span>
              </>
            )}
            {skill.created_at && (
              <>
                <span>&middot;</span>
                <span>Created {new Date(skill.created_at).toLocaleDateString()}</span>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
