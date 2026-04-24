import { useMemo, useState } from "react";
import { Bot, BarChart3, Database, Globe, GlobeLock } from "lucide-react";
import ChatMessage from "./ChatMessage";
import InputBox from "./InputBox";
import UploadedDataPanel from "./DataContext";
import WelcomeHeader from "./WelcomeHeader";
import BrowserLiveView from "./BrowserLiveView";
import { useApp } from "../context/AppContext";

const LIVE_BROWSER_ENABLED = import.meta.env.VITE_LIVE_BROWSER !== "false";
const IS_DEMO = import.meta.env.VITE_DEMO === "true";

function AgentBanner({
  agent,
  onViewEval,
  files = [],
  onRemoveFile,
  showBrowserToggle = false,
  browserVisible = false,
  onToggleBrowser,
}) {
  const [showData, setShowData] = useState(false);

  if (!agent) return null;
  return (
    <div className="sticky top-0 z-20 border-b border-border/30 bg-workspace/95 backdrop-blur-sm">
      <div className="mx-auto flex max-w-2xl items-center justify-between px-4 py-2.5">
        <div className="flex items-center gap-2 text-sm">
          <Bot size={15} className="text-accent-teal" />
          <span className="font-medium text-text-primary">{agent.name}</span>
          <span className="text-text-muted">&middot;</span>
          <span className="text-xs text-text-muted">
            {agent.model?.split("/").pop()}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {files.length > 0 && (
            <button
              onClick={() => setShowData((v) => !v)}
              className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                showData
                  ? "bg-accent-teal/20 text-accent-teal"
                  : "bg-surface-hover text-text-secondary hover:text-text-primary"
              }`}
            >
              <Database size={13} />
              Uploaded Data
              <span className="rounded-full bg-accent-teal/15 px-1.5 py-0.5 text-[10px] font-semibold text-accent-teal">
                {files.length}
              </span>
            </button>
          )}
          {showBrowserToggle && (
            <button
              onClick={onToggleBrowser}
              className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                browserVisible
                  ? "bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30"
                  : "bg-surface-hover text-text-secondary hover:text-text-primary"
              }`}
              title={
                browserVisible ? "Hide live browser" : "Show live browser"
              }
            >
              {browserVisible ? <Globe size={13} /> : <GlobeLock size={13} />}
              Live Browser
            </button>
          )}
          {onViewEval && (
            <button
              onClick={onViewEval}
              className="flex items-center gap-1.5 rounded-md bg-accent-teal/10 px-2.5 py-1 text-xs font-medium text-accent-teal transition-colors hover:bg-accent-teal/20"
            >
              <BarChart3 size={13} />
              Evaluation
            </button>
          )}
        </div>
      </div>
      {showData && (
        <UploadedDataPanel files={files} onRemoveFile={onRemoveFile} />
      )}
    </div>
  );
}

function AgentDivider({ agent, sentinelRef }) {
  return (
    <div ref={sentinelRef} className="flex items-center gap-3 py-1">
      <div className="h-px flex-1 bg-border/40" />
      <span className="flex items-center gap-1.5 text-[10px] font-medium text-text-muted">
        <Bot size={11} />
        {agent.name}
      </span>
      <div className="h-px flex-1 bg-border/40" />
    </div>
  );
}

