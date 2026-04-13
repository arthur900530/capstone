import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, MessageSquare, Terminal, BarChart3, Trash2, Loader2 } from "lucide-react";
import * as Icons from "lucide-react";
import EmployeeChat from "../components/employee/EmployeeChat";
import EmployeeConsole from "../components/employee/EmployeeConsole";
import EmployeeReportCard from "../components/employee/EmployeeReportCard";
import PLUGINS from "../data/plugins";
import { getEmployeeById, deleteEmployee } from "../services/employeeStore";
import { useApp } from "../context/AppContext";

const TABS = [
  { id: "chat", label: "Chat", icon: MessageSquare },
  { id: "console", label: "Console", icon: Terminal },
  { id: "report", label: "Report Card", icon: BarChart3 },
];

export default function EmployeePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { refreshEmployees } = useApp();
  const [activeTab, setActiveTab] = useState("chat");
  const [employee, setEmployee] = useState(null);
  const [loading, setLoading] = useState(true);

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

  const handleDelete = async () => {
    if (window.confirm(`Delete ${employee.name}? This cannot be undone.`)) {
      await deleteEmployee(employee.id);
      await refreshEmployees();
      navigate("/");
    }
  };

  return (
    <div className="flex flex-1 flex-col">
      <div className="border-b border-border/30 px-6 py-4">
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
            onClick={handleDelete}
            className="rounded-lg p-2 text-text-muted transition-colors hover:bg-surface hover:text-red-400"
          >
            <Trash2 size={16} />
          </button>
        </div>
      </div>

      <div className="border-b border-border/20 px-6">
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

      {activeTab === "chat" && <EmployeeChat employee={employee} />}
      {activeTab === "console" && <EmployeeConsole employee={employee} />}
      {activeTab === "report" && <EmployeeReportCard employee={employee} />}
    </div>
  );
}
