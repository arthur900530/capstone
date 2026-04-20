import { Globe, Terminal, Code, FileText } from "lucide-react";

const TYPE_ICONS = {
  browser:  Globe,
  terminal: Terminal,
  editor:   Code,
  notepad:  FileText,
};

export default function DesktopWindow({
  title,
  type,
  isActive,
  isMinimized,
  style,
  onFocus,
  children,
}) {
  const Icon = TYPE_ICONS[type] || Globe;

  const ringClass = isActive
    ? "ring-1 ring-accent-teal/20 shadow-accent-teal/5"
    : "ring-1 ring-white/5";

  const animationClass = isMinimized ? "animate-minimize" : "animate-slide-up";

  return (
    <div
      className={`absolute flex flex-col rounded-lg overflow-hidden shadow-2xl transition-all ${ringClass} ${animationClass}`}
      style={{ ...style, zIndex: isMinimized ? undefined : style?.zIndex }}
      onMouseDown={onFocus}
    >
      {/* Title bar */}
      <div className="h-8 bg-[#2a2a2a] border-b border-[#1a1a1a] flex items-center px-3 gap-2 shrink-0">
        {/* Traffic lights */}
        <div className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#febc2e]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
        </div>

        {/* Title */}
        <div className="flex-1 text-center text-xs text-text-muted font-medium truncate">
          {title}
        </div>

        {/* Window type icon */}
        <Icon size={13} className="text-text-muted shrink-0" />
      </div>

      {/* Content area */}
      <div className="flex-1 overflow-hidden bg-[#1e1e1e]">
        {children}
      </div>
    </div>
  );
}
