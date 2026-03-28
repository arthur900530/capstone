import { useState, useEffect, useRef } from "react";
import {
  Wrench,
  Plus,
  Loader2,
  AlertCircle,
  Search,
  Trash2,
  Save,
  X,
  Code,
  Pencil,
  Paperclip,
  ChevronDown,
  ChevronRight,
  FileText,
  Upload,
  BookOpen,
  Scale,
  FileCode,
  File,
  Sparkles,
  CheckCircle,
} from "lucide-react";
import {
  fetchSkills,
  createSkill,
  updateSkill,
  deleteSkill,
  addSkillFiles,
  removeSkillFile,
  fetchSkillFileContent,
  trainSkillsFromMedia,
} from "../services/api";

function fileIcon(name) {
  const lower = name.toLowerCase();
  if (lower === "skill.md") return { Icon: BookOpen, color: "text-accent-teal" };
  if (lower === "license") return { Icon: Scale, color: "text-yellow-500" };
  if (lower.endsWith(".md")) return { Icon: FileText, color: "text-blue-400" };
  if (lower.endsWith(".py") || lower.endsWith(".sh")) return { Icon: FileCode, color: "text-green-400" };
  if (lower.endsWith(".json") || lower.endsWith(".yaml") || lower.endsWith(".yml")) return { Icon: Code, color: "text-orange-400" };
  if (lower.endsWith(".csv")) return { Icon: FileText, color: "text-purple-400" };
  return { Icon: File, color: "text-text-muted" };
}

function isMonoFile(name) {
  const lower = name.toLowerCase();
  return (
    lower.endsWith(".json") ||
    lower.endsWith(".yaml") ||
    lower.endsWith(".yml") ||
    lower.endsWith(".csv") ||
    lower.endsWith(".py") ||
    lower.endsWith(".sh")
  );
}

