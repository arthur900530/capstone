import { useState, useEffect } from "react";
import { Loader2, AlertCircle, ChevronRight } from "lucide-react";
import { fetchSkillFileContent } from "../../services/api";
import { fileIcon, isMonoFile } from "./utils";

export default function FileViewer({ skillId, skillName, filename, onClose }) {
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
