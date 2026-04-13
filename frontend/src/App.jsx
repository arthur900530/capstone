import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { Routes, Route, useNavigate } from "react-router-dom";
import { Menu, BarChart3, Bot, Database } from "lucide-react";
import Sidebar from "./components/Sidebar";
import WelcomeHeader from "./components/WelcomeHeader";
import InputBox from "./components/InputBox";
import ChatMessage from "./components/ChatMessage";
import UploadedDataPanel from "./components/DataContext";
import DashboardPage from "./pages/DashboardPage";
import PluginsPage from "./pages/PluginsPage";
import EvaluationLabPage from "./pages/EvaluationLabPage";
import { AppProvider } from "./context/AppContext";
import { getEmployees } from "./services/employeeStore";
import {
  streamChat,
  uploadFiles,
  fetchChats,
  fetchChatById,
  fetchAgents,
  fetchSkills,
  deleteChat as apiDeleteChat,
  renameChat as apiRenameChat,
} from "./services/api";

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
          <button
            onClick={onViewEval}
            className="flex items-center gap-1.5 rounded-md bg-accent-teal/10 px-2.5 py-1 text-xs font-medium text-accent-teal transition-colors hover:bg-accent-teal/20"
          >
            <BarChart3 size={13} />
            Evaluation
          </button>
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

function restoreMessage(m) {
  const type = m.type || (m.role === "user" ? "user" : "chat_response");
  const base = { role: m.role || "assistant", type, animate: false };

  switch (type) {
    case "user":
      return { ...base, role: "user", content: m.content };
    case "trial_start":
      return { ...base, trial: m.trial, maxTrials: m.max_trials };
    case "tool_call":
      return { ...base, turn: m.turn, tool: m.tool, detail: m.detail };
    case "tool_result":
    case "reasoning":
    case "reflection":
    case "chat_response":
      return { ...base, content: m.text ?? m.content };
    case "self_eval":
      return {
        ...base,
        content: m.critique ?? m.content,
        confidenceScore: m.confidence_score,
        isConfident: m.is_confident,
      };
    case "answer":
      return { ...base, content: m.text ?? m.content };
    case "status":
      return { ...base, content: m.message ?? m.content, done: true };
    default:
      return { ...base, content: m.content ?? m.text ?? "" };
  }
}

/* ── Chat View (used at the / route when no employee context) ──────────── */
function ChatView() {
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
    handleSubmit,
    handleViewEval,
    scrollContainerRef,
    updateVisibleAgent,
    messagesEndRef,
    registerSentinel,
  } = useApp();

  const hasMessages = messages.length > 0;

  if (hasMessages) {
    return (
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
          />
        </div>
      </>
    );
  }

  return (
    <>
      <div className="flex flex-1 flex-col items-center justify-center">
        <div className="w-full">
          <WelcomeHeader />
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
          />
        </div>
      </div>
      <footer className="pb-4 text-center text-xs text-text-muted">
        AI may produce inaccurate information. Verify important facts.
      </footer>
    </>
  );
}

/* ── Imports for context hook ──────────────────────────────────────────── */
import { useApp } from "./context/AppContext";

