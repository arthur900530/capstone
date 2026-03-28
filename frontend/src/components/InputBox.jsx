import { useState, useRef } from "react";
import {
  Plus,
  Paperclip,
  ChevronDown,
  ArrowUp,
  Loader2,
} from "lucide-react";

const MODEL_OPTIONS = [
  "openai/gpt-5.1",
  "openai/gpt-4o",
  "openai/gpt-4o-mini",
  "anthropic/claude-sonnet-4-5-20250929",
  "anthropic/claude-3-5-haiku-20241022",
];

export default function InputBox({
  onSubmit,
  isStreaming,
  config,
  onConfigChange,
  stagedFiles,
  onFilesChange,
}) {
  const [text, setText] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const [showModelPicker, setShowModelPicker] = useState(false);
  const fileInputRef = useRef(null);
  const modelRef = useRef(null);

  const files = stagedFiles ?? [];

  const handleFileChange = (e) => {
    const picked = Array.from(e.target.files);
    onFilesChange?.([...files, ...picked]);
    e.target.value = "";
  };

  const removeFile = (index) => {
    onFilesChange?.(files.filter((_, i) => i !== index));
  };

  const handleSubmit = () => {
    if (!text.trim() || isStreaming) return;
    setShowModelPicker(false);
    onSubmit(text.trim(), [...files]);
    setText("");
    onFilesChange?.([]);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const displayModel = config.model
    ? config.model.split("/").pop()
    : "openai/gpt-5.1";

  return (
    <div className="mx-auto w-full max-w-4xl px-4">
      <div
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        className={`
          relative rounded-2xl bg-surface transition-all duration-200
          ${isFocused
            ? "ring-1 ring-accent-teal/60 shadow-[0_0_20px_rgba(45,155,173,0.15)]"
            : isHovered
              ? "ring-1 ring-accent-teal/30 shadow-[0_0_10px_rgba(45,155,173,0.08)]"
              : "ring-1 ring-border"
          }
        `}
      >
        {files.length > 0 && (
          <div className="flex flex-wrap gap-2 px-5 pt-4">
            {files.map((file, i) => (
              <span
                key={i}
                className="flex items-center gap-1.5 rounded-lg bg-surface-hover px-3 py-1.5 text-xs text-text-secondary"
              >
                <Paperclip size={12} />
                {file.name}
                <button
                  onClick={() => removeFile(i)}
                  className="ml-1 text-text-muted hover:text-text-primary"
                >
                  &times;
                </button>
              </span>
            ))}
          </div>
        )}

        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setIsFocused(false)}
          onKeyDown={handleKeyDown}
          placeholder={isStreaming ? "Agent is thinking..." : "Ask a financial question..."}
          rows={3}
          disabled={isStreaming}
          className="w-full resize-none bg-transparent px-5 pt-4 pb-14 text-sm text-text-primary placeholder-text-muted outline-none disabled:opacity-50"
        />

        <input
          ref={fileInputRef}
          type="file"
          multiple
          onChange={handleFileChange}
          className="hidden"
        />

        <div className="absolute right-3 bottom-3 left-3 flex items-center justify-between">
          <div className="flex items-center gap-1">
            <button
              onClick={() => fileInputRef.current?.click()}
              className="flex h-8 items-center gap-1 rounded-lg px-2 text-text-muted transition-colors hover:bg-surface-hover hover:text-text-secondary"
            >
              <Plus size={16} />
              <span className="text-xs">Files</span>
            </button>

          </div>

          <div className="flex items-center gap-2">
            <div className="relative" ref={modelRef}>
              <button
                onClick={() => {
                  setShowModelPicker(!showModelPicker);
                }}
                className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:bg-surface-hover"
              >
                <div className="h-3.5 w-3.5 rounded-full bg-gradient-to-br from-accent-deep to-accent-teal" />
                {displayModel}
                <ChevronDown size={14} className="text-text-muted" />
              </button>
              {showModelPicker && (
                <div className="absolute right-0 bottom-10 z-50 w-72 rounded-xl border border-border bg-charcoal py-1 shadow-xl">
                  {MODEL_OPTIONS.map((m) => (
                    <button
                      key={m}
                      onClick={() => {
                        onConfigChange({ ...config, model: m });
                        setShowModelPicker(false);
                      }}
                      className={`flex w-full items-center gap-2 px-4 py-2 text-left text-xs transition-colors hover:bg-surface ${
                        config.model === m ? "text-accent-teal" : "text-text-secondary"
                      }`}
                    >
                      <div className={`h-2 w-2 rounded-full ${config.model === m ? "bg-accent-teal" : "bg-border"}`} />
                      {m}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <button
              onClick={handleSubmit}
              disabled={isStreaming || !text.trim()}
              className={`
                flex h-8 w-8 items-center justify-center rounded-lg transition-all
                ${isStreaming
                  ? "bg-surface-hover text-accent-teal"
                  : text.trim()
                    ? "bg-accent-teal text-white"
                    : "bg-surface-hover text-text-muted"
                }
              `}
            >
              {isStreaming ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <ArrowUp size={16} />
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
