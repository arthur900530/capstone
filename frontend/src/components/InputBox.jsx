import { useState, useRef, useEffect } from "react";
import {
  Plus,
  Paperclip,
  ChevronDown,
  ArrowUp,
  Loader2,
  X,
  Wrench,
  Check,
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
  skills = [],
  selectedSkillIds = [],
  onSelectedSkillsChange,
  skipConfirm = false,
  onSkipConfirmChange,
}) {
  const [text, setText] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const [showModelPicker, setShowModelPicker] = useState(false);
  const [showSkillPicker, setShowSkillPicker] = useState(false);
  const [pendingSubmit, setPendingSubmit] = useState(null);
  const fileInputRef = useRef(null);
  const modelRef = useRef(null);
  const skillRef = useRef(null);

  const files = stagedFiles ?? [];

  const closeAllPopups = () => {
    setShowModelPicker(false);
    setShowSkillPicker(false);
  };

  const toggleSkill = (skillId) => {
    onSelectedSkillsChange?.(
      selectedSkillIds.includes(skillId)
        ? selectedSkillIds.filter((id) => id !== skillId)
        : [...selectedSkillIds, skillId]
    );
  };

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
    closeAllPopups();
    if (skipConfirm) {
      onSubmit(text.trim(), [...files]);
      setText("");
      onFilesChange?.([]);
      return;
    }
    setPendingSubmit({ text: text.trim(), files: [...files] });
  };

  const handleConfirm = () => {
    if (!pendingSubmit) return;
    onSubmit(pendingSubmit.text, pendingSubmit.files);
    setText("");
    onFilesChange?.([]);
    setPendingSubmit(null);
  };

  const handleCancelConfirm = () => {
    setPendingSubmit(null);
  };

  useEffect(() => {
    if (!pendingSubmit) return;
    const onKeyDown = (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        setPendingSubmit(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [pendingSubmit]);

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const displayModel = config.model
    ? config.model.split("/").pop()
    : "openai/gpt-5.1";

  const selectedSkills = skills.filter((s) => selectedSkillIds.includes(s.id));

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

        {selectedSkillIds.length > 0 && (
          <div className="flex flex-wrap gap-1.5 px-5 pt-3">
            {selectedSkills.map((skill) => (
              <span
                key={skill.id}
                className="flex items-center gap-1.5 rounded-md bg-accent-teal/10 px-2.5 py-1 text-[11px] font-medium text-accent-teal"
              >
                <Wrench size={11} />
                {skill.name}
                <button
                  onClick={() => toggleSkill(skill.id)}
                  className="ml-0.5 text-accent-teal/60 hover:text-accent-teal"
                >
                  <X size={11} />
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

            <div className="relative" ref={skillRef}>
              <button
                onClick={() => {
                  setShowSkillPicker(!showSkillPicker);
                  setShowModelPicker(false);
                }}
                className={`flex h-8 items-center gap-1 rounded-lg px-2 transition-colors hover:bg-surface-hover ${
                  selectedSkillIds.length > 0
                    ? "text-accent-teal"
                    : "text-text-muted hover:text-text-secondary"
                }`}
              >
                <Wrench size={14} />
                <span className="text-xs">Skills</span>
                {selectedSkillIds.length > 0 && (
                  <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-accent-teal/20 px-1 text-[10px] font-semibold text-accent-teal">
                    {selectedSkillIds.length}
                  </span>
                )}
              </button>

              {showSkillPicker && (
                <div className="absolute bottom-10 left-0 z-50 w-72 rounded-xl border border-border bg-charcoal shadow-xl">
                  <div className="flex items-center justify-between px-3 py-2.5 border-b border-border/50">
                    <span className="text-xs font-medium text-text-primary">Skills</span>
                    <button onClick={() => setShowSkillPicker(false)} className="text-text-muted hover:text-text-primary">
                      <X size={14} />
                    </button>
                  </div>
                  {skills.length === 0 ? (
                    <p className="px-3 py-4 text-center text-xs text-text-muted">No skills available</p>
                  ) : (
                    <div className="max-h-52 overflow-y-auto py-1">
                      {skills.map((skill) => (
                        <button
                          key={skill.id}
                          onClick={() => toggleSkill(skill.id)}
                          className="flex w-full items-start gap-2.5 px-3 py-2 text-left transition-colors hover:bg-surface"
                        >
                          <div
                            className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors ${
                              selectedSkillIds.includes(skill.id)
                                ? "border-accent-teal bg-accent-teal"
                                : "border-text-muted/50"
                            }`}
                          >
                            {selectedSkillIds.includes(skill.id) && (
                              <Check size={10} className="text-white" />
                            )}
                          </div>
                          <div className="min-w-0">
                            <p className="text-xs font-medium text-text-primary">{skill.name}</p>
                            <p className="truncate text-[11px] text-text-muted">{skill.description}</p>
                          </div>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <div className="relative" ref={modelRef}>
              <button
                onClick={() => {
                  setShowModelPicker(!showModelPicker);
                  setShowSkillPicker(false);
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

      {pendingSubmit && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm"
          onClick={handleCancelConfirm}
        >
          <div
            className="w-full max-w-md rounded-2xl border border-border bg-charcoal p-6 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="mb-1 text-sm font-semibold text-text-primary">
              Confirm Skills
            </h3>
            <p className="mb-4 text-xs text-text-muted">
              Review the skills that will be used for this message.
            </p>

            {selectedSkills.length > 0 ? (
              <div className="mb-5 space-y-2">
                {selectedSkills.map((skill) => (
                  <div
                    key={skill.id}
                    className="flex items-start gap-2.5 rounded-lg bg-surface p-3"
                  >
                    <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-accent-teal/15">
                      <Wrench size={13} className="text-accent-teal" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-text-primary">{skill.name}</p>
                      <p className="mt-0.5 text-[11px] leading-relaxed text-text-muted">
                        {skill.description}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="mb-5 rounded-lg bg-surface px-4 py-3">
                <p className="text-xs text-text-muted">
                  No skills selected. The agent will use its default capabilities.
                </p>
              </div>
            )}

            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={skipConfirm}
                  onChange={(e) => onSkipConfirmChange?.(e.target.checked)}
                  className="h-3.5 w-3.5 rounded border-text-muted/50 accent-accent-teal"
                />
                <span className="text-[11px] text-text-muted">Never ask again</span>
              </label>
              <div className="flex gap-2">
                <button
                  onClick={handleCancelConfirm}
                  className="rounded-lg px-4 py-2 text-xs font-medium text-text-secondary transition-colors hover:bg-surface-hover"
                >
                  Cancel
                </button>
                <button
                  onClick={handleConfirm}
                  className="rounded-lg bg-accent-teal px-4 py-2 text-xs font-medium text-white transition-colors hover:bg-accent-teal/90"
                >
                  Confirm &amp; Send
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
