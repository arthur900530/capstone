import { useEffect, useMemo, useRef, useState } from "react";
import { CircleAlert, Globe, Loader2, X } from "lucide-react";
import RFB from "@novnc/novnc";
import { useApp } from "../context/appContextCore";

// Same letterbox math as BrowserLiveView so the replay pane sizes
// identically to the live one.
const VM_ASPECT_RATIO = 1280 / 800;

function base64ToArrayBuffer(b64) {
  // ``atob`` is fine for the websockify byte stream — frames are short
  // ASCII strings produced server-side. For 100k+ messages this is still
  // microseconds per frame.
  const bin = atob(b64);
  const len = bin.length;
  const buf = new ArrayBuffer(len);
  const view = new Uint8Array(buf);
  for (let i = 0; i < len; i += 1) view[i] = bin.charCodeAt(i);
  return buf;
}

/**
 * A WebSocket-shaped object that emits recorded RFB byte frames on a
 * virtual clock. ``RFB`` accepts this object directly via its second
 * constructor argument — the constructor calls ``Websock.attach()`` which
 * sets ``onopen``/``onmessage`` on the channel. We then call those
 * handlers ourselves at the recorded timestamps.
 */
class FakeRfbSocket {
  constructor() {
    this.binaryType = "arraybuffer";
    this.protocol = "binary";
    this.readyState = 0; // CONNECTING
    this.onopen = null;
    this.onmessage = null;
    this.onerror = null;
    this.onclose = null;
    this._timers = [];
    this._opened = false;
  }

  // Required by Websock.attach()'s rawChannelProps check, but as a
  // passive replay channel we can ignore everything sent by the client.
  send(_data) {}

  close(_code, _reason) {
    this.readyState = 3; // CLOSED
    if (this.onclose) {
      try {
        this.onclose({ code: 1000, reason: "" });
      } catch {
        /* ignore */
      }
    }
    this._cancelTimers();
  }

  /** Schedule frames against ``performance.now()`` baseline ``startMs``. */
  start(frames, { startMs = performance.now() } = {}) {
    if (this._opened) return;
    this._opened = true;
    this.readyState = 1; // OPEN
    if (this.onopen) {
      try {
        this.onopen({});
      } catch (err) {
        // noVNC tolerates onopen throwing; surface in console either way.
        console.warn("[BrowserReplayView] onopen handler threw", err);
      }
    }

    let prev = 0;
    for (const f of frames) {
      const t = Math.max(0, Number(f.t) || 0);
      const delay = startMs + t - performance.now();
      const id = setTimeout(
        () => {
          if (this.readyState !== 1) return;
          if (!this.onmessage) return;
          try {
            this.onmessage({ data: base64ToArrayBuffer(f.b64) });
          } catch (err) {
            console.warn("[BrowserReplayView] onmessage threw", err);
          }
        },
        Math.max(0, delay),
      );
      this._timers.push(id);
      prev = t;
    }
    void prev;
  }

  _cancelTimers() {
    for (const id of this._timers) clearTimeout(id);
    this._timers = [];
  }
}

