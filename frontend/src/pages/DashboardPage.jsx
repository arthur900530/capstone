import { useNavigate } from "react-router-dom";
import { Plus, Users } from "lucide-react";
import EmployeeCard from "../components/dashboard/EmployeeCard";
import TemplateGallery from "../components/dashboard/TemplateGallery";
import { useApp } from "../context/AppContext";

export default function DashboardPage() {
  const { employees } = useApp();
  const navigate = useNavigate();
  const hasEmployees = employees.length > 0;

  return (
    <div className="flex-1 overflow-y-auto px-6 py-8">
      <div className="mx-auto max-w-5xl">
        {/* Header */}
        <div className="mb-8 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-text-primary">
              My Digital Employees
            </h1>
            {hasEmployees && (
              <span className="rounded-full bg-accent-teal/15 px-2.5 py-0.5 text-xs font-semibold text-accent-teal">
                {employees.length}
              </span>
            )}
          </div>
          <button
            onClick={() => navigate("/new")}
            className="flex items-center gap-2 rounded-lg bg-accent-teal px-4 py-2.5 text-sm font-medium text-workspace transition-colors hover:bg-accent-teal/90"
          >
            <Plus size={16} />
            Create New Employee
          </button>
        </div>

        {/* Employee Grid or Empty State */}
        {hasEmployees ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {employees.map((emp) => (
              <EmployeeCard key={emp.id} employee={emp} />
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border/40 py-20">
            <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-surface">
              <Users size={28} className="text-text-muted" />
            </div>
            <h2 className="mb-2 text-lg font-semibold text-text-primary">
              No employees yet
            </h2>
            <p className="mb-6 max-w-sm text-center text-sm text-text-muted">
              Create your first digital employee to get started. Each employee
              is an AI agent configured for a specific role.
            </p>
            <button
              onClick={() => navigate("/new")}
              className="flex items-center gap-2 rounded-lg bg-accent-teal px-5 py-2.5 text-sm font-medium text-workspace transition-colors hover:bg-accent-teal/90"
            >
              <Plus size={16} />
              Create Your First Employee
            </button>
          </div>
        )}

        {/* Template gallery */}
        <TemplateGallery />
      </div>
    </div>
  );
}
