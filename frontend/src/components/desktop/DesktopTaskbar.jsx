import { useState, useEffect } from "react";
import { Globe, Terminal, Code, FileText } from "lucide-react";

const TYPE_ICONS = {
  browser:  Globe,
  terminal: Terminal,
  editor:   Code,
  notepad:  FileText,
};

function Clock() {
  const [time, setTime] = useState(() => {
    const now = new Date();
    return now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  });

  useEffect(() => {
    const now = new Date();
    const msUntilNextMinute = (60 - now.getSeconds()) * 1000 - now.getMilliseconds();
    let intervalId = null;

    const tick = () => {
      setTime(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
    };

    const timeoutId = setTimeout(() => {
      tick();
      intervalId = setInterval(tick, 60000);
    }, msUntilNextMinute);

    return () => {
      clearTimeout(timeoutId);
      if (intervalId) clearInterval(intervalId);
    };
  }, []);

  return (
    <span className="text-[10px] text-text-muted tabular-nums">
      {time}
    </span>
  );
}

export default function DesktopTaskbar({ windows, activeWindowId, onWindowClick }) {
  const visible = windows.filter((w) => !w.minimized || true); // show all windows in taskbar

  return (
    <div className="h-10 bg-[#0d0d0d]/90 backdrop-blur border-t border-border/20 flex items-center px-4 shrink-0">
      {/* Left spacer */}
      <div className="flex-1" />

      {/* Window icons — centered */}
      <div className="flex items-center gap-1">
        {windows.map((win) => {
          const Icon = TYPE_ICONS[win.type] || Globe;
          const isActive = win.id === activeWindowId;

          return (
            <div key={win.id} className="relative flex flex-col items-center">
              <button
                onClick={() => onWindowClick(win.id)}
                className={`h-8 w-8 rounded-lg flex items-center justify-center transition-colors hover:bg-surface-hover ${
                  isActive ? "bg-surface" : ""
                }`}
                title={win.title}
              >
                <Icon size={16} className={isActive ? "text-accent-teal" : "text-text-secondary"} />
              </button>
              {isActive && (
                <span className="absolute -bottom-0.5 h-0.5 w-3 rounded-full bg-accent-teal" />
              )}
            </div>
          );
        })}
      </div>

      {/* Right side — clock */}
      <div className="flex-1 flex items-center justify-end">
        <Clock />
      </div>
    </div>
  );
}
