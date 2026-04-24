import { useMemo, useState } from "react";
import {
  Brain,
  ChevronDown,
  ChevronRight,
  FileCode2,
  Loader2,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Wrench,
} from "lucide-react";
import ChatMessage from "./ChatMessage";
import InputBox from "./InputBox";
import WelcomeHeader from "./WelcomeHeader";
import BrowserLiveView from "./BrowserLiveView";
import { useApp } from "../context/AppContext";

const LIVE_BROWSER_ENABLED = import.meta.env.VITE_LIVE_BROWSER !== "false";
const IS_DEMO = import.meta.env.VITE_DEMO === "true";

// Intermediate agent events that make up the "trajectory" — collapsed per turn
// behind a per-response toggle so the chat shows only user turns, final
// answers, and errors by default.
const TRAJECTORY_TYPES = new Set([
  "status",
  "trial_start",
  "tool_call",
  "tool_result",
  "reasoning",
  "self_eval",
  "reflection",
  "file_edit",
]);

const TOOL_LABELS = {
  web_search: "Web Search",
  edgar_search: "SEC Filing Search",
  parse_html: "Reading Page",
  retrieve_info: "Analyzing Documents",
  retrieve_information: "Analyzing Documents",
  submit_result: "Submitting Answer",
  submit_final_result: "Submitting Answer",
  finish: "Task Complete",
  FinishTool: "Task Complete",
  terminal: "Terminal",
  file_editor: "File Editor",
  task_tracker: "Task Tracker",
  delegate: "Delegate",
};

// Given a trajectory message, return an icon + short title suitable for the
// collapsed group header.
function describeStep(msg) {
  switch (msg?.type) {
    case "status":
      return { Icon: Loader2, label: msg.content || "Working" };
    case "trial_start":
      return {
        Icon: RefreshCw,
        label: `Trial ${msg.trial}/${msg.maxTrials}`,
      };
    case "tool_call": {
      const name = TOOL_LABELS[msg.tool] || msg.tool || "tool";
      return { Icon: Wrench, label: `Using ${name}` };
    }
    case "tool_result":
      return { Icon: Wrench, label: "Processing tool result" };
    case "reasoning":
      return { Icon: Brain, label: "Reasoning" };
    case "self_eval":
      return { Icon: ShieldCheck, label: "Self-evaluating" };
    case "reflection":
      return { Icon: RefreshCw, label: "Reflecting" };
    case "file_edit": {
      const fname = msg.path?.split("/").pop() || "file";
      const action =
        msg.command === "create"
          ? "Creating"
          : msg.command === "view"
            ? "Viewing"
            : msg.command === "undo_edit"
              ? "Reverting"
              : "Editing";
      return { Icon: FileCode2, label: `${action} ${fname}` };
    }
    default:
      return { Icon: Sparkles, label: "Working" };
  }
}

