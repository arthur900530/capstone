import { FileText, X } from "lucide-react";

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function UploadedDataPanel({ files = [], onRemoveFile }) {
  if (files.length === 0) return null;

  return (
    <div className="border-t border-border/20 px-4 pb-3 pt-2">
      <div className="mx-auto flex max-w-2xl flex-wrap gap-2">
        {files.map((f, i) => (
          <span
            key={`${f.name}-${i}`}
            className="group flex items-center gap-1.5 rounded-lg bg-surface-hover px-2.5 py-1.5 text-xs text-text-secondary"
          >
            <FileText size={12} className="shrink-0 text-text-muted" />
            <span className="max-w-[180px] truncate">{f.name}</span>
            {f.size != null && (
              <span className="text-text-muted">{formatSize(f.size)}</span>
            )}
            {onRemoveFile && (
              <button
                onClick={() => onRemoveFile(i)}
                className="ml-0.5 text-text-muted opacity-0 transition-opacity hover:text-text-primary group-hover:opacity-100"
              >
                <X size={12} />
              </button>
            )}
          </span>
        ))}
      </div>
    </div>
  );
}
