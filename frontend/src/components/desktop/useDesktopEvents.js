import { useState, useCallback, useRef } from "react";

let nextZIndex = 10;

const WINDOW_DEFAULTS = {
  browser:  { title: "Chrome",       style: { top: "5%",  left: "3%",  width: "90%", height: "68%" } },
  terminal: { title: "Terminal",     style: { top: "12%", left: "8%",  width: "78%", height: "58%" } },
  editor:   { title: "VS Code",      style: { top: "6%",  left: "5%",  width: "85%", height: "72%" } },
  notepad:  { title: "Data Extract", style: { top: "18%", left: "12%", width: "65%", height: "55%" } },
};

const RESULT_PHASE = {
  searching:      "results_shown",
  edgar:          "results_shown",
  reading:        "reading_done",
  extracting:     "extracted",
  typing_command: "command_done",
  editing:        "edit_done",
};

export default function useDesktopEvents() {
  const [windows, setWindows] = useState([]);
  const [activeWindowId, setActiveWindowId] = useState(null);
  const [scenes, setScenes] = useState({});
  const [overlays, setOverlays] = useState({
    thinking: false,
    confidence: { score: 0, visible: false, isConfident: false },
    reportReady: false,
  });
  const [isIdle, setIsIdle] = useState(true);
  const [isStreaming, setIsStreaming] = useState(false);

  // Ref mirrors for synchronous reads inside callbacks
  const windowsRef = useRef([]);
  const activeWindowIdRef = useRef(null);

  const thinkingTimer = useRef(null);
  const confidenceTimer = useRef(null);

  // Keep refs in sync
  const syncedSetWindows = useCallback((updater) => {
    setWindows((prev) => {
      const next = typeof updater === "function" ? updater(prev) : updater;
      windowsRef.current = next;
      return next;
    });
  }, []);

  // ── Helpers ──────────────────────────────────────────────

  const bringToFront = useCallback((id) => {
    const z = ++nextZIndex;
    syncedSetWindows((prev) =>
      prev.map((w) => (w.id === id ? { ...w, zIndex: z, minimized: false } : w))
    );
    setActiveWindowId(id);
    activeWindowIdRef.current = id;
  }, [syncedSetWindows]);

  /** Returns the window id (existing or newly created). */
  const openOrFocusWindow = useCallback((type) => {
    const existing = windowsRef.current.find((w) => w.type === type);
    if (existing) {
      bringToFront(existing.id);
      return existing.id;
    }
    const id = `${type}-${Date.now()}`;
    const defaults = WINDOW_DEFAULTS[type] || WINDOW_DEFAULTS.browser;
    const z = ++nextZIndex;
    syncedSetWindows((prev) => [
      ...prev,
      { id, type, title: defaults.title, style: defaults.style, zIndex: z, minimized: false },
    ]);
    setActiveWindowId(id);
    activeWindowIdRef.current = id;
    return id;
  }, [bringToFront, syncedSetWindows]);

  const setScene = useCallback((windowId, sceneState) => {
    setScenes((prev) => ({ ...prev, [windowId]: sceneState }));
  }, []);

  const minimizeAll = useCallback(() => {
    syncedSetWindows((prev) => prev.map((w) => ({ ...w, minimized: true })));
    setActiveWindowId(null);
    activeWindowIdRef.current = null;
  }, [syncedSetWindows]);

  const showOverlay = useCallback((name, data = {}) => {
    if (name === "thinking") {
      clearTimeout(thinkingTimer.current);
      setOverlays((prev) => ({ ...prev, thinking: true }));
      thinkingTimer.current = setTimeout(() => {
        setOverlays((prev) => ({ ...prev, thinking: false }));
      }, 3000);
    } else if (name === "confidence") {
      clearTimeout(confidenceTimer.current);
      setOverlays((prev) => ({
        ...prev,
        confidence: { score: data.score ?? 0, visible: true, isConfident: data.isConfident ?? false },
      }));
      confidenceTimer.current = setTimeout(() => {
        setOverlays((prev) => ({
          ...prev,
          confidence: { ...prev.confidence, visible: false },
        }));
      }, 5000);
    } else if (name === "reportReady") {
      setOverlays((prev) => ({ ...prev, reportReady: true }));
    }
  }, []);

  const hideOverlay = useCallback((name) => {
    if (name === "thinking") {
      clearTimeout(thinkingTimer.current);
      setOverlays((prev) => ({ ...prev, thinking: false }));
    } else if (name === "confidence") {
      clearTimeout(confidenceTimer.current);
      setOverlays((prev) => ({
        ...prev,
        confidence: { ...prev.confidence, visible: false },
      }));
    }
  }, []);

  const resetDesktop = useCallback(() => {
    windowsRef.current = [];
    activeWindowIdRef.current = null;
    syncedSetWindows([]);
    setActiveWindowId(null);
    setScenes({});
    setOverlays({ thinking: false, confidence: { score: 0, visible: false, isConfident: false }, reportReady: false });
    setIsIdle(true);
    setIsStreaming(false);
    clearTimeout(thinkingTimer.current);
    clearTimeout(confidenceTimer.current);
  }, [syncedSetWindows]);

  // ── Event processor ──────────────────────────────────────

  const processEvent = useCallback((eventType, data = {}) => {
    setIsIdle(false);
    setIsStreaming(true);

    switch (eventType) {
      case "tool_call": {
        // Clear thinking overlay on any new tool call
        hideOverlay("thinking");

        const tool = data.tool || "";

        if (tool === "web_search") {
          const winId = openOrFocusWindow("browser");
          setScene(winId, { phase: "searching", query: data.detail });

        } else if (tool === "edgar_search") {
          const winId = openOrFocusWindow("browser");
          setScene(winId, { phase: "edgar", query: data.detail });

        } else if (tool === "parse_html") {
          const existing = windowsRef.current.find((w) => w.type === "browser");
          if (existing) {
            bringToFront(existing.id);
            setScene(existing.id, { phase: "reading", detail: data.detail });
          }

        } else if (tool === "retrieve_info" || tool === "retrieve_information") {
          const winId = openOrFocusWindow("notepad");
          setScene(winId, { phase: "extracting", detail: data.detail });

        } else if (tool === "terminal") {
          const winId = openOrFocusWindow("terminal");
          setScene(winId, { phase: "typing_command", command: data.detail });

        } else if (tool === "file_editor") {
          const winId = openOrFocusWindow("editor");
          setScene(winId, { phase: "editing", detail: data.detail });

        } else if (
          tool === "submit_result" ||
          tool === "submit_final_result" ||
          tool === "finish" ||
          tool === "FinishTool"
        ) {
          minimizeAll();
          showOverlay("reportReady");
          setIsStreaming(false);
        }
        break;
      }

      case "tool_result": {
        // Advance the frontmost non-minimized window's scene to its result phase
        const sorted = [...windowsRef.current]
          .filter((w) => !w.minimized)
          .sort((a, b) => b.zIndex - a.zIndex);
        const active = sorted[0];
        if (active) {
          setScenes((prev) => {
            const current = prev[active.id];
            if (!current) return prev;
            const nextPhase = RESULT_PHASE[current.phase];
            if (!nextPhase) return prev;
            return { ...prev, [active.id]: { ...current, phase: nextPhase } };
          });
        }
        break;
      }

      case "reasoning": {
        showOverlay("thinking");
        break;
      }

      case "self_eval": {
        showOverlay("confidence", {
          score: data.confidence_score ?? 0,
          isConfident: data.is_confident ?? false,
        });
        break;
      }

      case "reflection": {
        hideOverlay("confidence");
        showOverlay("thinking");
        break;
      }

      case "answer": {
        minimizeAll();
        showOverlay("reportReady");
        setIsStreaming(false);
        break;
      }

      case "status":
      case "trial_start":
        // No desktop action
        break;

      default:
        break;
    }
  }, [openOrFocusWindow, setScene, minimizeAll, showOverlay, hideOverlay, bringToFront]);

  return {
    windows,
    activeWindowId,
    scenes,
    overlays,
    isIdle,
    isStreaming,
    processEvent,
    openOrFocusWindow,
    setScene,
    minimizeAll,
    showOverlay,
    resetDesktop,
    bringToFront,
  };
}
