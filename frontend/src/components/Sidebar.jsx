import { useState } from "react";
import {
  MessageSquare,
  ClipboardCheck,
  Store,
  Plus,
  ChevronDown,
  Trash2,
  Pencil,
  Check,
  X,
} from "lucide-react";

const navItems = [
  { icon: MessageSquare, label: "Chats", tab: "chat" },
  { icon: ClipboardCheck, label: "Evaluation", tab: "evaluation" },
  { icon: Store, label: "Marketplace", tab: "skills" },
];

function ChatHistoryItem({ chat, agentName, isActive, onSelect, onDelete, onRename }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(chat.name);

  const commitRename = () => {
    const trimmed = draft.trim();
    if (trimmed && trimmed !== chat.name) onRename(chat.id, trimmed);
    setEditing(false);
  };

  return (
    <li
      className={`group relative flex items-center rounded-lg text-sm transition-colors ${
        isActive
          ? "bg-surface text-text-primary"
          : "text-text-secondary hover:bg-surface hover:text-text-primary"
      }`}
    >
      {editing ? (
        <div className="flex w-full items-center gap-1 px-3 py-2">
          <input
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") commitRename();
              if (e.key === "Escape") setEditing(false);
            }}
            className="flex-1 rounded bg-workspace px-1.5 py-0.5 text-sm text-text-primary outline-none ring-1 ring-border focus:ring-accent-teal"
          />
          <button onClick={commitRename} className="p-0.5 text-emerald-400 hover:text-emerald-300">
            <Check size={14} />
          </button>
          <button onClick={() => setEditing(false)} className="p-0.5 text-text-muted hover:text-text-secondary">
            <X size={14} />
          </button>
        </div>
      ) : (
        <>
          <button
            onClick={() => onSelect(chat.id)}
            className="flex-1 overflow-hidden px-3 py-2 text-left"
          >
            <span className="block truncate">{chat.name}</span>
            {agentName && (
              <span className="block truncate text-[10px] text-text-muted">
                {agentName}
              </span>
            )}
          </button>
          <div className="absolute right-1 flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
            <button
              onClick={(e) => { e.stopPropagation(); setDraft(chat.name); setEditing(true); }}
              className="rounded p-1 text-text-muted hover:bg-surface-hover hover:text-text-secondary"
            >
              <Pencil size={13} />
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); onDelete(chat.id); }}
              className="rounded p-1 text-text-muted hover:bg-surface-hover hover:text-red-400"
            >
              <Trash2 size={13} />
            </button>
          </div>
        </>
      )}
    </li>
  );
}

export default function Sidebar({
  isOpen,
  onClose,
  activeTab,
  onTabChange,
  onNewChat,
  chats = [],
  agentMap = {},
  activeChatId,
  onSelectChat,
  onDeleteChat,
  onRenameChat,
}) {
  return (
    <>
      {isOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/50 lg:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={`
          fixed top-0 left-0 z-40 h-full w-[260px] bg-charcoal flex flex-col
          transition-transform duration-300 ease-in-out
          ${isOpen ? "translate-x-0" : "-translate-x-full"}
          lg:translate-x-0 lg:static lg:z-auto
        `}
      >
        <div className="p-4">
          <button
            onClick={() => { onNewChat?.(); onTabChange("chat"); onClose(); }}
            className="flex w-full items-center gap-3 rounded-xl bg-surface px-4 py-3 text-sm font-medium text-text-primary transition-colors hover:bg-surface-hover"
          >
            <Plus size={18} className="text-text-secondary" />
            New Chat
          </button>
        </div>

        <nav className="flex flex-col flex-1 overflow-hidden px-3 py-2">
          <ul className="space-y-0.5">
            {navItems.map(({ icon: Icon, label, tab }) => (
              <li key={label}>
                <button
                  onClick={() => { onTabChange(tab); onClose(); }}
                  className={`
                    flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors
                    ${activeTab === tab
                      ? "bg-surface text-text-primary"
                      : "text-text-secondary hover:bg-surface hover:text-text-primary"
                    }
                  `}
                >
                  <Icon size={18} strokeWidth={1.8} />
                  {label}
                </button>
              </li>
            ))}
          </ul>

          {chats.length > 0 && (
            <div className="mt-4 flex-1 overflow-y-auto">
              <p className="mb-1.5 px-3 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
                Recent
              </p>
              <ul className="space-y-0.5">
                {chats.map((chat) => (
                  <ChatHistoryItem
                    key={chat.id}
                    chat={chat}
                    agentName={agentMap[chat.agent_id]?.name}
                    isActive={chat.id === activeChatId}
                    onSelect={(id) => { onSelectChat(id); onClose(); }}
                    onDelete={onDeleteChat}
                    onRename={onRenameChat}
                  />
                ))}
              </ul>
            </div>
          )}
        </nav>

        <div className="border-t border-border p-4">
          <button className="flex w-full items-center gap-3 rounded-lg px-2 py-2 transition-colors hover:bg-surface">
            <div className="relative h-8 w-8 shrink-0">
              <div className="h-8 w-8 rounded-full bg-gradient-to-br from-accent-deep to-accent-teal" />
              <div className="absolute bottom-0 right-0 h-2.5 w-2.5 rounded-full border-2 border-charcoal bg-emerald-500" />
            </div>
            <div className="flex-1 text-left">
              <p className="text-sm font-medium text-text-primary">User</p>
            </div>
            <ChevronDown size={16} className="text-text-muted" />
          </button>
        </div>
      </aside>
    </>
  );
}
