import { useState, useRef, useEffect, useMemo } from "react";
import {
  Plus,
  Paperclip,
  ChevronDown,
  ArrowUp,
  Loader2,
  X,
  Wrench,
  Check,
  FolderOpen,
  Globe,
  GlobeLock,
} from "lucide-react";
import { fetchAgents, pickWorkspaceDirectory } from "../services/api";

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
  mountDir = "",
  onMountDirChange,
  hideSkillPicker = true,
  hideModelPicker = false,
  models: modelsProp,
  showBrowserToggle = false,
  browserVisible = false,
  onToggleBrowser,
}) {
  const [text, setText] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const [showModelPicker, setShowModelPicker] = useState(false);
  const [showSkillPicker, setShowSkillPicker] = useState(false);
  const [showWorkspacePicker, setShowWorkspacePicker] = useState(false);
  const [workspaceInput, setWorkspaceInput] = useState("");
  const [workspacePickerLoading, setWorkspacePickerLoading] = useState(false);
  const [workspacePickerError, setWorkspacePickerError] = useState("");
  const [pendingSubmit, setPendingSubmit] = useState(null);
  const fileInputRef = useRef(null);
  const modelRef = useRef(null);
  const skillRef = useRef(null);
  const workspaceRef = useRef(null);

  const [fetchedModels, setFetchedModels] = useState([]);

  // Source model options from the backend (via /api/agents) so the picker only
  // shows models the server actually supports. A `models` prop takes priority.
  useEffect(() => {
    if (Array.isArray(modelsProp) && modelsProp.length > 0) return;
    let cancelled = false;
    fetchAgents()
      .then((list) => {
        if (cancelled) return;
        const deduped = Array.from(
          new Set((list ?? []).map((a) => a?.model).filter(Boolean))
        );
        setFetchedModels(deduped);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [modelsProp]);

  const availableModels = useMemo(() => {
    if (Array.isArray(modelsProp) && modelsProp.length > 0) return modelsProp;
    return fetchedModels;
  }, [modelsProp, fetchedModels]);

  // If the current config.model isn't in the available list, snap to the first.
  useEffect(() => {
    if (availableModels.length === 0) return;
    if (!config?.model || !availableModels.includes(config.model)) {
      onConfigChange?.({ ...(config ?? {}), model: availableModels[0] });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [availableModels]);

  const files = stagedFiles ?? [];

  const closeAllPopups = () => {
    setShowModelPicker(false);
    setShowSkillPicker(false);
    setShowWorkspacePicker(false);
  };
  const selectedSkills = skills.filter((s) => selectedSkillIds.includes(s.id));

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

  const handleBrowseNative = async () => {
    if (workspacePickerLoading) return;
    setWorkspacePickerLoading(true);
    setWorkspacePickerError("");
    try {
      const result = await pickWorkspaceDirectory();
      if (result?.cancelled) return;
      if (result?.path) {
        onMountDirChange?.(result.path);
        setWorkspaceInput(result.path);
        setShowWorkspacePicker(false);
      }
    } catch (err) {
      setWorkspacePickerError(
        err?.message || "Could not open native folder picker"
      );
    } finally {
      setWorkspacePickerLoading(false);
    }
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

  const displayModel = config?.model
    ? config.model.split("/").pop()
    : availableModels[0]
    ? availableModels[0].split("/").pop()
    : "…";

  return (
    <div className="mx-auto w-full max-w-6xl px-4">
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

        {mountDir && (
          <div className="flex flex-wrap gap-1.5 px-5 pt-3">
            <span className="flex items-center gap-1.5 rounded-md bg-accent-deep/15 px-2.5 py-1 text-[11px] font-medium text-accent-deep">
              <FolderOpen size={11} />
              {mountDir}
              <button
                onClick={() => onMountDirChange?.("")}
                className="ml-0.5 text-accent-deep/60 hover:text-accent-deep"
              >
                <X size={11} />
              </button>
            </span>
          </div>
        )}

        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setIsFocused(false)}
          onKeyDown={handleKeyDown}
          placeholder={isStreaming ? "Agent is thinking..." : ""}
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

            {!hideSkillPicker && (
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
            )}

            <div className="relative" ref={workspaceRef}>
              <button
                onClick={() => {
                  setShowWorkspacePicker(!showWorkspacePicker);
                  setShowModelPicker(false);
                  setShowSkillPicker(false);
                  if (!showWorkspacePicker) setWorkspaceInput(mountDir);
                }}
                className={`flex h-8 items-center gap-1 rounded-lg px-2 transition-colors hover:bg-surface-hover ${
                  mountDir
                    ? "text-accent-deep"
                    : "text-text-muted hover:text-text-secondary"
                }`}
              >
                <FolderOpen size={14} />
                <span className="text-xs">Workspace</span>
              </button>

              {showWorkspacePicker && (
                <div className="absolute bottom-10 left-0 z-50 w-80 rounded-xl border border-border bg-charcoal shadow-xl">
                  <div className="flex items-center justify-between px-3 py-2.5 border-b border-border/50">
                    <span className="text-xs font-medium text-text-primary">Mount Directory</span>
                    <button onClick={() => setShowWorkspacePicker(false)} className="text-text-muted hover:text-text-primary">
                      <X size={14} />
                    </button>
                  </div>
                  <div className="p-3">
                    <p className="mb-2 text-[11px] text-text-muted">
                      Folder to mount into the agent container
                    </p>

                    <button
                      onClick={handleBrowseNative}
                      disabled={workspacePickerLoading}
                      className="flex w-full items-center justify-center gap-2 rounded-lg bg-accent-teal px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-accent-teal/90 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {workspacePickerLoading ? (
                        <Loader2 size={13} className="animate-spin" />
                      ) : (
                        <FolderOpen size={13} />
                      )}
                      {workspacePickerLoading ? "Waiting for dialog…" : "Browse…"}
                    </button>

                    {workspacePickerError && (
                      <p className="mt-2 text-[11px] text-red-400">
                        {workspacePickerError}
                      </p>
                    )}

                    {mountDir && (
                      <div className="mt-3 rounded-lg border border-border/60 bg-surface px-2.5 py-2">
                        <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-text-muted">
                          Current
                        </div>
                        <div className="mt-0.5 break-all text-[11px] text-text-primary">
                          {mountDir}
                        </div>
                      </div>
                    )}

                    <div className="mt-3 flex items-center gap-2">
                      <div className="h-px flex-1 bg-border/60" />
                      <span className="text-[10px] uppercase tracking-[0.14em] text-text-muted">
                        or type a path
                      </span>
                      <div className="h-px flex-1 bg-border/60" />
                    </div>

                    <div className="mt-2 flex gap-2">
                      <input
                        type="text"
                        value={workspaceInput}
                        onChange={(e) => setWorkspaceInput(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            onMountDirChange?.(workspaceInput.trim());
                            setShowWorkspacePicker(false);
                          }
                        }}
                        placeholder="/path/to/project"
                        className="flex-1 rounded-lg border border-border bg-surface px-3 py-1.5 text-xs text-text-primary placeholder-text-muted outline-none focus:border-accent-teal/50"
                      />
                      <button
                        onClick={() => {
                          onMountDirChange?.(workspaceInput.trim());
                          setShowWorkspacePicker(false);
                        }}
                        className="rounded-lg border border-border bg-surface px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:bg-surface-hover hover:text-text-primary"
                      >
                        Set
                      </button>
                    </div>

                    {mountDir && (
                      <button
                        onClick={() => {
                          onMountDirChange?.("");
                          setWorkspaceInput("");
                          setShowWorkspacePicker(false);
                        }}
                        className="mt-2 text-[11px] text-text-muted hover:text-red-400 transition-colors"
                      >
                        Clear workspace
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {showBrowserToggle && (
              <button
                type="button"
                onClick={onToggleBrowser}
                title={browserVisible ? "Hide live browser" : "Show live browser"}
                className={`flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium transition-colors ${
                  browserVisible
                    ? "bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30"
                    : "text-text-muted hover:bg-surface-hover hover:text-text-secondary"
                }`}
              >
                {browserVisible ? <Globe size={13} /> : <GlobeLock size={13} />}
                Live Browser
              </button>
            )}

            {!hideModelPicker && (
            <>
            <button
              type="button"
              role="switch"
              aria-checked={Boolean(config?.useReflexion)}
              onClick={() =>
                onConfigChange?.({ ...config, useReflexion: !config?.useReflexion })
              }
              title="Enable Reflexion (evaluate, reflect, retry on failure)"
              className={`flex h-8 items-center gap-2 rounded-lg px-2.5 text-xs font-medium transition-colors ${
                config?.useReflexion
                  ? "bg-accent-teal/20 text-accent-teal"
                  : "text-text-muted hover:bg-surface-hover hover:text-text-secondary"
              }`}
            >
              <span
                className={`relative inline-flex h-4 w-7 shrink-0 items-center rounded-full transition-colors ${
                  config?.useReflexion ? "bg-accent-teal" : "bg-border"
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 h-3 w-3 rounded-full bg-white shadow transition-transform ${
                    config?.useReflexion ? "translate-x-3" : "translate-x-0"
                  }`}
                />
              </span>
              Reflexion
            </button>

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
                  {availableModels.length === 0 ? (
                    <div className="px-4 py-2 text-xs text-text-muted">
                      No models available
                    </div>
                  ) : (
                    availableModels.map((m) => (
                      <button
                        key={m}
                        onClick={() => {
                          onConfigChange?.({ ...config, model: m });
                          setShowModelPicker(false);
                        }}
                        className={`flex w-full items-center gap-2 px-4 py-2 text-left text-xs transition-colors hover:bg-surface ${
                          config?.model === m ? "text-accent-teal" : "text-text-secondary"
                        }`}
                      >
                        <div className={`h-2 w-2 rounded-full ${config?.model === m ? "bg-accent-teal" : "bg-border"}`} />
                        {m}
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>
            </>
            )}

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
