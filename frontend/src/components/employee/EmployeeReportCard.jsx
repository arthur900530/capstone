import { BarChart3 } from "lucide-react";
import EvaluationView from "../EvaluationView";
import { useApp } from "../../context/AppContext";

export default function EmployeeReportCard({ employee }) {
  const { agentMap } = useApp();

  // Try to find a matching agent for this employee's model
  const matchingAgent = Object.values(agentMap).find(
    (a) => a.model === employee.model,
  );

  if (!matchingAgent) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center">
        <BarChart3 size={28} className="mb-3 text-text-muted" />
        <p className="mb-1 text-sm font-medium text-text-primary">
          No performance data yet
        </p>
        <p className="max-w-xs text-center text-xs text-text-muted">
          Start a conversation to generate metrics. Evaluation data will appear
          here once {employee.name} has completed some tasks.
        </p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <EvaluationView
        agentMap={agentMap}
        focusAgentId={matchingAgent.id}
        onClearFocus={() => {}}
      />
    </div>
  );
}
