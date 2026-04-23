import { useMemo } from "react";
import ChatMessage from "./ChatMessage";
import InputBox from "./InputBox";
import WelcomeHeader from "./WelcomeHeader";
import BrowserLiveView from "./BrowserLiveView";
import { useApp } from "../context/AppContext";

const LIVE_BROWSER_ENABLED = import.meta.env.VITE_LIVE_BROWSER !== "false";
const IS_DEMO = import.meta.env.VITE_DEMO === "true";

export default function ChatView({ showWelcome = true, embedded = false }) {
  const {
    messages,
    isStreaming,
    sessionId,
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
    scrollContainerRef,
    messagesEndRef,
    handleCanvasSelectFile,
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
      <div ref={scrollContainerRef} className="flex-1 overflow-y-auto">
        <div className="px-4 pt-4 pb-4">
          <div className="mx-auto max-w-5xl space-y-3">
            {messages.map((msg, i) =>
              msg.type === "agent_marker" ? null : (
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
          showBrowserToggle={liveBrowserAvailable}
          browserVisible={Boolean(browserLive?.visible)}
          onToggleBrowser={toggleBrowserVisible}
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
