import { useState, useEffect, useRef } from "react";
import { Plus, Loader2, AlertCircle, X, Upload, Paperclip } from "lucide-react";
import { createSkill } from "../../services/api";

export default function CreateSkillModal({ open, onClose, onCreated }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [definition, setDefinition] = useState("");
  const [files, setFiles] = useState([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const nameRef = useRef(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    if (open) {
      setName("");
      setDescription("");
      setDefinition("");
      setFiles([]);
      setError(null);
      setTimeout(() => nameRef.current?.focus(), 50);
    }
  }, [open]);

  if (!open) return null;

  const handleFileChange = (e) => {
    const selected = Array.from(e.target.files);
    setFiles((prev) => [...prev, ...selected]);
    e.target.value = "";
  };

  const removeFile = (index) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleCreate = async () => {
    if (!name.trim()) {
      setError("Name is required");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const fileMeta = files.map((f) => ({
        name: f.name,
        size: f.size,
        type: f.type,
      }));
      const skill = await createSkill({
        name: name.trim(),
        description: description.trim(),
        definition: definition.trim(),
        files: fileMeta.length > 0 ? fileMeta : undefined,
      });
      onCreated(skill);
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 w-full max-w-lg rounded-xl border border-border/50 bg-workspace shadow-2xl">
        <div className="flex items-center justify-between border-b border-border/40 px-5 py-4">
          <div className="flex items-center gap-2">
            <Plus size={16} className="text-accent-teal" />
            <h3 className="text-sm font-semibold text-text-primary">Create Skill</h3>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-text-muted transition-colors hover:bg-surface hover:text-text-secondary"
          >
            <X size={16} />
          </button>
        </div>

        <div className="max-h-[70vh] space-y-4 overflow-y-auto px-5 py-4">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-text-secondary">Name</label>
            <input
              ref={nameRef}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Custom Data Fetcher"
              className="w-full rounded-lg border border-border/50 bg-charcoal px-3 py-2 text-sm text-text-primary placeholder:text-text-muted outline-none transition-colors focus:border-accent-teal focus:ring-1 focus:ring-accent-teal/30"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-text-secondary">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What does this skill do?"
              rows={2}
              className="w-full resize-none rounded-lg border border-border/50 bg-charcoal px-3 py-2 text-sm text-text-primary placeholder:text-text-muted outline-none transition-colors focus:border-accent-teal focus:ring-1 focus:ring-accent-teal/30"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-text-secondary">Definition</label>
            <textarea
              value={definition}
              onChange={(e) => setDefinition(e.target.value)}
              placeholder="def my_skill(query: str) -> dict:&#10;    ..."
              rows={6}
              className="w-full resize-none rounded-lg border border-border/50 bg-charcoal px-3 py-2 font-mono text-xs text-text-primary placeholder:text-text-muted outline-none transition-colors focus:border-accent-teal focus:ring-1 focus:ring-accent-teal/30"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-text-secondary">Files</label>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              onChange={handleFileChange}
              className="hidden"
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-border/60 bg-charcoal/50 px-3 py-3 text-xs text-text-muted transition-colors hover:border-accent-teal/40 hover:text-text-secondary"
            >
              <Upload size={14} />
              Click to upload files
            </button>
            {files.length > 0 && (
              <div className="mt-2 space-y-1">
                {files.map((file, i) => (
                  <div
                    key={i}
                    className="flex items-center gap-2 rounded-md bg-charcoal/70 px-3 py-1.5"
                  >
                    <Paperclip size={12} className="shrink-0 text-text-muted" />
                    <span className="min-w-0 flex-1 truncate text-xs text-text-secondary">
                      {file.name}
                    </span>
                    <button
                      onClick={() => removeFile(i)}
                      className="shrink-0 rounded p-0.5 text-text-muted hover:text-red-400"
                    >
                      <X size={12} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {error && (
            <div className="flex items-center gap-2 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">
              <AlertCircle size={13} />
              {error}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-border/40 px-5 py-3">
          <button
            onClick={onClose}
            className="rounded-lg px-3.5 py-1.5 text-sm text-text-secondary transition-colors hover:bg-surface hover:text-text-primary"
          >
            Cancel
          </button>
          <button
            onClick={handleCreate}
            disabled={saving}
            className="flex items-center gap-1.5 rounded-lg bg-accent-teal px-3.5 py-1.5 text-sm font-medium text-charcoal transition-colors hover:bg-accent-light disabled:opacity-50"
          >
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
            Create
          </button>
        </div>
      </div>
    </div>
  );
}