export default function BrowserReplayView({ sessionId }) {
  const { setBrowserLive, replayMeta } = useApp();
  const targetRef = useRef(null);
  const panelRef = useRef(null);
  const rfbRef = useRef(null);
  const fakeSockRef = useRef(null);
  const [panelSize, setPanelSize] = useState({ w: 0, h: 0 });
  const [status, setStatus] = useState(
    replayMeta ? "Loading recorded browser…" : "Waiting for replay metadata…",
  );
  // Distinguishes the "still loading / no metadata" state from a hard
  // empty / failure state so we can pick the right overlay treatment.
  // States: "idle" | "loading" | "playing" | "empty" | "error"
  const [phase, setPhase] = useState(replayMeta ? "loading" : "idle");

  useEffect(() => {
    const el = panelRef.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const apply = () => setPanelSize({ w: el.clientWidth, h: el.clientHeight });
    apply();
    const observer = new ResizeObserver(apply);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const iframeBox = useMemo(() => {
    const { w, h } = panelSize;
    if (!w || !h) return { width: "100%", height: "100%" };
    const panelAspect = w / h;
    if (panelAspect > VM_ASPECT_RATIO) {
      return { width: `${h * VM_ASPECT_RATIO}px`, height: `${h}px` };
    }
    return { width: `${w}px`, height: `${w / VM_ASPECT_RATIO}px` };
  }, [panelSize]);

  // Tear down any existing RFB / fake socket whenever replay meta changes
  // (i.e. a new turn starts) so each turn replays from a clean slate.
  useEffect(() => {
    let cancelled = false;
    if (!replayMeta?.browserFramesUrl) {
      setStatus("Waiting for replay metadata…");
      setPhase("idle");
      return () => {
        cancelled = true;
      };
    }
    setStatus("Loading recorded browser…");
    setPhase("loading");

    const cleanup = () => {
      if (rfbRef.current) {
        try {
          rfbRef.current.disconnect();
        } catch {
          /* ignore */
        }
        rfbRef.current = null;
      }
      if (fakeSockRef.current) {
        try {
          fakeSockRef.current.close();
        } catch {
          /* ignore */
        }
        fakeSockRef.current = null;
      }
      if (targetRef.current) {
        // RFB injects a <canvas>; clear it on tear-down.
        targetRef.current.innerHTML = "";
      }
    };

    cleanup();

    (async () => {
      try {
        const res = await fetch(replayMeta.browserFramesUrl);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (cancelled) return;
        const frames = (data?.frames || []).filter((f) => f.dir === "s2c");
        if (frames.length === 0) {
          setStatus(
            "This recording captured the chat trajectory but no browser " +
              "framebuffer. Re-run with ./start.sh --record while the agent " +
              "uses the browser to populate it.",
          );
          setPhase("empty");
          return;
        }
        if (!targetRef.current) return;

        const fakeSock = new FakeRfbSocket();
        fakeSockRef.current = fakeSock;
        try {
          rfbRef.current = new RFB(targetRef.current, fakeSock, {});
        } catch (err) {
          console.error("[BrowserReplayView] RFB construction failed", err);
          setStatus("Failed to initialize replay viewer.");
          setPhase("error");
          return;
        }
        try {
          rfbRef.current.scaleViewport = true;
        } catch {
          /* ignore */
        }
        // Kick the replay clock ~50ms in the future so noVNC has finished
        // wiring up onopen/onmessage handlers before frames start firing.
        fakeSock.start(frames, { startMs: performance.now() + 50 });
        setStatus("Replaying recorded browser session…");
        setPhase("playing");
      } catch (err) {
        console.error("[BrowserReplayView] failed to load frames", err);
        setStatus("Failed to load recorded browser frames.");
        setPhase("error");
      }
    })();

    return () => {
      cancelled = true;
      cleanup();
    };
  }, [replayMeta?.browserFramesUrl, replayMeta?.turn, replayMeta?.recordingId]);

  return (
    <div className="flex h-full flex-col bg-[#11161f]">
      <div className="border-b border-white/10 px-4 py-3">
        <div className="mb-2 flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm font-medium text-white">
            <Globe size={15} className="text-cyan-300" />
            Live Browser
          </div>
          <div className="flex items-center gap-2">
            {setBrowserLive && (
              <button
                type="button"
                onClick={() =>
                  setBrowserLive((prev) => ({ ...prev, visible: false }))
                }
                className="flex h-6 w-6 items-center justify-center rounded-md text-slate-400 transition-colors hover:bg-white/10 hover:text-white"
                title="Hide browser"
                aria-label="Hide browser"
              >
                <X size={14} />
              </button>
            )}
          </div>
        </div>
      </div>

      <div ref={panelRef} className="relative flex-1 overflow-hidden bg-[#0b0f16]">
        {/* The RFB canvas mount target is *always* in the DOM so the
            ``targetRef.current`` lookup that constructs ``RFB`` succeeds
            (it runs while ``phase === "loading"``, before we transition
            to "playing"). We hide it via ``visibility`` while not playing
            so it doesn't paint a black rectangle over the overlay. */}
        <div
          ref={targetRef}
          className="absolute left-1/2 top-1/2 bg-black"
          style={{
            width: iframeBox.width,
            height: iframeBox.height,
            transform: "translate(-50%, -50%)",
            transformOrigin: "center center",
            visibility: phase === "playing" ? "visible" : "hidden",
          }}
        />

        {phase !== "playing" && (
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center gap-3 px-6 text-center">
            {phase === "empty" || phase === "error" ? (
              <CircleAlert
                size={28}
                className={
                  phase === "error" ? "text-rose-400" : "text-amber-300"
                }
              />
            ) : (
              <Loader2 size={20} className="animate-spin text-cyan-300" />
            )}
            <div className="max-w-md text-sm text-slate-200">{status}</div>
            <div className="max-w-sm text-xs text-slate-500">
              The recorded noVNC framebuffer plays here, in lock-step with
              the chat trajectory. No live agent runtime is running in
              demo mode.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
