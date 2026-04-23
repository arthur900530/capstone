import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import {
  Routes,
  Route,
  Navigate,
  useNavigate,
  useLocation,
} from "react-router-dom";
import { Menu, PanelRight } from "lucide-react";
import Sidebar from "./components/Sidebar";
import ChatView from "./components/ChatView";
import EditorCanvas, { isCanvasPreviewable } from "./components/EditorCanvas";
import WorkspacePanel from "./components/WorkspacePanel";
import DashboardPage from "./pages/DashboardPage";
import PluginsPage from "./pages/PluginsPage";
import EvaluationLabPage from "./pages/EvaluationLabPage";
import CreationWizard from "./pages/CreationWizard";
import EmployeePage from "./pages/EmployeePage";
import { AppProvider } from "./context/AppContext";
import { getEmployees } from "./services/employeeStore";
import { restoreMessage } from "./services/messageUtils";
import {
  streamChat,
  uploadFiles,
  fetchChats,
  fetchChatById,
  fetchAgents,
  fetchSkills,
  deleteChat as apiDeleteChat,
  renameChat as apiRenameChat,
  fetchWorkspaceFile,
} from "./services/api";

const LIVE_BROWSER_ENABLED = import.meta.env.VITE_LIVE_BROWSER !== "false";

/* ── App (layout shell) ───────────────────────────────────────────────── */
export default function App() {
  const navigate = useNavigate();
  const { pathname } = useLocation();

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
  const [employees, setEmployees] = useState([]);
  const [config, setConfig] = useState({
    model: "",
    maxTrials: 3,
    confidenceThreshold: 0.7,
    useReflexion: false,
  });

  // --- Workspace / Canvas state ---
  const [openFiles, setOpenFiles] = useState([]);
  const [activeFile, setActiveFile] = useState(null);
  const [fileContents, setFileContents] = useState({});
  const [modifiedFiles, setModifiedFiles] = useState(new Set());
  const [editEvents, setEditEvents] = useState([]);
  const [workspacePanelOpen, setWorkspacePanelOpen] = useState(true);
  const [treeRefreshTrigger, setTreeRefreshTrigger] = useState(0);
  const [canvasCollapsed, setCanvasCollapsed] = useState(false);
  const [browserLive, setBrowserLive] = useState({
    enabled: LIVE_BROWSER_ENABLED,
    visible: false,
    status: "idle",
    sessionId: null,
    lastAction: null,
  });

  // Routes where the chat-style workspace (canvas + file tree) is meaningful.
  // We gate by route — not by an effect-driven `chatMounted` flag — so the
  // canvas appears immediately when a file_edit event fires, with no race
  // between ChatView's mount effect and the state update from setOpenFiles.
  const onChatCapableRoute =
    pathname === "/chat" || pathname.startsWith("/employee/");

  // When we're on an employee page, the shared ChatView is the UI — but the
  // /api/chat payload must still carry persona data so the backend can
  // inject the employee's identity/role/task into the agent's system prompt.
  // Derive the current employee from the URL + employees list rather than
  // wiring new context plumbing; the id is the source of truth and the
  // server does its own DB lookup from it.
  const employeeIdMatch = pathname.match(/^\/employee\/([^/]+)/);
  const currentEmployeeId = employeeIdMatch?.[1] || null;
  const currentEmployee = currentEmployeeId
    ? employees.find((e) => e.id === currentEmployeeId) || null
    : null;

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

  const refreshEmployees = useCallback(async () => {
    try {
      const list = await getEmployees();
      setEmployees(list);
    } catch {
      /* keep stale */
    }
  }, []);

  useEffect(() => {
    refreshChats();
  }, [refreshChats]);

  useEffect(() => {
    refreshEmployees();
  }, [refreshEmployees]);

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
          files:
            submittedFiles.length > 0
              ? submittedFiles.map((f) => ({
                  name: f.name,
                  size: f.size,
                  type: f.type,
                }))
              : undefined,
          skillIds: selectedSkillIds,
          mountDir: mountDir || undefined,
          employeeId: currentEmployeeId || undefined,
          employee: currentEmployee
            ? {
                name: currentEmployee.name,
                position: currentEmployee.position,
                task: currentEmployee.task,
              }
            : undefined,
        },
        (eventType, data) => {
          let msg = null;

          switch (eventType) {
            case "session":
              setSessionId(data.session_id);
              setBrowserLive((prev) => ({
                ...prev,
                sessionId: data.session_id,
              }));
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
              if (String(data.tool || "").startsWith("browser_")) {
                setBrowserLive((prev) => ({
                  ...prev,
                  visible: true,
                  status: "active",
                  sessionId: sid,
                  lastAction: {
                    tool: data.tool,
                    detail: data.detail,
                    at: Date.now(),
                  },
                }));
              }
              break;
            case "tool_result":
              msg = {
                role: "assistant",
                type: "tool_result",
                content: data.text,
              };
              break;
            case "reasoning":
              msg = {
                role: "assistant",
                type: "reasoning",
                content: data.text,
              };
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
              msg = {
                role: "assistant",
                type: "reflection",
                content: data.text,
              };
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
            case "file_edit":
              msg = {
                role: "assistant",
                type: "file_edit",
                turn: data.turn,
                command: data.command,
                path: data.path,
                fileText: data.file_text,
                oldStr: data.old_str,
                newStr: data.new_str,
                insertLine: data.insert_line,
              };
              // Push edit to canvas (always, even without mountDir) so users
              // see a live diff as the agent edits files.
              {
                const editEvt = {
                  command: data.command,
                  path: data.path,
                  fileText: data.file_text,
                  oldStr: data.old_str,
                  newStr: data.new_str,
                  insertLine: data.insert_line,
                };
                setEditEvents((prev) => [...prev, editEvt]);
                setModifiedFiles((prev) => new Set(prev).add(data.path));
                if (mountDir) setTreeRefreshTrigger((n) => n + 1);

                // Auto-open only previewable files so binary / unknown
                // extensions don't pop up unreadable tabs.
                const filePath = data.path;
                if (isCanvasPreviewable(filePath)) {
                  setOpenFiles((prev) =>
                    prev.includes(filePath) ? prev : [...prev, filePath],
                  );
                  setActiveFile(filePath);

                  if (data.command === "create" && data.file_text) {
                    setFileContents((prev) => ({
                      ...prev,
                      [filePath]: data.file_text,
                    }));
                  } else if (mountDir) {
                    fetchWorkspaceFile(mountDir, filePath)
                      .then((res) =>
                        setFileContents((prev) => ({
                          ...prev,
                          [filePath]: res.content,
                        })),
                      )
                      .catch(() => {});
                  }
                }
              }
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
    // Reset workspace state
    setOpenFiles([]);
    setActiveFile(null);
    setFileContents({});
    setModifiedFiles(new Set());
    setEditEvents([]);
    setTreeRefreshTrigger(0);
    setCanvasCollapsed(false);
    setBrowserLive({
      enabled: LIVE_BROWSER_ENABLED,
      visible: false,
      status: "idle",
      sessionId: null,
      lastAction: null,
    });
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
      const hasBrowserActivity = chat.messages.some(
        (m) => m.type === "tool_call" && String(m.tool || "").startsWith("browser_"),
      );
      setBrowserLive((prev) => ({
        ...prev,
        visible: hasBrowserActivity,
        sessionId: chatId,
        status: hasBrowserActivity ? "active" : "idle",
        lastAction: null,
      }));
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

  // --- Canvas file selection ---
  const handleCanvasSelectFile = useCallback(
    async (filePath) => {
      setOpenFiles((prev) =>
        prev.includes(filePath) ? prev : [...prev, filePath],
      );
      setActiveFile(filePath);
      if (!fileContents[filePath] && mountDir) {
        // Binary previews (PDF, images) are rendered directly from the raw
        // endpoint; don't try to fetch them as text.
        const ext = filePath.split(".").pop()?.toLowerCase();
        const binaryExts = new Set([
          "pdf",
          "png",
          "jpg",
          "jpeg",
          "gif",
          "bmp",
          "webp",
          "svg",
          "ico",
        ]);
        if (binaryExts.has(ext)) {
          setFileContents((prev) => ({ ...prev, [filePath]: "" }));
          return;
        }
        try {
          const res = await fetchWorkspaceFile(mountDir, filePath);
          setFileContents((prev) => ({ ...prev, [filePath]: res.content }));
        } catch {
          /* ignore */
        }
      }
    },
    [fileContents, mountDir],
  );

  const handleCanvasCloseFile = useCallback(
    (filePath) => {
      setOpenFiles((prev) => {
        const next = prev.filter((f) => f !== filePath);
        if (activeFile === filePath) {
          setActiveFile(next.length > 0 ? next[next.length - 1] : null);
        }
        return next;
      });
    },
    [activeFile],
  );

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
    // canvas / workspace
    openFiles,
    activeFile,
    fileContents,
    modifiedFiles,
    editEvents,
    canvasCollapsed,
    setCanvasCollapsed,
    browserLive,
    setBrowserLive,
    handleCanvasSelectFile,
    handleCanvasCloseFile,
    workspacePanelOpen,
    setWorkspacePanelOpen,
    treeRefreshTrigger,
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

        <main className="relative flex flex-1 flex-col overflow-hidden">
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
            <Route path="/new" element={<CreationWizard />} />
            <Route path="/employee/:id" element={<EmployeePage />} />
            <Route path="/chat" element={<ChatView />} />
            <Route path="/plugins" element={<PluginsPage />} />
            <Route path="/evaluation" element={<EvaluationLabPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>

        {/* Canvas & workspace panel live at the app-root flex row so they
            span the full viewport height (above the employee page banner). */}
        {onChatCapableRoute && openFiles.length > 0 && (
          <EditorCanvas
            openFiles={openFiles}
            activeFile={activeFile}
            fileContents={fileContents}
            modifiedFiles={modifiedFiles}
            editEvents={editEvents}
            mountDir={mountDir}
            onSelectFile={handleCanvasSelectFile}
            onCloseFile={handleCanvasCloseFile}
            collapsed={canvasCollapsed}
            onToggleCollapse={() => setCanvasCollapsed((v) => !v)}
          />
        )}

        {onChatCapableRoute && mountDir && workspacePanelOpen && (
          <WorkspacePanel
            mountDir={mountDir}
            activeFile={activeFile}
            modifiedFiles={modifiedFiles}
            onSelectFile={handleCanvasSelectFile}
            onClose={() => setWorkspacePanelOpen(false)}
            refreshTrigger={treeRefreshTrigger}
          />
        )}

        {onChatCapableRoute && mountDir && !workspacePanelOpen && (
          <button
            onClick={() => setWorkspacePanelOpen(true)}
            className="fixed right-3 top-3 z-30 flex h-8 w-8 items-center justify-center rounded-lg bg-surface text-text-muted transition-colors hover:bg-surface-hover hover:text-text-primary"
            title="Show workspace files"
          >
            <PanelRight size={16} />
          </button>
        )}
      </div>
    </AppProvider>
  );
}
