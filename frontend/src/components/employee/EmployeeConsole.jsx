import { useState, useEffect } from "react";
import { Terminal, Wrench, Brain, CheckCircle, AlertCircle } from "lucide-react";
import { fetchChatById } from "../../services/api";

const EVENT_STYLES = {
  tool_call: { icon: Wrench, color: "text-accent-teal", bg: "bg-accent-teal/10", label: "Tool Call" },
  tool_result: { icon: Terminal, color: "text-accent-teal", bg: "bg-accent-teal/10", label: "Tool Result" },
  reasoning: { icon: Brain, color: "text-yellow-400", bg: "bg-yellow-400/10", label: "Reasoning" },
  reflection: { icon: Brain, color: "text-yellow-400", bg: "bg-yellow-400/10", label: "Reflection" },
  self_eval: { icon: CheckCircle, color: "text-green-400", bg: "bg-green-400/10", label: "Self Eval" },
  status: { icon: AlertCircle, color: "text-text-muted", bg: "bg-surface", label: "Status" },
};

const CONSOLE_TYPES = new Set(Object.keys(EVENT_STYLES));

export default function EmployeeConsole({ employee }) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadEvents() {
      setLoading(true);
      const allEvents = [];
      for (const sid of employee.chatSessionIds || []) {
        try {
          const chat = await fetchChatById(sid);
          for (const m of chat.messages) {
            const type = m.type || (m.role === "user" ? "user" : "chat_response");
            if (CONSOLE_TYPES.has(type)) {
              allEvents.push({ ...m, type, sessionId: sid, chatName: chat.name });
            }
          }
        } catch {
          /* skip unavailable sessions */
        }
      }
      setEvents(allEvents);
      setLoading(false);
    }
    loadEvents();
  }, [employee.id, employee.chatSessionIds?.length]);

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-text-muted">
        Loading activity log...
      </div>
    );
  }

  if (events.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center">
        <Terminal size={28} className="mb-3 text-text-muted" />
        <p className="text-sm text-text-muted">
          No activity yet. Start a conversation to see tool calls and reasoning.
        </p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-4">
      <div className="mx-auto max-w-3xl space-y-1.5 font-mono text-xs">
        {events.map((evt, i) => {
          const style = EVENT_STYLES[evt.type] || EVENT_STYLES.status;
          const Icon = style.icon;
          const content =
            evt.type === "tool_call"
              ? `${evt.tool}: ${evt.detail || ""}`
              : evt.text || evt.content || evt.critique || evt.message || "";

          return (
            <div
              key={i}
              className={`flex items-start gap-2 rounded-lg px-3 py-2 ${style.bg}`}
            >
              <Icon size={13} className={`mt-0.5 shrink-0 ${style.color}`} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className={`font-semibold ${style.color}`}>
                    {style.label}
                  </span>
                  {evt.chatName && (
                    <span className="text-text-muted/60 truncate">
                      {evt.chatName}
                    </span>
                  )}
                </div>
                <p className="mt-0.5 whitespace-pre-wrap break-words text-text-secondary">
                  {content}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