export default function ChatView({ showWelcome = true, embedded = false }) {
  const {
    messages,
    isStreaming,
    sessionId,
    visibleAgent,
    chatFiles,
    setChatFiles,
    stagedFiles,
    setStagedFiles,
    config,
    setConfig,
    skills,
    selectedSkillIds,
    setSelectedSkillIds,
    skipSkillConfirm,
    setSkipSkillConfirm,
    mountDir,
    setMountDir,
    agents,
    browserLive,
    setBrowserLive,
    handleSubmit,
    handleViewEval,
    scrollContainerRef,
    updateVisibleAgent,
    messagesEndRef,
    registerSentinel,
    handleCanvasSelectFile,
    ratings,
    currentEmployeeId,
  } = useApp();

  const liveBrowserAvailable = LIVE_BROWSER_ENABLED && !IS_DEMO;

  const toggleBrowserVisible = () => {
    if (!setBrowserLive) return;
    setBrowserLive((prev) => ({ ...prev, visible: !prev?.visible }));
  };

  // When `embedded` is true, the parent (e.g. EmployeePage) manages its own
  // split layout and renders BrowserLiveView itself, so we must not double it.
  const showBrowserPanel =
    !embedded && liveBrowserAvailable && browserLive?.visible;

  const hasMessages = messages.length > 0;

  const availableModels = useMemo(
    () =>
      Array.from(
        new Set((agents ?? []).map((a) => a?.model).filter(Boolean))
      ),
    [agents]
  );

  const chatColumn = hasMessages ? (
    <>
      <div
        ref={scrollContainerRef}
        onScroll={updateVisibleAgent}
        className="flex-1 overflow-y-auto"
      >
        <AgentBanner
          agent={visibleAgent}
          onViewEval={() => handleViewEval(visibleAgent?.id)}
          files={chatFiles}
          onRemoveFile={(i) =>
            setChatFiles((prev) => prev.filter((_, idx) => idx !== i))
          }
          showBrowserToggle={liveBrowserAvailable}
          browserVisible={Boolean(browserLive?.visible)}
          onToggleBrowser={toggleBrowserVisible}
        />
        <div className="px-4 pt-4 pb-4">
          <div className="mx-auto max-w-2xl space-y-3">
            {(() => {
              // Walk user turns so each answer can be keyed to the task it
              // closes, even if the server didn't embed ``task_index`` in
              // the SSE payload (e.g. legacy chat history).
              let userTurns = -1;
              return messages.map((msg, i) => {
                if (msg.type === "user") userTurns += 1;
                if (msg.type === "agent_marker") {
                  return (
                    <AgentDivider
                      key={`${sessionId}-${i}`}
                      agent={msg.agent}
                      sentinelRef={(el) => registerSentinel(i, el, msg.agent)}
                    />
                  );
                }
                const resolvedTaskIndex =
                  typeof msg.taskIndex === "number"
                    ? msg.taskIndex
                    : userTurns >= 0
                      ? userTurns
                      : undefined;
                const enriched =
                  msg.type === "answer" || msg.type === "chat_response"
                    ? { ...msg, taskIndex: resolvedTaskIndex }
                    : msg;
                const ratingForMsg =
                  currentEmployeeId && Number.isInteger(resolvedTaskIndex)
                    ? (ratings && ratings[resolvedTaskIndex]) ?? null
                    : null;
                return (
                  <ChatMessage
                    key={`${sessionId}-${i}`}
                    message={enriched}
                    animate={msg.animate !== false}
                    onFileEditClick={(m) => {
                      if (m.path) handleCanvasSelectFile(m.path);
                    }}
                    employeeId={currentEmployeeId || undefined}
                    sessionId={sessionId || undefined}
                    rating={ratingForMsg}
                  />
                );
              });
            })()}
            <div ref={messagesEndRef} />
          </div>
        </div>
      </div>
      <div className="border-t border-border/30 bg-workspace pb-4 pt-3">
        <InputBox
          onSubmit={handleSubmit}
          isStreaming={isStreaming}
          config={config}
          onConfigChange={setConfig}
          stagedFiles={stagedFiles}
          onFilesChange={setStagedFiles}
          skills={skills}
          selectedSkillIds={selectedSkillIds}
          onSelectedSkillsChange={setSelectedSkillIds}
          skipConfirm={skipSkillConfirm}
          onSkipConfirmChange={setSkipSkillConfirm}
          mountDir={mountDir}
          onMountDirChange={setMountDir}
          models={availableModels}
        />
      </div>
    </>
  ) : (
    <>
      <div className="flex flex-1 flex-col items-center justify-center">
        <div className="w-full">
          {showWelcome && <WelcomeHeader />}
          <InputBox
            onSubmit={handleSubmit}
            isStreaming={isStreaming}
            config={config}
            onConfigChange={setConfig}
            stagedFiles={stagedFiles}
            onFilesChange={setStagedFiles}
            skills={skills}
            selectedSkillIds={selectedSkillIds}
            onSelectedSkillsChange={setSelectedSkillIds}
            skipConfirm={skipSkillConfirm}
            onSkipConfirmChange={setSkipSkillConfirm}
            mountDir={mountDir}
            onMountDirChange={setMountDir}
            models={availableModels}
          />
        </div>
      </div>
      <footer className="pb-4 text-center text-xs text-text-muted">
        AI may produce inaccurate information. Verify important facts.
      </footer>
    </>
  );

  if (showBrowserPanel) {
    return (
      <div className="flex flex-1 overflow-hidden">
        <div className="flex min-w-0 flex-1 flex-col border-r border-border/20 transition-all duration-300 lg:max-w-[50%]">
          {chatColumn}
        </div>
        <div className="hidden flex-1 flex-col lg:flex">
          <BrowserLiveView sessionId={sessionId || browserLive?.sessionId} />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {chatColumn}
    </div>
  );
}
