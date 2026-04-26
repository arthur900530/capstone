import { useState, useEffect } from "react";
import { FileText, CheckCircle } from "lucide-react";

const DATA_ITEMS = [
  { key: "Revenue", value: "$383.3B" },
  { key: "Net Income", value: "$97.0B" },
  { key: "EPS", value: "$6.13" },
  { key: "Operating Margin", value: "30.7%" },
  { key: "Free Cash Flow", value: "$111.4B" },
];

function DataRow({ label, value, index }) {
  return (
    <div
      className="flex items-center justify-between py-2 px-3 rounded-md bg-surface/50"
      style={{
        opacity: 0,
        animation: `fadeIn 0.3s ease-out ${index * 50}ms forwards`,
      }}
    >
      <span className="text-text-secondary text-xs shrink-0">{label}</span>
      <span className="border-b border-dotted border-border/40 flex-1 mx-2" />
      <div className="flex items-center gap-1 shrink-0">
        <span className="text-text-primary text-sm font-medium">{value}</span>
        <span
          className="text-emerald-400"
          style={{
            display: "inline-block",
            opacity: 0,
            animation: `badgeEntrance 0.3s ease-out ${index * 50 + 150}ms forwards`,
          }}
        >
          ✓
        </span>
      </div>
    </div>
  );
}

export default function NotepadScene({ scene = {} }) {
  const { phase = "idle" } = scene;

  const [visibleCount, setVisibleCount] = useState(0);
  const [showBadge, setShowBadge] = useState(false);

  const isExtracting = phase === "extracting" || phase === "extracted";

  useEffect(() => {
    if (!isExtracting) {
      setVisibleCount(0);
      setShowBadge(false);
      return;
    }

    if (phase === "extracted") {
      setVisibleCount(DATA_ITEMS.length);
      setShowBadge(true);
      return;
    }

    // extracting: reveal items one by one
    setVisibleCount(0);
    setShowBadge(false);

    let current = 0;
    const interval = setInterval(() => {
      current++;
      setVisibleCount(current);
      if (current >= DATA_ITEMS.length) {
        clearInterval(interval);
        setTimeout(() => setShowBadge(true), 400);
      }
    }, 400);

    return () => clearInterval(interval);
  }, [phase, isExtracting]);

  return (
    <div className="h-full flex flex-col bg-[#1e1e1e]">
      {/* Header */}
      <div className="h-9 bg-[#2a2a2a] border-b border-border/20 px-4 flex items-center gap-2 text-xs text-text-muted shrink-0">
        <FileText size={13} />
        <span>Extracted Data</span>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden p-4">
        {phase === "idle" && (
          <div className="h-full flex items-center justify-center">
            <span className="text-text-muted text-xs">Waiting for data...</span>
          </div>
        )}

        {isExtracting && (
          <div className="space-y-2">
            {DATA_ITEMS.slice(0, visibleCount).map((item, i) => (
              <DataRow key={item.key} label={item.key} value={item.value} index={i} />
            ))}

            {showBadge && (
              <div
                className="mt-4 flex items-center justify-center gap-2 text-emerald-400 text-xs font-medium"
                style={{
                  opacity: 0,
                  animation: "fadeIn 0.4s ease-out 0ms forwards",
                }}
              >
                <CheckCircle size={14} />
                <span>Extraction Complete</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
