import { useState, useRef, useEffect, useCallback } from "react";
import { X, PanelTop, GripHorizontal } from "lucide-react";

const WIDTH = 480;

export default function FloatingWindow({
  title,
  children,
  initialPosition,
  zIndex = 30,
  onClose,
  onDock,
  onFocus,
}) {
  const [pos, setPos] = useState(() => initialPosition || {
    x: Math.max(40, (window.innerWidth - WIDTH) / 2),
    y: 80,
  });
  const containerRef = useRef(null);
  const dragging = useRef(false);
  const offset = useRef({ x: 0, y: 0 });

  const handleMouseDown = useCallback((e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    onFocus?.();
    dragging.current = true;
    const rect = containerRef.current.getBoundingClientRect();
    offset.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    document.body.style.cursor = "grabbing";
    document.body.style.userSelect = "none";
  }, [onFocus]);

  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!dragging.current || !containerRef.current) return;
      const x = Math.max(0, Math.min(e.clientX - offset.current.x, window.innerWidth - WIDTH));
      const y = Math.max(0, Math.min(e.clientY - offset.current.y, window.innerHeight - 60));
      containerRef.current.style.transform = `translate(${x}px, ${y}px)`;
      containerRef.current._dragPos = { x, y };
    };

    const handleMouseUp = () => {
      if (!dragging.current) return;
      dragging.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      if (containerRef.current?._dragPos) {
        setPos(containerRef.current._dragPos);
        delete containerRef.current._dragPos;
      }
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, []);

  return (
    <div
      ref={containerRef}
      onMouseDown={onFocus}
      className="animate-scale-in fixed top-0 left-0 flex flex-col rounded-2xl border border-border/30 bg-workspace shadow-2xl shadow-black/40"
      style={{
        width: WIDTH,
        maxHeight: "80vh",
        zIndex,
        transform: `translate(${pos.x}px, ${pos.y}px)`,
      }}
    >
      {/* Draggable header */}
      <div
        onMouseDown={handleMouseDown}
        className="flex shrink-0 cursor-grab items-center justify-between border-b border-border/40 px-4 py-2.5 active:cursor-grabbing"
      >
        <div className="flex items-center gap-2">
          <GripHorizontal size={14} className="text-text-muted" />
          <span className="text-xs font-medium text-text-primary">{title}</span>
        </div>
        <div className="flex items-center gap-1">
          {onDock && (
            <button
              onClick={onDock}
              className="rounded-md p-1 text-text-muted transition-colors hover:bg-surface hover:text-text-secondary"
              title="Dock to side panel"
            >
              <PanelTop size={13} />
            </button>
          )}
          <button
            onClick={onClose}
            className="rounded-md p-1 text-text-muted transition-colors hover:bg-surface hover:text-text-secondary"
            title="Close"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden">
        {children}
      </div>
    </div>
  );
}
