import { Brain } from "lucide-react";

export default function ThinkingOverlay({ visible }) {
  return (
    <div
      className={`absolute top-3 right-3 flex items-center gap-2 rounded-full px-3 py-1.5 bg-yellow-400/10 backdrop-blur animate-pulse-glow transition-opacity duration-300 ${
        visible ? "opacity-100" : "opacity-0"
      }`}
    >
      <Brain size={14} className="text-yellow-400" />
      <span className="text-xs text-yellow-400/80">Thinking...</span>
    </div>
  );
}
