import { useNavigate } from "react-router-dom";
import * as Icons from "lucide-react";
import PLUGINS from "../../data/plugins";

export default function EmployeeCard({ employee }) {
  const navigate = useNavigate();
  const plugin = PLUGINS.find((p) => p.id === employee.pluginId);
  const IconComp = Icons[plugin?.icon] || Icons.Bot;
  const isActive = employee.status === "active";

  return (
    <button
      onClick={() => navigate(`/employee/${employee.id}`)}
      className="flex flex-col gap-3 rounded-xl border border-border/40 bg-surface p-5 text-left transition-all hover:border-accent-teal/40 hover:bg-surface-hover"
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent-teal/10">
            <IconComp size={20} className="text-accent-teal" />
          </div>
          <div>
            <h3 className="font-semibold text-text-primary">{employee.name}</h3>
            <p className="text-xs text-text-muted">
              {plugin?.name || "Custom Role"}
            </p>
          </div>
        </div>
        <span
          className={`mt-1 h-2.5 w-2.5 rounded-full ${
            isActive ? "bg-green-400" : "bg-text-muted/40"
          }`}
        />
      </div>

      <p className="line-clamp-2 text-sm text-text-secondary">
        {employee.task}
      </p>

      <div className="flex items-center justify-between text-xs text-text-muted">
        <span>
          {employee.chatSessionIds.length}{" "}
          {employee.chatSessionIds.length === 1 ? "chat" : "chats"}
        </span>
        <span>
          {new Date(employee.createdAt).toLocaleDateString()}
        </span>
      </div>
    </button>
  );
}
