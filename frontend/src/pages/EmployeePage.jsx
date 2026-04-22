import { useState, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, MessageSquare, Terminal, BarChart3, Wrench, Trash2, Loader2 } from "lucide-react";
import ConfirmDialog from "../components/skills/ConfirmDialog";
import * as Icons from "lucide-react";
import EmployeeChat from "../components/employee/EmployeeChat";
import DesktopSimulator from "../components/desktop/DesktopSimulator";
import EmployeeConsole from "../components/employee/EmployeeConsole";
import ChatView from "../components/ChatView";
import BrowserLiveView from "../components/BrowserLiveView";

const IS_DEMO = import.meta.env.VITE_DEMO === "true";
const LIVE_BROWSER_ENABLED = import.meta.env.VITE_LIVE_BROWSER !== "false";
import EmployeeReportCard from "../components/employee/EmployeeReportCard";
import EmployeeSkillsTab from "../components/employee/EmployeeSkillsTab";
import PLUGINS from "../data/plugins";
import { getEmployeeById, deleteEmployee } from "../services/employeeStore";
import { useApp } from "../context/AppContext";

const TABS = [
  { id: "chat", label: "Chat", icon: MessageSquare },
  { id: "skills", label: "Skills", icon: Wrench },
  { id: "console", label: "Console", icon: Terminal },
  { id: "report", label: "Report Card", icon: BarChart3 },
];

export default function EmployeePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { refreshEmployees, browserLive, sessionId } = useApp();
  const [activeTab, setActiveTab] = useState("chat");
  const [employee, setEmployee] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const desktopEventRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getEmployeeById(id)
      .then((emp) => { if (!cancelled) { setEmployee(emp); setLoading(false); } })
      .catch(() => { if (!cancelled) { setEmployee(null); setLoading(false); } });
    return () => { cancelled = true; };
  }, [id]);

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

  const handleDesktopEvent = (type, data) => {
    desktopEventRef.current?.(type, data);
  };

  const handleDelete = async () => {
    setDeleting(true);
    await deleteEmployee(employee.id);
    await refreshEmployees();
    navigate("/");
  };

  const showBrowserPanel =
    LIVE_BROWSER_ENABLED && !IS_DEMO && activeTab === "chat" && browserLive?.visible;

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
                {plugins.map((p) => p.name).join(", ") || "Custom Role"}
              </p>
            </div>
          </div>

          <button
            onClick={() => setShowDeleteConfirm(true)}
            className="rounded-lg p-2 text-text-muted transition-colors hover:bg-surface hover:text-red-400"
          >
            <Trash2 size={16} />
          </button>
        </div>
      </div>

      <div className="shrink-0 border-b border-border/20 px-6">
        <div className="mx-auto flex max-w-5xl gap-1">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={`flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-medium transition-colors ${
                activeTab === id
                  ? "border-accent-teal text-accent-teal"
                  : "border-transparent text-text-muted hover:text-text-secondary"
              }`}
            >
              <Icon size={15} />
              {label}
            </button>
          ))}
        </div>
      </div>

      {activeTab === "chat" && !IS_DEMO && (
        <div className="flex flex-1 overflow-hidden">
          <div
            className={`flex min-w-0 flex-1 flex-col transition-all duration-300 ${
              showBrowserPanel ? "border-r border-border/20 lg:max-w-[50%]" : ""
            }`}
          >
            <ChatView showWelcome={false} embedded />
          </div>
          {showBrowserPanel && (
            <div className="hidden flex-1 flex-col lg:flex">
              <BrowserLiveView sessionId={sessionId || browserLive?.sessionId} />
            </div>
          )}
        </div>
      )}
      {activeTab === "chat" && IS_DEMO && (
        <div className="flex flex-1 overflow-hidden">
          <div className="flex min-w-0 flex-1 flex-col border-r border-border/20 lg:max-w-[50%]">
            <EmployeeChat key={id} employee={employee} onDesktopEvent={handleDesktopEvent} />
          </div>
          <div className="hidden flex-1 flex-col lg:flex">
            <DesktopSimulator employee={employee} onEventRef={desktopEventRef} />
          </div>
        </div>
      )}
      {activeTab === "skills" && (
        <EmployeeSkillsTab
          key={id}
          employee={employee}
          onEmployeeUpdated={(emp) => setEmployee(emp)}
        />
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
