import { useCallback, useEffect, useRef, useState } from "react";
import {
  FileText,
  Loader2,
  Paperclip,
  Plus,
  Trash2,
  Upload,
} from "lucide-react";
import {
  deleteProjectFile,
  listProjectFiles,
  projectFileRawUrl,
  uploadProjectFiles,
} from "../../services/api";

function formatSize(bytes) {
  const n = Number(bytes) || 0;
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function EmployeeProjectFilesTab({ employee }) {
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [error, setError] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);

  const refresh = useCallback(async () => {
    try {
      const data = await listProjectFiles(employee.id);
      setFiles(data.files || []);
      setError(null);
    } catch (err) {
      setError(err?.message || "Failed to load project files");
    } finally {
      setLoading(false);
    }
  }, [employee.id]);

  useEffect(() => {
    setLoading(true);
    refresh();
  }, [refresh]);

  const handleUpload = async (incoming) => {
    const list = Array.from(incoming || []).filter(Boolean);
    if (!list.length) return;
    setUploading(true);
    setError(null);
    try {
      const data = await uploadProjectFiles(employee.id, list);
      setFiles(data.files || []);
    } catch (err) {
      setError(err?.message || "Upload failed");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDelete = async (fileId) => {
    setDeletingId(fileId);
    setError(null);
    try {
      const data = await deleteProjectFile(employee.id, fileId);
      setFiles(data.files || []);
    } catch (err) {
      setError(err?.message || "Delete failed");
    } finally {
      setDeletingId(null);
    }
  };

  const onDragOver = (e) => {
    e.preventDefault();
    setDragOver(true);
  };
  const onDragLeave = () => setDragOver(false);
  const onDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer?.files;
    if (dropped?.length) handleUpload(dropped);
  };

  return (
    <div className="mx-auto flex max-w-5xl flex-1 flex-col overflow-y-auto px-6 py-6">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold text-text-primary">
            Project Files
          </h3>
          <p className="mt-1 text-xs text-text-muted">
            These files are always staged into the agent&apos;s workspace at{" "}
            <code className="rounded bg-surface-hover px-1 py-0.5 text-[11px]">
              ./project_files/
            </code>{" "}
            at the start of every turn, so the agent can read them on demand.
            Unlike chat-uploaded files, they persist across every conversation
            with this employee.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => handleUpload(e.target.files)}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="flex items-center gap-1.5 rounded-lg bg-accent-teal px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-accent-teal/90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {uploading ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Plus size={14} />
            )}
            {uploading ? "Uploading…" : "Add files"}
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-3 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-400">
          {error}
        </div>
      )}

      <div
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        className={`mb-4 flex flex-col items-center justify-center rounded-xl border-2 border-dashed px-4 py-6 text-xs transition-colors ${
          dragOver
            ? "border-accent-teal bg-accent-teal/5 text-accent-teal"
            : "border-border/40 text-text-muted"
        }`}
      >
        <Upload size={20} className="mb-2" />
        <span>
          Drag files here or{" "}
          <button
            onClick={() => fileInputRef.current?.click()}
            className="font-medium text-accent-teal hover:underline"
          >
            browse
          </button>
          . All file types are accepted.
        </span>
      </div>

      <div className="rounded-xl border border-border/40 bg-surface">
        {loading ? (
          <div className="flex items-center justify-center px-4 py-10 text-xs text-text-muted">
            <Loader2 size={16} className="mr-2 animate-spin" />
            Loading project files…
          </div>
        ) : files.length === 0 ? (
          <div className="flex flex-col items-center justify-center px-4 py-10 text-center">
            <Paperclip size={20} className="mb-2 text-text-muted" />
            <p className="text-xs text-text-muted">
              No project files yet. Add reference material the agent should
              always have access to — specs, examples, schemas, datasets.
            </p>
          </div>
        ) : (
          <ul className="divide-y divide-border/30">
            {files.map((f) => (
              <li
                key={f.id}
                className="flex items-center gap-3 px-4 py-3 text-xs"
              >
                <FileText size={16} className="shrink-0 text-accent-teal" />
                <div className="min-w-0 flex-1">
                  <a
                    href={projectFileRawUrl(employee.id, f.id)}
                    target="_blank"
                    rel="noreferrer"
                    className="block truncate font-medium text-text-primary hover:text-accent-teal hover:underline"
                    title={f.name}
                  >
                    {f.name}
                  </a>
                  <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-text-muted">
                    <span>{formatSize(f.size)}</span>
                    <span className="truncate" title={f.mime}>
                      {f.mime}
                    </span>
                    {f.uploaded_at && (
                      <span>Uploaded {formatDate(f.uploaded_at)}</span>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => handleDelete(f.id)}
                  disabled={deletingId === f.id}
                  title="Delete file"
                  className="shrink-0 rounded-md p-1.5 text-text-muted transition-colors hover:bg-red-500/10 hover:text-red-400 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {deletingId === f.id ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Trash2 size={14} />
                  )}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
