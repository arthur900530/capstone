import { useEffect, useRef, useState } from "react";
import { Star } from "lucide-react";
import { rateTaskRun } from "../services/api";

/**
 * Passive 1–5 rating widget shown beneath an agent's terminal answer.
 *
 * Stays muted by default, highlights on hover, commits on click, and
 * optimistically updates local state so the click feels instant. If the
 * underlying task_run row isn't persisted yet (fresh answer, DB write still
 * in-flight), we retry briefly before surfacing an error.
 */
const RETRY_DELAYS_MS = [400, 800, 1600];

export default function MessageRating({
  employeeId,
  sessionId,
  taskIndex,
  initialRating = null,
  disabled = false,
  onRated,
}) {
  const [rating, setRating] = useState(initialRating ?? null);
  const [hover, setHover] = useState(0);
  const [status, setStatus] = useState("idle"); // idle | saving | error
  const [error, setError] = useState(null);
  const committed = useRef(initialRating ?? null);

  useEffect(() => {
    setRating(initialRating ?? null);
    committed.current = initialRating ?? null;
  }, [initialRating, sessionId, taskIndex]);

  const canRate =
    !disabled &&
    Boolean(employeeId) &&
    Boolean(sessionId) &&
    Number.isInteger(taskIndex);

  async function submit(next) {
    if (!canRate) return;
    setRating(next);
    setStatus("saving");
    setError(null);

    const attempts = [0, ...RETRY_DELAYS_MS];
    for (let i = 0; i < attempts.length; i++) {
      if (attempts[i] > 0) {
        await new Promise((r) => setTimeout(r, attempts[i]));
      }
      try {
        await rateTaskRun(employeeId, sessionId, taskIndex, next);
        committed.current = next;
        setStatus("idle");
        // Lift the rating up so parents (App/ChatView) can keep their
        // context map in sync across tab switches + re-mounts. Fire-and-
        // forget — ignore errors from parent handlers.
        try {
          onRated?.(taskIndex, next);
        } catch {
          // noop
        }
        return;
      } catch (err) {
        if (err?.code === "TASK_RUN_NOT_FOUND" && i < attempts.length - 1) {
          continue;
        }
        setRating(committed.current);
        setStatus("error");
        setError(err?.message || "Failed to save rating");
        return;
      }
    }
  }

  const displayed = hover || rating || 0;

  return (
    <div
      className="mt-2 flex items-center gap-1.5 text-[11px] text-text-muted"
      onMouseLeave={() => setHover(0)}
    >
      <span className="select-none">
        {rating ? "Your rating" : "Rate this answer"}
      </span>
      <div className="flex items-center gap-0.5">
        {[1, 2, 3, 4, 5].map((n) => {
          const filled = n <= displayed;
          return (
            <button
              key={n}
              type="button"
              disabled={!canRate || status === "saving"}
              aria-label={`Rate ${n} of 5`}
              onMouseEnter={() => setHover(n)}
              onClick={() => submit(n)}
              className={`rounded p-0.5 transition-colors ${
                canRate
                  ? "hover:text-amber-300 focus:outline-none focus-visible:ring-1 focus-visible:ring-amber-300/60"
                  : "cursor-not-allowed"
              }`}
            >
              <Star
                size={13}
                className={
                  filled
                    ? "fill-amber-300 text-amber-300"
                    : "text-text-muted/50"
                }
              />
            </button>
          );
        })}
      </div>
      {status === "saving" && (
        <span className="text-text-muted/70">saving…</span>
      )}
      {status === "error" && (
        <span className="text-red-400" title={error}>
          couldn’t save · retry
        </span>
      )}
    </div>
  );
}
