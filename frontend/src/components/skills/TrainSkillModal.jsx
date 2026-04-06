import { useState, useEffect, useRef } from "react";
import { Loader2, AlertCircle, X, Upload, Paperclip, Sparkles, CheckCircle } from "lucide-react";
import { trainSkillsFromMedia } from "../../services/api";

const MEDIA_ACCEPT =
  "video/*,audio/*,text/*,.md,.py,.sh,.json,.yaml,.yml,.csv,.txt,.mp4,.mov,.mp3,.wav,.m4a,.webm";

export default function TrainSkillModal({ open, onClose, onTrained }) {
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
