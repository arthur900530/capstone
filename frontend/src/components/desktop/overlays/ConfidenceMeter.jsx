import { CheckCircle2, AlertTriangle } from "lucide-react";

function barColor(score) {
  if (score >= 0.7) return "bg-emerald-400";
  if (score >= 0.4) return "bg-yellow-400";
  return "bg-red-400";
}

function textColor(score) {
  if (score >= 0.7) return "text-emerald-400";
  if (score >= 0.4) return "text-yellow-400";
  return "text-red-400";
}

export default function ConfidenceMeter({ score, isConfident, visible }) {
  const color = barColor(score);
  const text = textColor(score);

  return (
    <div
      className={`absolute bottom-14 right-3 rounded-lg bg-surface/90 backdrop-blur p-3 w-40 transition-opacity duration-300 ${
        visible ? "opacity-100" : "opacity-0"
      }`}
    >
      <span className="text-[10px] text-text-muted uppercase tracking-wider">
        Confidence
      </span>

      <div className="h-2 rounded-full bg-[#1a1a1a] mt-1.5 overflow-hidden">
        <div
          className={`h-full rounded-full animate-meter ${color}`}
          style={{ width: `${Math.round(score * 100)}%` }}
        />
      </div>

      <p className={`mt-1 text-right text-xs font-medium ${text}`}>
        {Math.round(score * 100)}%
      </p>

      <div className={`mt-1 flex items-center gap-1 text-[10px]`}>
        {isConfident ? (
          <>
            <CheckCircle2 size={12} className="text-emerald-400" />
            <span className="text-emerald-400">Confident</span>
          </>
        ) : (
          <>
            <AlertTriangle size={12} className="text-yellow-400" />
            <span className="text-yellow-400">Uncertain</span>
          </>
        )}
      </div>
    </div>
  );
}
