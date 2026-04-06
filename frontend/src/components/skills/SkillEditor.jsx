import { useState, useEffect, useRef } from "react";
import { Loader2, AlertCircle, Save, X, Code, Pencil, Paperclip, Trash2, Upload } from "lucide-react";
import { updateSkill, deleteSkill, addSkillFiles, removeSkillFile } from "../../services/api";
import { fileIcon } from "./utils";
import FileViewer from "./FileViewer";

export default function SkillEditor({ skill, onSaved, onDeleted, viewingFile, onViewFile }) {
  const [name, setName] = useState(skill.name);
  const [description, setDescription] = useState(skill.description);
  const [definition, setDefinition] = useState(skill.definition);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [dirty, setDirty] = useState(false);
  const fileInputRef = useRef(null);

  const files = skill.files ?? [];

  useEffect(() => {
    setName(skill.name);
    setDescription(skill.description);
    setDefinition(skill.definition);
    setDirty(false);
    setError(null);
  }, [skill]);

  const handleFieldChange = (setter) => (e) => {
    setter(e.target.value);
    setDirty(true);
  };

  const handleSave = async () => {
    if (!name.trim()) {
      setError("Name is required");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const updated = await updateSkill(skill.id, {
        name: name.trim(),
        description: description.trim(),
        definition: definition.trim(),
      });
      setDirty(false);
      onSaved(updated);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm(`Delete "${skill.name}"?`)) return;
    try {
      await deleteSkill(skill.id);
      onDeleted(skill.id);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleAddFiles = async (e) => {
    const selected = Array.from(e.target.files);
    if (selected.length === 0) return;
    e.target.value = "";
    try {
      const meta = selected.map((f) => ({ name: f.name, size: f.size, type: f.type }));
      const updated = await addSkillFiles(skill.id, meta);
      onSaved(updated);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleRemoveFile = async (filename) => {
    try {
      const updated = await removeSkillFile(skill.id, filename);
      onSaved(updated);
    } catch (err) {
      setError(err.message);
    }
  };

  if (viewingFile) {
    return (
      <FileViewer
        skillId={skill.id}
        skillName={skill.name}
        filename={viewingFile}
        onClose={() => onViewFile(null)}
      />
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border/40 px-5 py-3">
        <div className="flex items-center gap-2">
          <Code size={15} className="text-accent-teal" />
          <h3 className="text-sm font-medium text-text-primary">{skill.name}</h3>
        </div>
        <div className="flex items-center gap-1.5">
          {dirty && (
            <button
              onClick={handleSave}
              disabled={saving}
              className="flex items-center gap-1.5 rounded-lg bg-accent-teal px-3 py-1.5 text-xs font-medium text-charcoal transition-colors hover:bg-accent-light disabled:opacity-50"
            >
              {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
              Save
            </button>
          )}
          <button
            onClick={handleDelete}
            className="rounded-lg p-1.5 text-text-muted transition-colors hover:bg-red-500/10 hover:text-red-400"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-5">
        <div className="mx-auto max-w-2xl space-y-5">
          <div>
            <label className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-text-secondary">
              <Pencil size={12} />
              Name
            </label>
            <input
              value={name}
              onChange={handleFieldChange(setName)}
              className="w-full rounded-lg border border-border/50 bg-charcoal px-3 py-2 text-sm text-text-primary outline-none transition-colors focus:border-accent-teal focus:ring-1 focus:ring-accent-teal/30"
            />
          </div>

          <div>
            <label className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-text-secondary">
              <Pencil size={12} />
              Description
            </label>
            <textarea
              value={description}
              onChange={handleFieldChange(setDescription)}
              rows={3}
              className="w-full resize-none rounded-lg border border-border/50 bg-charcoal px-3 py-2 text-sm text-text-primary outline-none transition-colors focus:border-accent-teal focus:ring-1 focus:ring-accent-teal/30"
            />
          </div>

          {/* Files section */}
          <div>
            <div className="mb-1.5 flex items-center justify-between">
              <label className="flex items-center gap-1.5 text-xs font-medium text-text-secondary">
                <Paperclip size={12} />
                Files
                {files.length > 0 && (
                  <span className="rounded-full bg-surface px-1.5 py-0.5 text-[10px] text-text-muted">
                    {files.length}
                  </span>
                )}
              </label>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                onChange={handleAddFiles}
                className="hidden"
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-accent-teal transition-colors hover:bg-accent-teal/10"
              >
                <Upload size={11} />
                Add Files
              </button>
            </div>
            {files.length > 0 ? (
              <div className="rounded-lg border border-border/60 bg-[#2a2c31] shadow-[0_2px_12px_rgba(0,0,0,0.25)]">
                {files.map((file, i) => {
                  const { Icon, color } = fileIcon(file.name);
                  return (
                    <div
                      key={file.name}
                      className={`group flex items-center gap-2.5 px-3 py-2 ${
                        i > 0 ? "border-t border-border/20" : ""
                      }`}
                    >
                      <Icon size={14} className={`shrink-0 ${color}`} />
                      <button
                        onClick={() => onViewFile(file.name)}
                        className={`min-w-0 flex-1 truncate text-left text-sm transition-colors hover:underline ${
                          file.name === "SKILL.md"
                            ? "font-medium text-accent-teal hover:text-accent-light"
                            : file.name === "LICENSE"
                              ? "text-yellow-500/90 hover:text-yellow-400"
                              : "text-text-primary hover:text-accent-teal"
                        }`}
                      >
                        {file.name}
                      </button>
                      <button
                        onClick={() => handleRemoveFile(file.name)}
                        className="shrink-0 rounded p-0.5 text-text-muted opacity-0 transition-all group-hover:opacity-100 hover:text-red-400"
                      >
                        <X size={13} />
                      </button>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="rounded-lg border border-dashed border-border/30 bg-charcoal/20 px-3 py-4 text-center text-xs text-text-muted">
                No files in this skill
              </p>
            )}
          </div>

          <div>
            <label className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-text-secondary">
              <Code size={12} />
              Definition
            </label>
            <textarea
              value={definition}
              onChange={handleFieldChange(setDefinition)}
              rows={14}
              className="w-full resize-none rounded-lg border border-border/50 bg-charcoal px-4 py-3 font-mono text-xs leading-relaxed text-text-primary outline-none transition-colors focus:border-accent-teal focus:ring-1 focus:ring-accent-teal/30"
            />
          </div>

          {error && (
            <div className="flex items-center gap-2 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">
              <AlertCircle size={13} />
              {error}
            </div>
          )}

          <div className="flex items-center gap-3 rounded-lg border border-border/60 bg-[#2a2c31] px-4 py-3 shadow-[0_2px_12px_rgba(0,0,0,0.25)]">
            <div className="text-xs text-text-muted">
              <span className="font-medium text-text-secondary">ID:</span>{" "}
              <code className="rounded bg-surface px-1.5 py-0.5 text-accent-teal">{skill.id}</code>
            </div>
            <span className="text-text-muted">&middot;</span>
            <div className="text-xs text-text-muted">
              Created {new Date(skill.created_at).toLocaleDateString()}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