function CreateSkillModal({ open, onClose, onCreated }) {
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

const MEDIA_ACCEPT =
  "video/*,audio/*,text/*,.md,.py,.sh,.json,.yaml,.yml,.csv,.txt,.mp4,.mov,.mp3,.wav,.m4a,.webm";

function TrainSkillModal({ open, onClose, onTrained }) {
  const [files, setFiles] = useState([]);
  const [training, setTraining] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const fileInputRef = useRef(null);
  const dropRef = useRef(null);

  useEffect(() => {
    if (open) {
      setFiles([]);
      setError(null);
      setResult(null);
      setTraining(false);
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

  const handleDrop = (e) => {
    e.preventDefault();
    const dropped = Array.from(e.dataTransfer.files);
    if (dropped.length > 0) setFiles((prev) => [...prev, ...dropped]);
  };

  const handleTrain = async () => {
    if (files.length === 0) {
      setError("Please add at least one file");
      return;
    }
    setTraining(true);
    setError(null);
    setResult(null);
    try {
      const newSkills = await trainSkillsFromMedia(files);
      setResult(newSkills);
      onTrained(newSkills);
    } catch (err) {
      setError(err.message);
    } finally {
      setTraining(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={training ? undefined : onClose} />
      <div className="relative z-10 w-full max-w-lg rounded-xl border border-border/50 bg-workspace shadow-2xl">
        <div className="flex items-center justify-between border-b border-border/40 px-5 py-4">
          <div className="flex items-center gap-2">
            <Sparkles size={16} className="text-accent-teal" />
            <h3 className="text-sm font-semibold text-text-primary">Train Skills from Media</h3>
          </div>
          {!training && (
            <button
              onClick={onClose}
              className="rounded-md p-1 text-text-muted transition-colors hover:bg-surface hover:text-text-secondary"
            >
              <X size={16} />
            </button>
          )}
        </div>

        <div className="max-h-[70vh] space-y-4 overflow-y-auto px-5 py-4">
          {result ? (
            <div className="space-y-3">
              <div className="flex items-center gap-2 rounded-lg bg-green-500/10 px-3 py-2.5 text-sm text-green-400">
                <CheckCircle size={15} />
                {result.length === 0
                  ? "Training complete, but no new skills were extracted."
                  : `Successfully extracted ${result.length} skill${result.length > 1 ? "s" : ""}!`}
              </div>
              {result.length > 0 && (
                <div className="space-y-1.5">
                  {result.map((s) => (
                    <div
                      key={s.id}
                      className="flex items-center gap-2 rounded-md bg-charcoal/70 px-3 py-2"
                    >
                      <Sparkles size={12} className="shrink-0 text-accent-teal" />
                      <span className="min-w-0 flex-1 truncate text-sm font-medium text-text-primary">
                        {s.name}
                      </span>
                      <span className="shrink-0 text-[10px] text-text-muted">{s.id}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : training ? (
            <div className="flex flex-col items-center gap-3 py-8">
              <Loader2 size={28} className="animate-spin text-accent-teal" />
              <p className="text-sm font-medium text-text-primary">Analyzing media and extracting skills...</p>
              <p className="text-xs text-text-muted">This may take a minute for large files</p>
            </div>
          ) : (
            <>
              <p className="text-xs text-text-muted">
                Upload video, audio, or text files. The AI will analyze them and extract reusable skills.
              </p>
              <div>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept={MEDIA_ACCEPT}
                  onChange={handleFileChange}
                  className="hidden"
                />
                <div
                  ref={dropRef}
                  onClick={() => fileInputRef.current?.click()}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={handleDrop}
                  className="flex w-full cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border/60 bg-charcoal/50 px-3 py-6 text-xs text-text-muted transition-colors hover:border-accent-teal/40 hover:text-text-secondary"
                >
                  <Upload size={20} />
                  <span>Click or drag files here</span>
                  <span className="text-[10px]">Video, audio, text, code files</span>
                </div>
              </div>
              {files.length > 0 && (
                <div className="space-y-1">
                  {files.map((file, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-2 rounded-md bg-charcoal/70 px-3 py-1.5"
                    >
                      <Paperclip size={12} className="shrink-0 text-text-muted" />
                      <span className="min-w-0 flex-1 truncate text-xs text-text-secondary">
                        {file.name}
                      </span>
                      <span className="shrink-0 text-[10px] text-text-muted">
                        {file.size < 1024 * 1024
                          ? `${Math.round(file.size / 1024)}KB`
                          : `${(file.size / (1024 * 1024)).toFixed(1)}MB`}
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
            </>
          )}

          {error && (
            <div className="flex items-center gap-2 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">
              <AlertCircle size={13} />
              <span className="min-w-0 flex-1 break-all">{error}</span>
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-border/40 px-5 py-3">
          {result ? (
            <button
              onClick={onClose}
              className="flex items-center gap-1.5 rounded-lg bg-accent-teal px-3.5 py-1.5 text-sm font-medium text-charcoal transition-colors hover:bg-accent-light"
            >
              Done
            </button>
          ) : (
            <>
              <button
                onClick={onClose}
                disabled={training}
                className="rounded-lg px-3.5 py-1.5 text-sm text-text-secondary transition-colors hover:bg-surface hover:text-text-primary disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleTrain}
                disabled={training || files.length === 0}
                className="flex items-center gap-1.5 rounded-lg bg-accent-teal px-3.5 py-1.5 text-sm font-medium text-charcoal transition-colors hover:bg-accent-light disabled:opacity-50"
              >
                {training ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                Train
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function SkillListItem({ skill, isSelected, onSelect, onFileClick }) {
  const [expanded, setExpanded] = useState(false);
  const files = skill.files ?? [];

  const handleClick = () => {
    onSelect(skill.id);
    if (files.length > 0) setExpanded((v) => !v);
  };

  return (
    <li>
      <button
        onClick={handleClick}
        className={`flex w-full items-start gap-2 rounded-lg px-3 py-2.5 text-left transition-colors ${
          isSelected
            ? "bg-surface text-text-primary"
            : "text-text-secondary hover:bg-surface/50 hover:text-text-primary"
        }`}
      >
        <div className="mt-0.5 shrink-0 rounded-md p-1.5 bg-accent-teal/10 text-accent-teal">
          <Wrench size={13} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{skill.name}</p>
          <p className="mt-0.5 truncate text-[11px] text-text-muted">{skill.id}</p>
        </div>
        {files.length > 0 && (
          <div className="mt-0.5 flex shrink-0 items-center gap-0.5 text-text-muted">
            <Paperclip size={11} />
            <span className="text-[10px]">{files.length}</span>
            {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </div>
        )}
      </button>

      {expanded && files.length > 0 && (
        <div className="mb-1 ml-[42px] mr-2 rounded-md border border-border/30 bg-charcoal/50">
          {files.map((file, i) => {
            const { Icon, color } = fileIcon(file.name);
            return (
              <button
                key={file.name}
                onClick={() => onFileClick(skill.id, file.name)}
                className={`flex w-full items-center gap-2 px-2.5 py-1.5 text-left transition-colors hover:bg-surface/60 ${
                  i > 0 ? "border-t border-border/20" : ""
                }`}
              >
                <Icon size={11} className={`shrink-0 ${color}`} />
                <span
                  className={`min-w-0 flex-1 truncate text-[11px] ${
                    file.name === "SKILL.md"
                      ? "font-medium text-accent-teal"
                      : file.name === "LICENSE"
                        ? "text-yellow-500/80"
                        : "text-text-secondary"
                  }`}
                >
                  {file.name}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </li>
  );
}

function FileViewer({ skillId, skillName, filename, onClose }) {
  const [content, setContent] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { Icon, color } = fileIcon(filename);

  useEffect(() => {
    let cancelled = false;
    fetchSkillFileContent(skillId, filename)
      .then((data) => {
        if (!cancelled) setContent(data.content);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [skillId, filename]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-border/40 px-5 py-3">
        <button
          onClick={onClose}
          className="text-sm font-medium text-text-secondary transition-colors hover:text-accent-teal"
        >
          {skillName}
        </button>
        <ChevronRight size={14} className="text-text-muted" />
        <Icon size={15} className={color} />
        <h3 className="text-sm font-medium text-text-primary">{filename}</h3>
      </div>

      <div className="flex-1 overflow-auto p-5">
        <div className="mx-auto max-w-2xl">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 size={20} className="animate-spin text-accent-teal" />
            </div>
          ) : error ? (
            <div className="flex items-center gap-2 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">
              <AlertCircle size={13} />
              {error}
            </div>
          ) : (
            <pre
              className={`whitespace-pre-wrap rounded-lg border border-border/60 bg-[#2a2c31] p-4 text-sm leading-relaxed text-text-primary shadow-[0_2px_12px_rgba(0,0,0,0.25)] ${
                isMonoFile(filename) ? "font-mono text-xs" : ""
              }`}
            >
              {content}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}

function SkillEditor({ skill, onSaved, onDeleted, viewingFile, onViewFile }) {
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

export default function SkillsView({ onSkillsChanged }) {
  const [skills, setSkills] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [viewingFile, setViewingFile] = useState(null);
  const [search, setSearch] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [showTrain, setShowTrain] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchSkills()
      .then((data) => {
        if (!cancelled) {
          setSkills(data);
          setSelectedId((prev) => prev ?? (data.length > 0 ? data[0].id : null));
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const filtered = skills.filter(
    (s) =>
      s.name.toLowerCase().includes(search.toLowerCase()) ||
      s.id.toLowerCase().includes(search.toLowerCase()),
  );

  const selectedSkill = skills.find((s) => s.id === selectedId);

  const handleSelectSkill = (id) => {
    setViewingFile(null);
    setSelectedId(id);
  };

  const handleFileClick = (skillId, filename) => {
    setSelectedId(skillId);
    setViewingFile(filename);
  };

  const handleCreated = (skill) => {
    setSkills((prev) => [...prev, skill]);
    setSelectedId(skill.id);
    setViewingFile(null);
    onSkillsChanged?.();
  };

  const handleTrained = async (newSkills) => {
    const refreshed = await fetchSkills();
    setSkills(refreshed);
    if (newSkills.length > 0) {
      setSelectedId(newSkills[0].id);
      setViewingFile(null);
    }
    onSkillsChanged?.();
  };

  const handleSaved = (updated) => {
    setSkills((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
  };

  const handleDeleted = (id) => {
    setSkills((prev) => prev.filter((s) => s.id !== id));
    setSelectedId((prev) => {
      if (prev !== id) return prev;
      const remaining = skills.filter((s) => s.id !== id);
      return remaining.length > 0 ? remaining[0].id : null;
    });
    onSkillsChanged?.();
  };

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <Loader2 size={24} className="animate-spin text-accent-teal" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="flex items-center gap-2 text-sm text-red-400">
          <AlertCircle size={16} />
          {error}
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="flex flex-1 overflow-hidden pt-12 lg:pt-0">
        {/* Skill list panel */}
        <div className="flex w-[280px] shrink-0 flex-col border-r border-border/40 bg-charcoal/30">
          <div className="border-b border-border/40 p-3">
            <div className="mb-2.5 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Wrench size={15} className="text-accent-teal" />
                <h2 className="text-sm font-semibold text-text-primary">Skills</h2>
                <span className="rounded-full bg-surface px-1.5 py-0.5 text-[10px] text-text-muted">
                  {skills.length}
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => setShowTrain(true)}
                  className="flex items-center gap-1 rounded-lg bg-purple-500/10 px-2 py-1 text-xs font-medium text-purple-400 transition-colors hover:bg-purple-500/20"
                >
                  <Sparkles size={13} />
                  Train
                </button>
                <button
                  onClick={() => setShowCreate(true)}
                  className="flex items-center gap-1 rounded-lg bg-accent-teal/10 px-2 py-1 text-xs font-medium text-accent-teal transition-colors hover:bg-accent-teal/20"
                >
                  <Plus size={13} />
                  New
                </button>
              </div>
            </div>
            <div className="relative">
              <Search
                size={14}
                className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted"
              />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search skills…"
                className="w-full rounded-lg border border-border/40 bg-charcoal py-1.5 pl-8 pr-3 text-xs text-text-primary placeholder:text-text-muted outline-none transition-colors focus:border-accent-teal"
              />
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-2">
            {filtered.length === 0 ? (
              <p className="px-3 py-6 text-center text-xs text-text-muted">
                {search ? "No matching skills" : "No skills yet"}
              </p>
            ) : (
              <ul className="space-y-0.5">
                {filtered.map((skill) => (
                  <SkillListItem
                    key={skill.id}
                    skill={skill}
                    isSelected={skill.id === selectedId}
                    onSelect={handleSelectSkill}
                    onFileClick={handleFileClick}
                  />
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* Skill detail / editor */}
        <div className="flex flex-1 flex-col bg-workspace">
          {selectedSkill ? (
            <SkillEditor
              key={selectedSkill.id}
              skill={selectedSkill}
              onSaved={handleSaved}
              onDeleted={handleDeleted}
              viewingFile={viewingFile}
              onViewFile={setViewingFile}
            />
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center">
              <Wrench size={40} className="text-text-muted" />
              <div>
                <p className="text-sm font-medium text-text-primary">
                  {skills.length === 0 ? "No skills yet" : "Select a skill"}
                </p>
                <p className="mt-1 text-xs text-text-muted">
                  {skills.length === 0
                    ? "Create your first custom skill to get started."
                    : "Choose a skill from the list to view or edit it."}
                </p>
              </div>
              {skills.length === 0 && (
                <button
                  onClick={() => setShowCreate(true)}
                  className="mt-2 flex items-center gap-1.5 rounded-lg bg-accent-teal px-4 py-2 text-sm font-medium text-charcoal transition-colors hover:bg-accent-light"
                >
                  <Plus size={15} />
                  Create Skill
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      <CreateSkillModal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onCreated={handleCreated}
      />
      <TrainSkillModal
        open={showTrain}
        onClose={() => setShowTrain(false)}
        onTrained={handleTrained}
      />
    </>
  );
}
