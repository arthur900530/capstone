import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import * as Icons from "lucide-react";
import {
  Home,
  ChevronDown,
  ChevronRight,
  Trash2,
  Pencil,
  Check,
  X,
  Puzzle,
  FlaskConical,
  MessageSquare,
} from "lucide-react";
import PLUGINS from "../data/plugins";

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
        <div className="flex w-full items-center gap-1 px-3 py-1.5">
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
            className="flex-1 overflow-hidden px-3 py-1.5 text-left"
          >
            <span className="block truncate text-xs">{chat.name}</span>
          </button>
          <div className="absolute right-1 flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
            <button
              onClick={(e) => { e.stopPropagation(); setDraft(chat.name); setEditing(true); }}
              className="rounded p-1 text-text-muted hover:bg-surface-hover hover:text-text-secondary"
            >
              <Pencil size={11} />
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); onDelete(chat.id); }}
              className="rounded p-1 text-text-muted hover:bg-surface-hover hover:text-red-400"
            >
              <Trash2 size={11} />
            </button>
          </div>
        </>
      )}
    </li>
  );
}

function EmployeeListItem({ employee, isActive, onNavigate }) {
  const pluginIds = employee.pluginIds || (employee.pluginId ? [employee.pluginId] : []);
  const plugin = PLUGINS.find((p) => pluginIds.includes(p.id));
  const IconComp = Icons[plugin?.icon] || Icons.Bot;
  const isUp = employee.status === "active";

  return (
    <button
      onClick={() => onNavigate(`/employee/${employee.id}`)}
      className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors ${
        isActive
          ? "bg-surface text-text-primary"
          : "text-text-secondary hover:bg-surface hover:text-text-primary"
      }`}
    >
      <IconComp size={15} className="shrink-0 text-accent-teal" />
      <span className="flex-1 truncate">{employee.name}</span>
      <span
        className={`h-2 w-2 shrink-0 rounded-full ${
          isUp ? "bg-green-400" : "bg-text-muted/40"
        }`}
      />
    </button>
  );
}

export default function Sidebar({
  isOpen,
  onClose,
  onNewChat,
  chats = [],
  agentMap = {},
  activeChatId,
  onSelectChat,
  onDeleteChat,
  onRenameChat,
  employees = [],
}) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const nav = (path) => {
    navigate(path);
    onClose();
  };

  // Determine which employee is active (if viewing one)
  const activeEmployeeId = pathname.startsWith("/employee/")
    ? pathname.split("/")[2]
    : null;

  // Filter chats belonging to active employee
  const activeEmployee = employees.find((e) => e.id === activeEmployeeId);
  const employeeChatIds = new Set(activeEmployee?.chatSessionIds || []);

  return (
    <>
      {isOpen && (
        <div className="fixed inset-0 z-30 bg-black/50 lg:hidden" onClick={onClose} />
      )}

      <aside
        className={`
          fixed top-0 left-0 z-40 h-full w-[260px] bg-charcoal flex flex-col
          transition-transform duration-300 ease-in-out
          ${isOpen ? "translate-x-0" : "-translate-x-full"}
          lg:translate-x-0 lg:static lg:z-auto
        `}
      >
        {/* Primary action */}
        <div className="p-4">
          <button
            onClick={() => nav("/")}
            className="flex w-full items-center gap-3 rounded-xl bg-accent-teal px-4 py-3 text-sm font-medium text-workspace transition-colors hover:bg-accent-teal/90"
          >
            <Home size={18} />
            Home
          </button>
        </div>

        <nav className="flex flex-1 flex-col overflow-hidden px-3 py-1">
          {/* MY EMPLOYEES section */}
          <p className="mb-1.5 px-3 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
            My Employees
          </p>

          {employees.length === 0 ? (
            <p className="px-3 py-2 text-xs text-text-muted/60">
              No employees yet
            </p>
          ) : (
            <ul className="space-y-0.5">
              {employees.map((emp) => (
                <li key={emp.id}>
                  <EmployeeListItem
                    employee={emp}
                    isActive={emp.id === activeEmployeeId}
                    onNavigate={nav}
                  />
                  {/* Show chats under active employee */}
                  {emp.id === activeEmployeeId && (emp.chatSessionIds?.length ?? 0) > 0 && (
                    <ul className="ml-6 mt-0.5 space-y-0.5">
                      {chats
                        .filter((c) => employeeChatIds.has(c.id))
                        .map((chat) => (
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
                  )}
                </li>
              ))}
            </ul>
          )}

          {/* Standalone chat link */}
          <div className="mt-4">
            <button
              onClick={() => { onNewChat?.(); nav("/chat"); }}
              className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors ${
                pathname === "/chat"
                  ? "bg-surface text-text-primary"
                  : "text-text-secondary hover:bg-surface hover:text-text-primary"
              }`}
            >
              <MessageSquare size={15} />
              Quick Chat
            </button>
          </div>

          {/* Recent chats (not assigned to employees) */}
          {chats.length > 0 && !activeEmployeeId && (
            <div className="mt-3 flex-1 overflow-y-auto">
              <p className="mb-1.5 px-3 text-[11px] font-semibold uppercase tracking-wider text-text-muted">
                Recent Chats
              </p>
              <ul className="space-y-0.5">
                {chats.slice(0, 10).map((chat) => (
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

          {/* ADVANCED collapsible section */}
          <div className="mt-auto border-t border-border/20 pt-3">
            <button
              onClick={() => setAdvancedOpen((v) => !v)}
              className="flex w-full items-center gap-2 px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-text-muted hover:text-text-secondary"
            >
              {advancedOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
              Advanced
            </button>
            {advancedOpen && (
              <ul className="space-y-0.5 pb-2">
                <li>
                  <button
                    onClick={() => nav("/plugins")}
                    className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors ${
                      pathname === "/plugins"
                        ? "bg-surface text-text-primary"
                        : "text-text-secondary hover:bg-surface hover:text-text-primary"
                    }`}
                  >
                    <Puzzle size={15} />
                    Plugin Workshop
                  </button>
                </li>
                <li>
                  <button
                    onClick={() => nav("/evaluation")}
                    className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors ${
                      pathname === "/evaluation"
                        ? "bg-surface text-text-primary"
                        : "text-text-secondary hover:bg-surface hover:text-text-primary"
                    }`}
                  >
                    <FlaskConical size={15} />
                    Evaluation Lab
                  </button>
                </li>
              </ul>
            )}
          </div>
        </nav>

        {/* User profile */}
        <div className="border-t border-border p-4">
          <button
            onClick={() => nav("/")}
            className="flex w-full items-center gap-3 rounded-lg px-2 py-2 transition-colors hover:bg-surface"
          >
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
