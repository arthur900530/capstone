import EvaluationView from "../components/EvaluationView";
import { useApp } from "../context/AppContext";

export default function EvaluationLabPage() {
  const { agentMap, focusAgentId, setFocusAgentId } = useApp();
  return (
    <EvaluationView
      agentMap={agentMap}
      focusAgentId={focusAgentId}
      onClearFocus={() => setFocusAgentId(null)}
    />
  );
}
