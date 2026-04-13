import { useState, useEffect } from "react";
import {
  X, Download, Trash2, Cloud, CheckCircle, Paperclip, AlertCircle,
  ChevronDown, ChevronRight, ExternalLink, Copy, Check, Maximize2,
  Loader2, Pencil, Save, Undo2, Send,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import { updateSkill, createSubmission } from "../../services/api";
import { fileIcon } from "./utils";
import FileViewer from "./FileViewer";
import ConfirmDialog from "./ConfirmDialog";
import VersionTabs from "./VersionTabs";
import useVersionHistory from "../../hooks/useVersionHistory";

/* ── Shared markdown component map ──────────────────────────────────────── */

const mdComponents = {
  h1: ({ children }) => <h1 className="mb-3 mt-1 text-base font-semibold text-text-primary">{children}</h1>,
  h2: ({ children }) => <h2 className="mb-2 mt-5 border-b border-border/20 pb-1.5 text-[13px] font-semibold text-text-primary">{children}</h2>,
  h3: ({ children }) => <h3 className="mb-1.5 mt-3 text-xs font-semibold text-text-primary">{children}</h3>,
  p: ({ children }) => <p className="mb-2.5 text-[13px] leading-[1.7] text-text-secondary">{children}</p>,
  ul: ({ children }) => <ul className="mb-2.5 ml-4 list-disc space-y-1 text-[13px] text-text-secondary">{children}</ul>,
  ol: ({ children }) => <ol className="mb-2.5 ml-4 list-decimal space-y-1 text-[13px] text-text-secondary">{children}</ol>,
  li: ({ children }) => <li className="text-[13px] leading-[1.6] text-text-secondary">{children}</li>,
  a: ({ href, children }) => <a href={href} className="text-accent-teal hover:text-accent-light hover:underline">{children}</a>,
  strong: ({ children }) => <strong className="font-semibold text-text-primary">{children}</strong>,
  em: ({ children }) => <em className="text-text-secondary/80">{children}</em>,
  code: ({ className, children, ...props }) => {
    const isBlock = className?.includes("language-");
    if (isBlock) {
      return (
        <pre className="my-3 overflow-x-auto rounded-lg border border-border/20 bg-charcoal/80 px-4 py-3">
          <code className="text-xs font-mono leading-relaxed text-accent-light/90">{children}</code>
        </pre>
      );
    }
    return <code className="rounded-md bg-accent-teal/8 px-1.5 py-0.5 text-xs font-mono text-accent-teal" {...props}>{children}</code>;
  },
  pre: ({ children }) => <>{children}</>,
  blockquote: ({ children }) => (
    <blockquote className="my-3 border-l-2 border-accent-teal/30 pl-3.5 text-[13px] italic text-text-muted">{children}</blockquote>
  ),
  hr: () => <hr className="my-5 border-border/20" />,
};

/* ── Pop-out modal ──────────────────────────────────────────────────────── */

function DefinitionModal({ definition, skillName, onClose }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(definition);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-8">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 flex max-h-[85vh] w-full max-w-3xl animate-scale-in flex-col rounded-2xl border border-border/30 bg-workspace shadow-2xl shadow-black/40">
        <div className="flex items-center justify-between border-b border-border/30 px-5 py-3">
          <span className="text-sm font-medium text-text-primary">{skillName}</span>
          <div className="flex items-center gap-1">
            <button
              onClick={handleCopy}
              className="rounded-lg p-1.5 text-text-muted transition-colors hover:bg-surface hover:text-text-secondary"
              title="Copy definition"
            >
              {copied ? <Check size={15} className="text-green-400" /> : <Copy size={15} />}
            </button>
            <button
              onClick={onClose}
              className="rounded-lg p-1.5 text-text-muted transition-colors hover:bg-surface hover:text-text-secondary"
            >
              <X size={15} />
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto px-8 py-6">
          <ReactMarkdown components={mdComponents}>{definition}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
}

/* ── Main panel ─────────────────────────────────────────────────────────── */

export default function SkillDetailPanel({ skill, onClose, onInstall, onUninstall, onDelete, onSaved, onPopOut }) {
  const [viewingFile, setViewingFile] = useState(null);
  const [filesExpanded, setFilesExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [installing, setInstalling] = useState(false);

  // Edit mode state
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState(skill.name);
  const [editDesc, setEditDesc] = useState(skill.description);
  const [editDef, setEditDef] = useState(skill.definition);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [showSaveConfirm, setShowSaveConfirm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitDone, setSubmitDone] = useState(false);

  const {
    versions, activeVersion, setActiveVersion, addVersion, markSubmitted, getVersion, latestVersion,
  } = useVersionHistory(skill.id, skill);

  const viewingOldVersion = activeVersion !== latestVersion;
  const versionData = viewingOldVersion ? getVersion(activeVersion) : null;

  const files = skill.files ?? [];
  const isCloudOnly = skill.is_cloud_only;
  const isBuiltin = skill.is_builtin || skill.type === "builtin";
  const tags = skill.tags ?? [];

  // Reset edit state when skill changes
  useEffect(() => {
    setEditing(false);
    setEditName(skill.name);
    setEditDesc(skill.description);
    setEditDef(skill.definition);
    setSubmitDone(false);
  }, [skill.id]);

  const dirty = editing && (editName !== skill.name || editDesc !== skill.description || editDef !== skill.definition);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(skill.definition);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleInstall = async () => {
    setInstalling(true);
    try { await onInstall?.(skill.id); } finally { setInstalling(false); }
  };

  const handleUninstall = async () => {
    setInstalling(true);
    try { await onUninstall?.(skill.id); } finally { setInstalling(false); }
  };

  const handleSave = () => setShowSaveConfirm(true);

  const handleConfirmSave = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const updated = await updateSkill(skill.id, {
        name: editName.trim(),
        description: editDesc.trim(),
        definition: editDef.trim(),
      });
      addVersion({
        name: editName.trim(),
        description: editDesc.trim(),
        definition: editDef.trim(),
      });
      setEditing(false);
      setShowSaveConfirm(false);
      onSaved?.(updated);
    } catch (err) {
      setSaveError(err.message);
      setShowSaveConfirm(false);
    } finally {
      setSaving(false);
    }
  };

  const handleDiscard = () => {
    setEditName(skill.name);
    setEditDesc(skill.description);
    setEditDef(skill.definition);
    setEditing(false);
  };

  const latestVersionData = getVersion(latestVersion);
  const latestSubmitted = latestVersionData?.submitted ?? false;

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      await createSubmission({
        name: skill.name,
        description: skill.description,
        skill_md: skill.definition,
        submission_type: "authored",
      });
      markSubmitted(latestVersion);
      setSubmitDone(true);
      setTimeout(() => setSubmitDone(false), 3000);
    } finally {
      setSubmitting(false);
    }
  };

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
        <h3 className="text-sm font-semibold text-text-primary">
          {editing ? "Editing" : ""} {skill.name}
        </h3>
        <div className="flex items-center gap-1.5">
          {/* Edit toggle */}
          {!isBuiltin && !editing && !viewingOldVersion && (
            <button
              onClick={() => setEditing(true)}
              className="flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium text-text-muted transition-colors hover:bg-surface hover:text-text-secondary"
            >
              <Pencil size={12} />
              Edit
            </button>
          )}
          {/* Save / Discard (edit mode) */}
          {editing && (
            <>
              <button
                onClick={handleDiscard}
                className="flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs text-text-muted transition-colors hover:bg-surface hover:text-text-secondary"
              >
                <Undo2 size={12} />
                Discard
              </button>
              <button
                onClick={handleSave}
                disabled={saving || !dirty}
                className="flex items-center gap-1 rounded-lg bg-accent-teal px-2.5 py-1.5 text-xs font-medium text-charcoal transition-colors hover:bg-accent-light disabled:opacity-50"
              >
                {saving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                Save
              </button>
            </>
          )}
          {/* Submit — shown when latest version is unsubmitted and not editing */}
          {!isBuiltin && !editing && !viewingOldVersion && (
            <button
              onClick={handleSubmit}
              disabled={submitting || latestSubmitted}
              className={`flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors ${
                submitDone || latestSubmitted
                  ? "bg-green-500/10 text-green-400"
                  : "bg-accent-teal px-3 text-charcoal hover:bg-accent-light"
              } disabled:opacity-50`}
            >
              {submitDone || latestSubmitted ? <Check size={12} /> : submitting ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
              {submitDone || latestSubmitted ? `v${latestVersion} Submitted` : `Submit v${latestVersion}`}
            </button>
          )}
          {onPopOut && (
            <button
              onClick={onPopOut}
              className="rounded-md p-1 text-text-muted transition-colors hover:bg-surface hover:text-text-secondary"
              title="Pop out"
            >
              <Maximize2 size={14} />
            </button>
          )}
          <button
            onClick={onClose}
            className="rounded-md p-1 text-text-muted transition-colors hover:bg-surface hover:text-text-secondary"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      <VersionTabs
        versions={versions}
        activeVersion={activeVersion}
        onSelect={setActiveVersion}
      />

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-5">
        <div className="space-y-5">
          {/* Old version banner */}
          {viewingOldVersion && versionData && (
            <div className="flex items-center justify-between rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2">
              <span className="text-xs text-amber-400">
                Viewing v{activeVersion} (read-only) — saved {new Date(versionData.savedAt).toLocaleDateString()}
              </span>
              <button
                onClick={() => setActiveVersion(latestVersion)}
                className="text-[11px] font-medium text-accent-teal hover:underline"
              >
                Go to latest
              </button>
            </div>
          )}

          {saveError && (
            <div className="flex items-center gap-2 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">
              <AlertCircle size={13} />
              {saveError}
            </div>
          )}

          {/* Badges */}
          <div className="flex flex-wrap items-center gap-2">
            <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium ${
              isBuiltin
                ? "bg-blue-500/10 text-blue-400"
                : "bg-purple-500/10 text-purple-400"
            }`}>
              {isBuiltin ? "builtin" : "user"}
            </span>
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
            {editing && (
              <span className="rounded-full bg-yellow-500/10 px-2.5 py-0.5 text-[11px] text-yellow-400">
                editing
              </span>
            )}
            {tags.map((tag) => (
              <span key={tag} className="rounded-full bg-accent-teal/10 px-2 py-0.5 text-[10px] text-accent-teal">
                {tag}
              </span>
            ))}
          </div>

          {/* Editable or read-only fields */}
          {editing ? (
            <div className="space-y-4">
              <div>
                <label className="mb-1.5 block text-xs font-medium text-text-secondary">Name</label>
                <input
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="w-full rounded-lg border border-border/50 bg-charcoal px-3 py-2 text-sm text-text-primary outline-none transition-colors focus:border-accent-teal focus:ring-1 focus:ring-accent-teal/30"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium text-text-secondary">Description</label>
                <textarea
                  value={editDesc}
                  onChange={(e) => setEditDesc(e.target.value)}
                  rows={2}
                  className="w-full resize-none rounded-lg border border-border/50 bg-charcoal px-3 py-2 text-sm text-text-primary outline-none transition-colors focus:border-accent-teal focus:ring-1 focus:ring-accent-teal/30"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium text-text-secondary">Definition</label>
                <textarea
                  value={editDef}
                  onChange={(e) => setEditDef(e.target.value)}
                  rows={16}
                  className="w-full resize-none rounded-lg border border-border/50 bg-charcoal px-4 py-3 font-mono text-xs leading-relaxed text-text-primary outline-none transition-colors focus:border-accent-teal focus:ring-1 focus:ring-accent-teal/30"
                />
              </div>
            </div>
          ) : (
            <>
              {/* Description */}
              {(viewingOldVersion ? versionData?.description : skill.description) && (
                <p className="text-sm leading-relaxed text-text-secondary">
                  {viewingOldVersion ? versionData.description : skill.description}
                </p>
              )}

              {/* Actions */}
              <div className="flex items-center gap-2">
                {isCloudOnly ? (
                  <button
                    onClick={handleInstall}
                    disabled={installing}
                    className="flex items-center gap-2 rounded-lg bg-accent-teal px-4 py-2 text-sm font-medium text-charcoal transition-colors hover:bg-accent-light disabled:opacity-50"
                  >
                    {installing ? <Loader2 size={15} className="animate-spin" /> : <Download size={15} />}
                    {installing ? "Installing..." : "Install Skill"}
                  </button>
                ) : !isBuiltin && (
                  <button
                    onClick={handleUninstall}
                    disabled={installing}
                    className="flex items-center gap-2 rounded-lg border border-border/40 px-4 py-2 text-sm text-text-secondary transition-colors hover:bg-surface disabled:opacity-50"
                  >
                    {installing ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                    {installing ? "Removing..." : "Uninstall"}
                  </button>
                )}
                {!isBuiltin && onDelete && (
                  <button
                    onClick={() => { if (confirm(`Permanently delete "${skill.name}" from the database? This cannot be undone.`)) onDelete(skill.id); }}
                    className="flex items-center gap-2 rounded-lg border border-red-500/20 px-4 py-2 text-sm text-red-400 transition-colors hover:bg-red-500/10"
                  >
                    <Trash2 size={14} />
                    Delete
                  </button>
                )}
              </div>

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
              {(viewingOldVersion ? versionData?.definition : skill.definition) && (
                <div className="group relative rounded-xl border border-border/20 bg-gradient-to-b from-surface/40 to-transparent p-[1px]">
                  <div className="rounded-[11px] bg-workspace px-5 py-4">
                    <div className="mb-3 flex items-center justify-between">
                      <span className="text-[11px] font-medium tracking-wide text-text-muted uppercase">Definition</span>
                      <div className="flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                        <button
                          onClick={handleCopy}
                          className="rounded-md p-1.5 text-text-muted transition-colors hover:bg-surface hover:text-text-secondary"
                          title="Copy to clipboard"
                        >
                          {copied ? <Check size={14} className="text-green-400" /> : <Copy size={14} />}
                        </button>
                        <button
                          onClick={() => setShowModal(true)}
                          className="rounded-md p-1.5 text-text-muted transition-colors hover:bg-surface hover:text-text-secondary"
                          title="Expand"
                        >
                          <Maximize2 size={14} />
                        </button>
                      </div>
                    </div>
                    <ReactMarkdown components={mdComponents}>
                      {viewingOldVersion ? versionData.definition : skill.definition}
                    </ReactMarkdown>
                  </div>
                </div>
              )}
            </>
          )}

          {/* Metadata footer */}
          <div className="flex items-center gap-3 text-[11px] text-text-muted">
            <span>
              <span className="font-medium text-text-secondary">ID:</span>{" "}
              <code className="rounded bg-surface px-1.5 py-0.5 text-accent-teal">{skill.id}</code>
            </span>
            {latestVersion > 0 && (
              <>
                <span>&middot;</span>
                <span>v{activeVersion} of {latestVersion}</span>
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

      {/* Pop-out modal */}
      {showModal && (
        <DefinitionModal
          definition={skill.definition}
          skillName={skill.name}
          onClose={() => setShowModal(false)}
        />
      )}

      <ConfirmDialog
        open={showSaveConfirm}
        title={`Save as v${latestVersion + 1}?`}
        message="This creates a new version of the skill. Previous versions remain viewable."
        confirmLabel="Save"
        onConfirm={handleConfirmSave}
        onCancel={() => setShowSaveConfirm(false)}
        loading={saving}
      />
    </div>
  );
}
