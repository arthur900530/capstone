import { createElement, useState, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  MessageSquare,
  MessageSquarePlus,
  Terminal,
  BarChart3,
  Wrench,
  Files,
  Sparkles,
  Trash2,
  Loader2,
  ShieldCheck,
} from "lucide-react";
import ConfirmDialog from "../components/skills/ConfirmDialog";
import * as Icons from "lucide-react";
import EmployeeConsole from "../components/employee/EmployeeConsole";
import ChatView from "../components/ChatView";
import BrowserLiveView from "../components/BrowserLiveView";

// In --demo mode the standard ChatView + BrowserLiveView (which itself
// swaps in BrowserReplayView when VITE_DEMO=true) renders the recorded
// session, so the legacy EmployeeChat + DesktopSimulator fork is no
// longer needed.
const LIVE_BROWSER_ENABLED = import.meta.env.VITE_LIVE_BROWSER !== "false";
import EmployeeReportCard from "../components/employee/EmployeeReportCard";
import EmployeeSkillsTab from "../components/employee/EmployeeSkillsTab";
import EmployeeProjectFilesTab from "../components/employee/EmployeeProjectFilesTab";
import EmployeeSystemPromptTab from "../components/employee/EmployeeSystemPromptTab";
import AutoTestsTab from "../components/employee/AutoTestsTab";
import PLUGINS from "../data/plugins";
import { getEmployeeById, deleteEmployee } from "../services/employeeStore";
import { useApp } from "../context/appContextCore";

const TABS = [
  { id: "chat", label: "Chat", icon: MessageSquare },
  { id: "skills", label: "Skills", icon: Wrench },
  { id: "project_files", label: "Project Files", icon: Files },
  { id: "system_prompt", label: "System Prompt", icon: Sparkles },
  { id: "auto_tests", label: "Auto Tests", icon: ShieldCheck },
  // { id: "console", label: "Console", icon: Terminal },
  { id: "report", label: "Report Card", icon: BarChart3 },
];

