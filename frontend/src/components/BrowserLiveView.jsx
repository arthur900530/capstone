import { useEffect, useMemo, useRef, useState } from "react";
import { Globe, Loader2, MousePointerClick, X } from "lucide-react";
import { useApp } from "../context/appContextCore";

// The agent's VM runs Chromium inside a desktop environment. noVNC streams
// the whole desktop over ``resize=scale``. We measure the panel with a
// ResizeObserver and size the iframe ``contain``-style: fit the full VM
// width horizontally and letterbox vertically if the panel is taller than
// the VM's aspect ratio. This shows the entire VM with no cropping.
const VM_ASPECT_RATIO = 1280 / 800;

function formatAction(action) {
  if (!action?.tool) return "";

  const labels = {
    browser_navigate: "Navigating",
    browser_click: "Clicking",
    browser_type: "Typing",
    browser_scroll: "Scrolling",
    browser_go_back: "Going back",
    browser_switch_tab: "Switching tab",
    browser_close_tab: "Closing tab",
    browser_get_content: "Reading page",
    browser_get_state: "Inspecting page",
  };

  const base = labels[action.tool] || action.tool.replaceAll("_", " ");
  return action.detail ? `${base}: ${action.detail}` : base;
}

export default function BrowserLiveView({ sessionId }) {
  const { browserLive, setBrowserLive } = useApp();
  const [iframeSrc, setIframeSrc] = useState("");
  const [status, setStatus] = useState("Waiting for agent to open the browser...");
  const [panelSize, setPanelSize] = useState({ w: 0, h: 0 });
  const pollTimerRef = useRef(null);
  const panelRef = useRef(null);

  // Observe the panel's size so we can size the iframe ``cover``-style
  // (match VM aspect ratio, fill panel, crop overflow).
  useEffect(() => {
    const el = panelRef.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const apply = () => {
      setPanelSize({ w: el.clientWidth, h: el.clientHeight });
    };
    apply();
    const observer = new ResizeObserver(apply);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const iframeBox = useMemo(() => {
    const { w, h } = panelSize;
    if (!w || !h) return { width: "100%", height: "100%" };
    const panelAspect = w / h;
    // Contain: fit the full VM inside the panel preserving aspect ratio.
    // Letterbox vertically when panel is taller than VM, pillarbox
    // horizontally when panel is wider than VM.
    if (panelAspect > VM_ASPECT_RATIO) {
      // Panel is wider than VM -> constrain by height.
      return {
        width: `${h * VM_ASPECT_RATIO}px`,
        height: `${h}px`,
      };
    }
    return {
      width: `${w}px`,
      height: `${w / VM_ASPECT_RATIO}px`,
    };
  }, [panelSize]);

  const actionText = useMemo(
    () => formatAction(browserLive?.lastAction),
    [browserLive?.lastAction],
  );

  useEffect(() => {
    if (!browserLive?.enabled || !browserLive?.visible) {
      setIframeSrc("");
      return undefined;
    }

    let cancelled = false;

    const poll = async () => {
      try {
        const qs = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : "";
        const res = await fetch(`/api/browser/live${qs}`);
        if (!res.ok) {
          throw new Error(`Live browser not ready (status ${res.status})`);
        }
        const data = await res.json();
        if (cancelled) return;
        if (data?.url && data.url !== iframeSrc) {
          setIframeSrc(data.url);
          setStatus("Connecting to live browser…");
        } else if (!data?.url) {
          setStatus("Live browser not available yet.");
        }
      } catch {
        if (cancelled) return;
        setStatus("Waiting for agent browser to come online…");
      } finally {
        if (!cancelled) {
          pollTimerRef.current = window.setTimeout(poll, 2500);
        }
      }
    };

    poll();

    return () => {
      cancelled = true;
      if (pollTimerRef.current) {
        window.clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [browserLive?.enabled, browserLive?.visible, sessionId, iframeSrc]);

  return (
    <div className="flex h-full flex-col bg-[#11161f]">
      <div className="border-b border-white/10 px-4 py-3">
        <div className="mb-2 flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm font-medium text-white">
            <Globe size={15} className="text-cyan-300" />
            Live Browser
          </div>
          <div className="flex items-center gap-2">
            {/* <div className="text-[11px] text-slate-400">noVNC</div> */}
            {setBrowserLive && (
              <button
                type="button"
                onClick={() =>
                  setBrowserLive((prev) => ({ ...prev, visible: false }))
                }
                className="flex h-6 w-6 items-center justify-center rounded-md text-slate-400 transition-colors hover:bg-white/10 hover:text-white"
                title="Hide live browser"
                aria-label="Hide live browser"
              >
                <X size={14} />
              </button>
            )}
          </div>
        </div>
        {/* <div className="truncate rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs text-slate-300">
          {iframeReady ? "Streaming agent Chromium" : status}
        </div> */}
      </div>

      <div
        ref={panelRef}
        className="relative flex-1 overflow-hidden bg-[#0b0f16]"
      >
        {iframeSrc ? (
          <iframe
            key={iframeSrc}
            src={iframeSrc}
            title="Agent browser (noVNC)"
            className="absolute left-1/2 top-1/2 border-0 bg-black"
            style={{
              width: iframeBox.width,
              height: iframeBox.height,
              transform: "translate(-50%, -50%)",
              transformOrigin: "center center",
            }}
            allow="clipboard-read; clipboard-write"
          />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
            <Loader2 size={20} className="animate-spin text-cyan-300" />
            <div className="text-sm text-slate-200">{status}</div>
            <div className="max-w-sm text-xs text-slate-500">
              The panel connects automatically once the agent Chromium is up.
              The view is read-only while the agent is working.
            </div>
          </div>
        )}

        {actionText && (
          <div className="pointer-events-none absolute bottom-4 left-4 right-4">
            <div className="inline-flex max-w-full items-center gap-2 rounded-full border border-cyan-400/20 bg-slate-950/75 px-3 py-2 text-xs text-cyan-100 shadow-lg backdrop-blur">
              <MousePointerClick size={13} className="shrink-0 text-cyan-300" />
              <span className="truncate">{actionText}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
