/**
 * Converts a stored chat message into the internal format used by the UI.
 * Shared between App.jsx (standalone chat) and EmployeeChat.jsx.
 */
export function restoreMessage(m) {
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
