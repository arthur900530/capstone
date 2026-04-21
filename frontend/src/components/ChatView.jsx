import { useMemo, useState } from "react";
import { Bot, BarChart3, Database } from "lucide-react";
import ChatMessage from "./ChatMessage";
import InputBox from "./InputBox";
import UploadedDataPanel from "./DataContext";
import WelcomeHeader from "./WelcomeHeader";
import { useApp } from "../context/AppContext";

function AgentBanner({ agent, onViewEval, files = [], onRemoveFile }) {
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

export default function ChatView({ showWelcome = true }) {
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
    handleSubmit,
    handleViewEval,
    scrollContainerRef,
    updateVisibleAgent,
    messagesEndRef,
    registerSentinel,
    handleCanvasSelectFile,
  } = useApp();

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
        />
        <div className="px-4 pt-4 pb-4">
          <div className="mx-auto max-w-2xl space-y-3">
            {messages.map((msg, i) =>
              msg.type === "agent_marker" ? (
                <AgentDivider
                  key={`${sessionId}-${i}`}
                  agent={msg.agent}
                  sentinelRef={(el) => registerSentinel(i, el, msg.agent)}
                />
              ) : (
                <ChatMessage
                  key={`${sessionId}-${i}`}
                  message={msg}
                  animate={msg.animate !== false}
                  onFileEditClick={(m) => {
                    if (m.path) handleCanvasSelectFile(m.path);
                  }}
                />
              ),
            )}
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

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {chatColumn}
    </div>
  );
}
