import { useEffect } from "react";
import { Bot } from "lucide-react";
import useDesktopEvents from "./useDesktopEvents";
import DesktopWindow from "./DesktopWindow";
import DesktopTaskbar from "./DesktopTaskbar";
import BrowserScene from "./scenes/BrowserScene";
import TerminalScene from "./scenes/TerminalScene";
import EditorScene from "./scenes/EditorScene";
import NotepadScene from "./scenes/NotepadScene";
import ThinkingOverlay from "./overlays/ThinkingOverlay";
import ConfidenceMeter from "./overlays/ConfidenceMeter";
import ReportReady from "./overlays/ReportReady";

const SCENE_COMPONENTS = {
  browser: BrowserScene,
  terminal: TerminalScene,
  editor: EditorScene,
  notepad: NotepadScene,
};

export default function DesktopSimulator({ employee, onEventRef }) {
  const {
    windows,
    activeWindowId,
    scenes,
    overlays,
    isIdle,
    isStreaming,
    processEvent,
    bringToFront,
  } = useDesktopEvents();

  useEffect(() => {
    onEventRef.current = processEvent;
    return () => {
      onEventRef.current = null;
    };
  }, [onEventRef, processEvent]);

  const sortedWindows = [...windows].sort((a, b) => a.zIndex - b.zIndex);

  return (
    <div className="relative flex flex-1 flex-col overflow-hidden rounded-lg">
      {/* Status bar */}
      <div className="bg-[#0d0d0d]/80 h-6 px-3 flex items-center text-[10px] text-text-muted gap-2">
        <span>{employee.name}</span>
        {isStreaming && (
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-green-400 animate-pulse" />
        )}
      </div>

      {/* Desktop area with wallpaper */}
      <div
        className="relative flex-1"
        style={{
          backgroundColor: "#1a1a1a",
          backgroundImage: "radial-gradient(circle, #3a3a3a 1px, transparent 1px)",
          backgroundSize: "24px 24px",
        }}
      >
        {/* Desktop content area */}
        <div className="relative flex-1 p-3 h-full">
          {/* Idle placeholder */}
          {isIdle && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-2">
              <Bot size={32} className="text-text-muted animate-pulse" />
              <span className="text-xs text-text-muted">Waiting for instructions...</span>
            </div>
          )}

          {/* Windows */}
          {sortedWindows
            .filter((w) => !w.minimized)
            .map((w) => {
              const SceneComponent = SCENE_COMPONENTS[w.type];
              return (
                <DesktopWindow
                  key={w.id}
                  title={w.title}
                  type={w.type}
                  isActive={w.id === activeWindowId}
                  isMinimized={w.minimized}
                  style={w.style}
                  onFocus={() => bringToFront(w.id)}
                >
                  {SceneComponent && <SceneComponent scene={scenes[w.id] || { phase: "idle" }} />}
                </DesktopWindow>
              );
            })}

          {/* Overlays */}
          <ThinkingOverlay visible={overlays.thinking} />
          <ConfidenceMeter
            score={overlays.confidence.score}
            isConfident={overlays.confidence.isConfident}
            visible={overlays.confidence.visible}
          />
          <ReportReady
            visible={overlays.reportReady}
            employeeName={employee.name}
          />
        </div>
      </div>

      {/* Taskbar */}
      <DesktopTaskbar
        windows={windows}
        activeWindowId={activeWindowId}
        onWindowClick={bringToFront}
      />
    </div>
  );
}