/* ── App (layout shell) ───────────────────────────────────────────────── */
export default function App() {
  const navigate = useNavigate();

  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [visibleAgent, setVisibleAgent] = useState(null);
  const [agents, setAgents] = useState([]);
  const [chats, setChats] = useState([]);
  const [chatFiles, setChatFiles] = useState([]);
  const [stagedFiles, setStagedFiles] = useState([]);
  const [skills, setSkills] = useState([]);
  const [focusAgentId, setFocusAgentId] = useState(null);
  const [mountDir, setMountDir] = useState("");
  const [selectedSkillIds, setSelectedSkillIds] = useState([]);
  const [skipSkillConfirm, setSkipSkillConfirm] = useState(false);
  const [employees, setEmployees] = useState(getEmployees());
  const [config, setConfig] = useState({
    model: "",
    maxTrials: 3,
    confidenceThreshold: 0.7,
    useReflexion: false,
  });

  const messagesEndRef = useRef(null);
  const scrollContainerRef = useRef(null);
  const sentinelRefs = useRef(new Map());
  const visibleAgentRef = useRef(null);

  const agentMap = useMemo(
    () => Object.fromEntries(agents.map((a) => [a.id, a])),
    [agents],
  );

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const updateVisibleAgent = useCallback(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    const containerTop = container.getBoundingClientRect().top;
    const bannerOffset = 52;

    const entries = [...sentinelRefs.current.entries()].sort(
      ([a], [b]) => a - b,
    );
    if (entries.length === 0) return;

    let best = entries[0][1].agent;
    for (const [, { el, agent }] of entries) {
      if (!el) continue;
      if (el.getBoundingClientRect().top <= containerTop + bannerOffset) {
        best = agent;
      }
    }

    if (best && best.id !== visibleAgentRef.current) {
      visibleAgentRef.current = best.id;
      setVisibleAgent(best);
    }
  }, []);

  useEffect(() => {
    updateVisibleAgent();
  }, [messages, updateVisibleAgent]);

  useEffect(() => {
    fetchAgents()
      .then(setAgents)
      .catch(() => {});
    fetchSkills()
      .then(setSkills)
      .catch(() => {});
  }, []);

  const refreshSkills = useCallback(async () => {
    try {
      const list = await fetchSkills();
      setSkills(list);
    } catch {
      /* skills list stays stale */
    }
  }, []);

  const refreshChats = useCallback(async () => {
    try {
      const list = await fetchChats();
      setChats(list);
    } catch {
      /* sidebar stays stale */
    }
  }, []);

  const refreshEmployees = useCallback(() => {
    setEmployees(getEmployees());
  }, []);

  useEffect(() => {
    refreshChats();
  }, [refreshChats]);

  const handleSubmit = async (question, submittedFiles = []) => {
    if (!question.trim() || isStreaming) return;

    const sid = sessionId || crypto.randomUUID();
    if (!sessionId) setSessionId(sid);

    if (submittedFiles.length > 0) {
      const fileMeta = submittedFiles.map((f) => ({
        name: f.name,
        size: f.size,
        type: f.type,
      }));
      setChatFiles((prev) => [...prev, ...fileMeta]);
    }

    setMessages((prev) => [
      ...prev,
      { role: "user", type: "user", content: question },
    ]);
    setIsStreaming(true);

    try {
      if (submittedFiles.length > 0) {
        await uploadFiles(sid, submittedFiles);
      }

      await streamChat(
        {
          question,
          sessionId: sid,
          model: config.model || undefined,
          maxTrials: config.maxTrials,
          confidenceThreshold: config.confidenceThreshold,
          useReflexion: config.useReflexion,
          files: submittedFiles.length > 0
            ? submittedFiles.map((f) => ({ name: f.name, size: f.size, type: f.type }))
            : undefined,
          skillIds: selectedSkillIds,
          mountDir: mountDir || undefined,
        },
        (eventType, data) => {
          let msg = null;

          switch (eventType) {
            case "session":
              setSessionId(data.session_id);
              return;
            case "agent":
              setMessages((prev) => [
                ...prev,
                { type: "agent_marker", agent: data },
              ]);
              return;
            case "status":
              msg = {
                role: "assistant",
                type: "status",
                content: data.message,
              };
              break;
            case "trial_start":
              msg = {
                role: "assistant",
                type: "trial_start",
                trial: data.trial,
                maxTrials: data.max_trials,
              };
              break;
            case "tool_call":
              msg = {
                role: "assistant",
                type: "tool_call",
                turn: data.turn,
                tool: data.tool,
                detail: data.detail,
              };
              break;
            case "tool_result":
              msg = { role: "assistant", type: "tool_result", content: data.text };
              break;
            case "reasoning":
              msg = { role: "assistant", type: "reasoning", content: data.text };
              break;
            case "self_eval":
              msg = {
                role: "assistant",
                type: "self_eval",
                content: data.critique,
                confidenceScore: data.confidence_score,
                isConfident: data.is_confident,
              };
              break;
            case "reflection":
              msg = { role: "assistant", type: "reflection", content: data.text };
              break;
            case "answer":
              msg = {
                role: "assistant",
                type: "answer",
                content: data.text,
                question,
              };
              break;
            case "chat_response":
              msg = {
                role: "assistant",
                type: "chat_response",
                content: data.text,
              };
              break;
            case "error":
              msg = {
                role: "assistant",
                type: "error",
                content: data.message,
              };
              break;
            default:
              break;
          }

          if (msg) {
            setMessages((prev) => {
              const updated = prev.map((m) =>
                m.type === "status" && !m.done ? { ...m, done: true } : m,
              );
              return [...updated, msg];
            });
          }
        },
      );

      refreshChats();
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", type: "error", content: err.message },
      ]);
    } finally {
      setIsStreaming(false);
      setMessages((prev) =>
        prev.map((m) => (m.animate === false ? m : { ...m, animate: false })),
      );
    }
  };

  const handleNewChat = () => {
    setMessages([]);
    setSessionId(null);
    setVisibleAgent(null);
    setChatFiles([]);
    setStagedFiles([]);
    setSkipSkillConfirm(false);
    setMountDir("");
    visibleAgentRef.current = null;
    sentinelRefs.current.clear();
  };

  const handleSelectChat = async (chatId) => {
    if (chatId === sessionId) {
      navigate("/chat");
      return;
    }
    try {
      const chat = await fetchChatById(chatId);
      setSessionId(chatId);

      const agent = agentMap[chat.agent_id] ?? null;

      sentinelRefs.current.clear();
      visibleAgentRef.current = null;

      const restored = [];
      if (agent) {
        restored.push({ type: "agent_marker", agent });
      }
      for (const m of chat.messages) {
        restored.push(restoreMessage(m));
      }
      setMessages(restored);
      setChatFiles(chat.files ?? []);
      setStagedFiles([]);
      if (agent) {
        visibleAgentRef.current = agent.id;
        setVisibleAgent(agent);
      }
      navigate("/chat");
    } catch {
      /* ignore */
    }
  };

  const handleDeleteChat = async (chatId) => {
    try {
      await apiDeleteChat(chatId);
      setChats((prev) => prev.filter((c) => c.id !== chatId));
      if (chatId === sessionId) handleNewChat();
    } catch {
      /* ignore */
    }
  };

  const handleRenameChat = async (chatId, newName) => {
    try {
      await apiRenameChat(chatId, newName);
      setChats((prev) =>
        prev.map((c) => (c.id === chatId ? { ...c, name: newName } : c)),
      );
    } catch {
      /* ignore */
    }
  };

  const handleViewEval = (agentId) => {
    if (agentId) setFocusAgentId(agentId);
    navigate("/evaluation");
  };

  const registerSentinel = (index, el, agent) => {
    if (el) {
      sentinelRefs.current.set(index, { el, agent });
    } else {
      sentinelRefs.current.delete(index);
    }
  };

  const ctxValue = {
    messages,
    setMessages,
    isStreaming,
    sessionId,
    setSessionId,
    visibleAgent,
    agents,
    agentMap,
    chats,
    chatFiles,
    setChatFiles,
    stagedFiles,
    setStagedFiles,
    skills,
    selectedSkillIds,
    setSelectedSkillIds,
    skipSkillConfirm,
    setSkipSkillConfirm,
    config,
    setConfig,
    mountDir,
    setMountDir,
    focusAgentId,
    setFocusAgentId,
    employees,
    refreshEmployees,
    refreshSkills,
    refreshChats,
    handleSubmit,
    handleNewChat,
    handleSelectChat,
    handleDeleteChat,
    handleRenameChat,
    handleViewEval,
    scrollContainerRef,
    messagesEndRef,
    updateVisibleAgent,
    registerSentinel,
  };

  return (
    <AppProvider value={ctxValue}>
      <div className="flex h-full bg-workspace">
        <Sidebar
          isOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          onNewChat={handleNewChat}
          chats={chats}
          agentMap={agentMap}
          activeChatId={sessionId}
          onSelectChat={handleSelectChat}
          onDeleteChat={handleDeleteChat}
          onRenameChat={handleRenameChat}
          employees={employees}
        />

        <main className="relative flex flex-1 flex-col">
          <div className="absolute top-4 left-4 z-30 lg:hidden">
            <button
              onClick={() => setSidebarOpen(true)}
              className="flex h-10 w-10 items-center justify-center rounded-lg text-text-secondary transition-colors hover:bg-surface"
            >
              <Menu size={20} />
            </button>
          </div>

          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/chat" element={<ChatView />} />
            <Route path="/plugins" element={<PluginsPage />} />
            <Route path="/evaluation" element={<EvaluationLabPage />} />
          </Routes>
        </main>
      </div>
    </AppProvider>
  );
}