export default function EmployeePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const {
    refreshEmployees,
    browserLive,
    sessionId,
    chats,
    employees,
    handleSelectChat,
    handleNewChat,
  } = useApp();
  const [activeTab, setActiveTab] = useState("chat");
  // Track whether the Auto Tests tab has been visited so we mount it lazily
  // but then keep it mounted (with CSS hiding) so in-flight runs survive tab switches.
  const [autoTestsEverActive, setAutoTestsEverActive] = useState(false);
  const [employee, setEmployee] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const restoredForRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getEmployeeById(id)
      .then((emp) => { if (!cancelled) { setEmployee(emp); setLoading(false); } })
      .catch(() => { if (!cancelled) { setEmployee(null); setLoading(false); } });
    return () => { cancelled = true; };
  }, [id]);

  // Auto-restore chat state when the user lands on a new employee page.
  // Runs exactly once per employee id to avoid nuking an in-flight chat
  // when `chats`/`employees` refresh mid-stream:
  //  * If the current session already belongs to this employee → keep it.
  //  * Otherwise load the most-recent chat this employee owns.
  //  * If the employee has no prior chats, reset to a fresh session so the
  //    next submit links the new conversation to this employee.
  useEffect(() => {
    if (!employee) return;
    if (restoredForRef.current === employee.id) return;
    restoredForRef.current = employee.id;

    // Prefer the live employees list from context for freshness; fall back
    // to the locally fetched record.
    const latest = employees.find((e) => e.id === employee.id) || employee;
    const ownedIds = new Set(latest.chatSessionIds || []);

    if (sessionId && ownedIds.has(sessionId)) return;

    const mostRecent = chats.find((c) => ownedIds.has(c.id));
    if (mostRecent) {
      handleSelectChat(mostRecent.id);
    } else {
      handleNewChat();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [employee?.id]);

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <Loader2 size={20} className="animate-spin text-accent-teal" />
      </div>
    );
  }

  if (!employee) {
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-text-muted">
        Employee not found.
      </div>
    );
  }

  const pluginIds = employee.pluginIds || (employee.pluginId ? [employee.pluginId] : []);
  const plugins = PLUGINS.filter((p) => pluginIds.includes(p.id));
  const RoleIcon = Icons[plugins[0]?.icon] || Icons.Bot;

  const handleDelete = async () => {
    setDeleting(true);
    await deleteEmployee(employee.id);
    await refreshEmployees();
    navigate("/");
  };

  // Intentionally NOT gated on ``activeTab === "chat"``. The chat
  // container below is kept mounted (and hidden via CSS) when the user
  // navigates to another tab, so the BrowserLiveView / BrowserReplayView
  // instance — and in --demo mode the running noVNC RFB session — can
  // survive tab switches. Re-adding the active-tab check here would
  // unmount the browser panel on every Report Card / Skills hop and the
  // demo replay would restart from frame 0 on return.
  const showBrowserPanel = LIVE_BROWSER_ENABLED && browserLive?.visible;

  return (
    <div className="flex flex-1 flex-col min-h-0 overflow-hidden">
      <div className="shrink-0 border-b border-border/30 px-6 py-4">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate("/")}
              className="text-text-muted hover:text-text-secondary"
            >
              <ArrowLeft size={18} />
            </button>
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent-teal/10">
              <RoleIcon size={20} className="text-accent-teal" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-lg font-semibold text-text-primary">
                  {employee.name}
                </h1>
              </div>
              <p className="text-xs text-text-muted">
                {plugins.map((p) => p.name).join(", ") ||
                  employee.position?.trim() ||
                  "Custom Role"}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1">
            <button
              onClick={handleNewChat}
              title="Start a new chat with this employee"
              className="rounded-lg p-2 text-text-muted transition-colors hover:bg-surface hover:text-accent-teal"
            >
              <MessageSquarePlus size={16} />
            </button>
            <button
              onClick={() => setShowDeleteConfirm(true)}
              className="rounded-lg p-2 text-text-muted transition-colors hover:bg-surface hover:text-red-400"
            >
              <Trash2 size={16} />
            </button>
          </div>
        </div>
      </div>

      <div className="shrink-0 border-b border-border/20 px-6">
        <div className="mx-auto flex max-w-5xl gap-1">
          {TABS.map(({ id, label, icon }) => (
            <button
              key={id}
              onClick={() => {
                setActiveTab(id);
                if (id === "auto_tests") setAutoTestsEverActive(true);
              }}
              className={`flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-medium transition-colors ${
                activeTab === id
                  ? "border-accent-teal text-accent-teal"
                  : "border-transparent text-text-muted hover:text-text-secondary"
              }`}
            >
              {createElement(icon, { size: 15 })}
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Chat panel is mounted unconditionally and merely hidden via CSS
          when the user is on another tab. Unmounting would tear down
          ChatView's local message state and, in --demo mode, the
          BrowserReplayView's RFB session + queued frame timers, causing
          the recorded browser to restart from frame 0 every time the
          user came back from Report Card / Skills / etc. ``hidden``
          (display:none) collapses the layout so the active tab below
          still gets the full viewport. */}
      <div
        className={`flex flex-1 overflow-hidden ${
          activeTab !== "chat" ? "hidden" : ""
        }`}
      >
        <div
          className={`flex min-w-0 flex-1 flex-col transition-all duration-300 ${
            showBrowserPanel ? "border-r border-border/20 lg:max-w-[50%]" : ""
          }`}
        >
          <ChatView embedded />
        </div>
        {showBrowserPanel && (
          <div className="hidden flex-1 flex-col lg:flex">
            <BrowserLiveView sessionId={sessionId || browserLive?.sessionId} />
          </div>
        )}
      </div>
      {activeTab === "skills" && (
        <EmployeeSkillsTab
          key={id}
          employee={employee}
          onEmployeeUpdated={(emp) => setEmployee(emp)}
        />
      )}
      {activeTab === "project_files" && (
        <EmployeeProjectFilesTab key={id} employee={employee} />
      )}
      {activeTab === "system_prompt" && (
        <EmployeeSystemPromptTab
          key={id}
          employee={employee}
          onUpdated={(emp) => {
            setEmployee(emp);
            refreshEmployees?.();
          }}
        />
      )}
      {/* AutoTestsTab is mounted lazily on first visit, then stays mounted so
          in-flight test runs survive tab switches. CSS hides it rather than
          unmounting, which would kill in-progress fetches. */}
      {autoTestsEverActive && (
        <div
          className={`flex flex-1 flex-col overflow-hidden ${
            activeTab !== "auto_tests" ? "hidden" : ""
          }`}
        >
          <AutoTestsTab key={id} employee={employee} />
        </div>
      )}
      {activeTab === "console" && <EmployeeConsole key={id} employee={employee} />}
      {activeTab === "report" && <EmployeeReportCard key={id} employee={employee} />}

      <ConfirmDialog
        open={showDeleteConfirm}
        title="Delete Employee"
        message={`Are you sure you want to delete ${employee.name}? This cannot be undone.`}
        confirmLabel="Delete"
        confirmColor="red"
        onConfirm={handleDelete}
        onCancel={() => setShowDeleteConfirm(false)}
        loading={deleting}
      />
    </div>
  );
}
