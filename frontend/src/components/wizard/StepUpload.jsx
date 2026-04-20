import { Upload, X, FileText } from "lucide-react";

export default function StepUpload({ files, onFilesChange, onBack, onNext }) {
  const handleFileChange = (e) => {
    const selected = Array.from(e.target.files || []);
    if (selected.length > 0) {
      onFilesChange([...files, ...selected]);
    }
  };

  const removeFile = (idx) => {
    onFilesChange(files.filter((_, i) => i !== idx));
  };

  return (
    <div className="mx-auto max-w-2xl">
      <h2 className="mb-2 text-xl font-semibold text-text-primary">
        Upload data
      </h2>
      <p className="mb-6 text-sm text-text-muted">
        Optionally provide files your employee should reference. You can skip
        this and upload later.
      </p>

      {/* Drop zone */}
      <label className="flex cursor-pointer flex-col items-center gap-3 rounded-xl border-2 border-dashed border-border/40 bg-surface/50 px-6 py-10 transition-colors hover:border-accent-teal/40 hover:bg-surface">
        <Upload size={28} className="text-text-muted" />
        <span className="text-sm text-text-secondary">
          Click to upload or drag files here
        </span>
        <input
          type="file"
          multiple
          onChange={handleFileChange}
          className="hidden"
        />
      </label>

      {/* File list */}
      {files.length > 0 && (
        <ul className="mt-4 space-y-2">
          {files.map((f, i) => (
            <li
              key={i}
              className="flex items-center justify-between rounded-lg border border-border/30 bg-surface px-4 py-2.5"
            >
              <div className="flex items-center gap-2 text-sm text-text-primary">
                <FileText size={14} className="text-text-muted" />
                <span className="truncate">{f.name}</span>
                <span className="text-xs text-text-muted">
                  ({(f.size / 1024).toFixed(1)} KB)
                </span>
              </div>
              <button
                onClick={() => removeFile(i)}
                className="text-text-muted hover:text-red-400"
              >
                <X size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-8 flex justify-between">
        <button
          onClick={onBack}
          className="rounded-lg border border-border/40 px-6 py-2.5 text-sm font-medium text-text-secondary transition-colors hover:bg-surface"
        >
          Back
        </button>
        <div className="flex items-center gap-3">
          {files.length === 0 && (
            <button
              onClick={onNext}
              className="text-sm text-text-muted hover:text-text-secondary"
            >
              Skip
            </button>
          )}
          <button
            onClick={onNext}
            className="rounded-lg bg-accent-teal px-6 py-2.5 text-sm font-medium text-workspace transition-colors hover:bg-accent-teal/90"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
