import { useState, useRef, useEffect } from "react";
import { Bot, BarChart3, Database } from "lucide-react";
import ChatMessage from "../ChatMessage";
import InputBox from "../InputBox";
import UploadedDataPanel from "../DataContext";
import {
  streamChat,
  uploadFiles,
  fetchChatById,
} from "../../services/api";
import { mockStreamChat } from "../../services/mockStream";

const IS_MOCK = import.meta.env.VITE_MOCK === "true";
import { addChatSession, markActive } from "../../services/employeeStore";
import { restoreMessage } from "../../services/messageUtils";

function AgentBanner({ agent, files = [], onRemoveFile }) {
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
            {files.length} files
          </button>
        )}
      </div>
      {showData && <UploadedDataPanel files={files} onRemoveFile={onRemoveFile} />}
    </div>
  );
}

export default function EmployeeChat({ employee, onDesktopEvent }) {
  const [messages, setMessages] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [visibleAgent, setVisibleAgent] = useState(null);
  const [chatFiles, setChatFiles] = useState([]);
  const [stagedFiles, setStagedFiles] = useState([]);
  // task_index -> 1..5 rating the user previously set for this session.
  // Hydrated from the server on chat load; live answers rely on
  // message.taskIndex (set from the SSE payload) and MessageRating's own
  // optimistic state, so we don't need to mirror ratings as they change.
  const [ratings, setRatings] = useState({});

  const endRef = useRef(null);
  const scrollRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Load last chat session if one exists
  useEffect(() => {
    const lastSid = employee.chatSessionIds?.[employee.chatSessionIds.length - 1];
    if (lastSid) {
      fetchChatById(lastSid)
        .then((chat) => {
          setSessionId(lastSid);
          setMessages(chat.messages.map(restoreMessage));
          setChatFiles(chat.files ?? []);
          setRatings(chat.ratings || {});
        })
        .catch(() => {});
    } else {
      setRatings({});
    }
  }, [employee.id]);

  const handleSubmit = async (question, submittedFiles = []) => {
    if (!question.trim() || isStreaming) return;

    const sid = sessionId || crypto.randomUUID();
    if (!sessionId) {
      setSessionId(sid);
      addChatSession(employee.id, sid);
    }

    if (submittedFiles.length > 0) {
      setChatFiles((prev) => [
        ...prev,
        ...submittedFiles.map((f) => ({ name: f.name, size: f.size, type: f.type })),
      ]);
    }

    setMessages((prev) => [
      ...prev,
      { role: "user", type: "user", content: question },
    ]);
    setIsStreaming(true);
    markActive(employee.id);

    const handleEvent = (eventType, data) => {
      let msg = null;
      switch (eventType) {
        case "session":
          setSessionId(data.session_id);
          addChatSession(employee.id, data.session_id);
          onDesktopEvent?.(eventType, data);
          return;
        case "agent":
          setVisibleAgent(data);
          setMessages((prev) => [...prev, { type: "agent_marker", agent: data }]);
          onDesktopEvent?.(eventType, data);
          return;
        case "status":
          msg = { role: "assistant", type: "status", content: data.message };
          break;
        case "trial_start":
          msg = { role: "assistant", type: "trial_start", trial: data.trial, maxTrials: data.max_trials };
          break;
        case "tool_call":
          msg = { role: "assistant", type: "tool_call", turn: data.turn, tool: data.tool, detail: data.detail };
          break;
        case "tool_result":
          msg = { role: "assistant", type: "tool_result", content: data.text };
          break;
        case "reasoning":
          msg = { role: "assistant", type: "reasoning", content: data.text };
          break;
        case "self_eval":
          msg = { role: "assistant", type: "self_eval", content: data.critique, confidenceScore: data.confidence_score, isConfident: data.is_confident };
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
            taskIndex: typeof data.task_index === "number" ? data.task_index : undefined,
          };
          break;
        case "chat_response":
          msg = {
            role: "assistant",
            type: "chat_response",
            content: data.text,
            taskIndex: typeof data.task_index === "number" ? data.task_index : undefined,
          };
          break;
        case "error":
          msg = { role: "assistant", type: "error", content: data.message };
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
      onDesktopEvent?.(eventType, data);
    };

    try {
      if (!IS_MOCK && submittedFiles.length > 0) {
        await uploadFiles(sid, submittedFiles);
      }

      if (IS_MOCK) {
        await mockStreamChat({ question }, handleEvent);
      } else {
        await streamChat(
          {
            question,
            sessionId: sid,
            model: employee.model || undefined,
            maxTrials: employee.maxTrials,
            confidenceThreshold: employee.confidenceThreshold,
            useReflexion: employee.useReflexion,
            skillIds: employee.skillIds,
            employeeId: employee.id,
            employee: {
              name: employee.name,
              position: employee.position,
              task: employee.task,
            },
          },
          handleEvent,
        );
      }
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

  const hasMessages = messages.length > 0;

  return (
    <div className="flex flex-1 flex-col">
      {hasMessages ? (
        <>
          <div ref={scrollRef} className="flex-1 overflow-y-auto">
            <AgentBanner
              agent={visibleAgent}
              files={chatFiles}
              onRemoveFile={(i) => setChatFiles((prev) => prev.filter((_, idx) => idx !== i))}
            />
            <div className="px-4 pt-4 pb-4">
              <div className="mx-auto max-w-2xl space-y-3">
                {(() => {
                  // Count user messages as we walk so each agent answer can
                  // be keyed to the task it closes, even if the server
                  // didn't embed ``task_index`` in its event payload.
                  let userTurns = -1;
                  return messages.map((msg, i) => {
                    if (msg.type === "user") userTurns += 1;
                    if (msg.type === "agent_marker") {
                      return (
                        <div key={i} className="flex items-center gap-3 py-1">
                          <div className="h-px flex-1 bg-border/40" />
                          <span className="flex items-center gap-1.5 text-[10px] font-medium text-text-muted">
                            <Bot size={11} />
                            {msg.agent.name}
                          </span>
                          <div className="h-px flex-1 bg-border/40" />
                        </div>
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
                      Number.isInteger(resolvedTaskIndex)
                        ? ratings[resolvedTaskIndex] ?? null
                        : null;
                    return (
                      <ChatMessage
                        key={i}
                        message={enriched}
                        animate={msg.animate !== false}
                        employeeId={employee.id}
                        sessionId={sessionId}
                        rating={ratingForMsg}
                        onRated={(ti, r) => {
                          if (!Number.isInteger(ti)) return;
                          setRatings((prev) => ({ ...(prev || {}), [ti]: r }));
                        }}
                      />
                    );
                  });
                })()}
                <div ref={endRef} />
              </div>
            </div>
          </div>
          <div className="border-t border-border/30 bg-workspace pb-4 pt-3">
            <InputBox
              onSubmit={handleSubmit}
              isStreaming={isStreaming}
              stagedFiles={stagedFiles}
              onFilesChange={setStagedFiles}
              hideSkillPicker
              hideModelPicker
            />
          </div>
        </>
      ) : (
        <div className="flex flex-1 flex-col items-center justify-center">
          <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-surface">
            <Bot size={28} className="text-text-muted" />
          </div>
          <p className="mb-1 text-lg font-semibold text-text-primary">
            Start a conversation
          </p>
          <p className="mb-8 text-sm text-text-muted">
            Ask {employee.name} anything related to their role.
          </p>
          <div className="w-full max-w-2xl">
            <InputBox
              onSubmit={handleSubmit}
              isStreaming={isStreaming}
              stagedFiles={stagedFiles}
              onFilesChange={setStagedFiles}
              hideSkillPicker
              hideModelPicker
            />
          </div>
        </div>
      )}
    </div>
  );
}