function TypingIndicator() {
  return (
    <div className="flex">
      <div className="flex items-center gap-1 rounded-2xl rounded-bl-sm bg-surface px-4 py-3">
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent-teal/80 [animation-delay:-0.3s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent-teal/80 [animation-delay:-0.15s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent-teal/80" />
      </div>
    </div>
  );
}

function TrajectoryGroup({
  items,
  sessionId,
  isActive,
  settled,
  onFileEditClick,
}) {
  const [open, setOpen] = useState(false);
  const count = items.length;
  const latest = items[items.length - 1]?.msg;
  const { Icon, label } = describeStep(latest);

  // Once the final response has arrived, the header collapses back to a
  // static "Show agent steps" label. Until then, show the live step title.
  const HeaderIcon = settled ? Sparkles : Icon;

  return (
    <div className="rounded-lg border border-border/40 bg-charcoal/30">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-text-secondary transition-colors hover:text-text-primary"
      >
        {open ? (
          <ChevronDown size={14} className="shrink-0" />
        ) : (
          <ChevronRight size={14} className="shrink-0" />
        )}
        <HeaderIcon
          size={13}
          className={`shrink-0 text-accent-teal/80 ${
            isActive ? "animate-spin" : ""
          }`}
        />
        {open ? (
          <span className="font-medium">Hide agent steps</span>
        ) : settled ? (
          <span className="flex min-w-0 items-center gap-1.5">
            <span className="font-medium text-text-primary">
              Show agent steps
            </span>
            <span className="shrink-0 text-text-muted">· {count}</span>
          </span>
        ) : (
          <span className="flex min-w-0 items-center gap-1.5">
            <span className="truncate font-medium text-text-primary">
              {label}
            </span>
            <span className="shrink-0 text-text-muted">· {count}</span>
          </span>
        )}
      </button>
      {open && (
        <div className="space-y-3 border-t border-border/30 px-3 py-3">
          {items.map(({ msg, idx }) => (
            <ChatMessage
              key={`${sessionId}-${idx}`}
              message={msg}
              animate={msg.animate !== false}
              onFileEditClick={onFileEditClick}
            />
          ))}
        </div>
      )}
    </div>
  );
}

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
    ratings,
    setRatings,
    currentEmployeeId,
    chatFiles,
    setChatFiles,
  } = useApp();

  const handleRemoveChatFile = (index) => {
    setChatFiles?.((prev) => (prev ?? []).filter((_, i) => i !== index));
  };

  const handleRated = (taskIndex, rating) => {
    if (!Number.isInteger(taskIndex)) return;
    setRatings?.((prev) => ({ ...(prev || {}), [taskIndex]: rating }));
  };

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

  // Walk the message list and collapse consecutive trajectory messages into
  // a single collapsible group, so each response gets its own toggle. A group
  // is "settled" once a final answer / chat_response / error has been emitted
  // for its turn (we use that to swap the header copy).
  //
  // We also count user turns inline so each answer can be keyed to the task
  // it closes even when the SSE payload didn't embed ``task_index`` (e.g.
  // legacy chat history). This lets MessageRating persist / rehydrate.
  const renderItems = useMemo(() => {
    const items = [];
    let currentGroup = null;
    let userTurns = -1;
    messages.forEach((msg, idx) => {
      if (msg.type === "agent_marker") return;
      if (TRAJECTORY_TYPES.has(msg.type)) {
        if (!currentGroup) {
          currentGroup = {
            kind: "group",
            startIdx: idx,
            items: [],
            settled: false,
          };
          items.push(currentGroup);
        }
        currentGroup.items.push({ msg, idx });
      } else {
        if (msg.type === "user" || msg.role === "user") userTurns += 1;
        let taskIndex;
        if (msg.type === "answer" || msg.type === "chat_response") {
          taskIndex =
            typeof msg.taskIndex === "number"
              ? msg.taskIndex
              : userTurns >= 0
                ? userTurns
                : undefined;
        }
        if (
          currentGroup &&
          ["answer", "chat_response", "error"].includes(msg.type)
        ) {
          currentGroup.settled = true;
        }
        currentGroup = null;
        items.push({ kind: "single", msg, idx, taskIndex });
      }
    });
    return items;
  }, [messages]);

  const handleFileEditClick = (m) => {
    if (m.path) handleCanvasSelectFile(m.path);
  };

  // Show the typing indicator while the agent is working but hasn't started
  // emitting the final answer yet (the answer has its own typing cursor).
  const lastMessage = messages[messages.length - 1];
  const showTypingIndicator =
    isStreaming &&
    (!lastMessage ||
      !["answer", "chat_response", "error"].includes(lastMessage.type));

  const chatColumn = hasMessages ? (
    <>
      <div ref={scrollContainerRef} className="flex-1 overflow-y-auto">
        <div className="px-4 pt-4 pb-4">
          <div className="mx-auto max-w-5xl space-y-3">
            {renderItems.map((item, i) =>
              item.kind === "group" ? (
                <TrajectoryGroup
                  key={`${sessionId}-group-${item.startIdx}`}
                  items={item.items}
                  sessionId={sessionId}
                  isActive={
                    isStreaming &&
                    i === renderItems.length - 1 &&
                    !item.settled
                  }
                  settled={item.settled}
                  onFileEditClick={handleFileEditClick}
                />
              ) : (
                <ChatMessage
                  key={`${sessionId}-${item.idx}`}
                  message={
                    Number.isInteger(item.taskIndex)
                      ? { ...item.msg, taskIndex: item.taskIndex }
                      : item.msg
                  }
                  animate={item.msg.animate !== false}
                  onFileEditClick={handleFileEditClick}
                  employeeId={currentEmployeeId}
                  sessionId={sessionId}
                  rating={
                    Number.isInteger(item.taskIndex)
                      ? (ratings?.[item.taskIndex] ?? null)
                      : null
                  }
                  onRated={handleRated}
                />
              ),
            )}
            {showTypingIndicator && <TypingIndicator />}
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
          chatFiles={chatFiles}
          onRemoveChatFile={handleRemoveChatFile}
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
            chatFiles={chatFiles}
            onRemoveChatFile={handleRemoveChatFile}
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
