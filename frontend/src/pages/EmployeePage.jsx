import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, MessageSquare, Terminal, BarChart3, Trash2 } from "lucide-react";
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

  const employee = getEmployeeById(id);
  if (!employee) {
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-text-muted">
        Employee not found.
      </div>
    );
  }

  const plugin = PLUGINS.find((p) => p.id === employee.pluginId);
  const RoleIcon = Icons[plugin?.icon] || Icons.Bot;
  const isActive = employee.status === "active";

  const handleDelete = () => {
    if (window.confirm(`Delete ${employee.name}? This cannot be undone.`)) {
      deleteEmployee(employee.id);
      refreshEmployees();
      navigate("/");
    }
  };

  return (
    <div className="flex flex-1 flex-col">
      {/* Header */}
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
                <span
                  className={`h-2 w-2 rounded-full ${
                    isActive ? "bg-green-400" : "bg-text-muted/40"
                  }`}
                />
              </div>
              <p className="text-xs text-text-muted">
                {plugin?.name || "Custom Role"}
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

      {/* Tab bar */}
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

      {/* Tab content */}
      {activeTab === "chat" && <EmployeeChat employee={employee} />}
      {activeTab === "console" && <EmployeeConsole employee={employee} />}
      {activeTab === "report" && <EmployeeReportCard employee={employee} />}
    </div>
  );
}
