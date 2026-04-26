
import { useState, useEffect, useRef } from "react";
import {
  FileCode2,
  FilePlus2,
  FilePen,
  FileSearch,
  Undo2,
  ChevronDown,
  ChevronRight,
  Copy,
  Check,
} from "lucide-react";


const COMMAND_META = {
  create:      { label: "Created",  Icon: FilePlus2,  accent: "emerald" },
  str_replace: { label: "Edited",   Icon: FilePen,    accent: "amber" },
  insert:      { label: "Inserted", Icon: FilePen,    accent: "amber" },
  view:        { label: "Viewed",   Icon: FileSearch,  accent: "sky" },
  undo_edit:   { label: "Reverted", Icon: Undo2,      accent: "rose" },
};

const ACCENT_CLASSES = {
  emerald: {
    badge: "bg-emerald-400/15 text-emerald-400 ring-emerald-400/20",
    glow:  "border-emerald-500/30",
    dot:   "bg-emerald-400",
  },
  amber: {
    badge: "bg-amber-400/15 text-amber-400 ring-amber-400/20",
    glow:  "border-amber-500/30",
    dot:   "bg-amber-400",
  },
  sky: {
    badge: "bg-sky-400/15 text-sky-400 ring-sky-400/20",
    glow:  "border-sky-500/30",
    dot:   "bg-sky-400",
  },
  rose: {
    badge: "bg-rose-400/15 text-rose-400 ring-rose-400/20",
    glow:  "border-rose-500/30",
    dot:   "bg-rose-400",
  },
};

/* ── Line-reveal hook ──────────────────────────────────────────── */
function useLineReveal(totalLines, { enabled = true, interval = 80 } = {}) {
  const [revealed, setRevealed] = useState(enabled ? 0 : totalLines);
  const timerRef = useRef(null);

  useEffect(() => {
    if (!enabled) {
      return;
    }
    let current = 0;
    const resetTimer = window.setTimeout(() => setRevealed(0), 0);
    timerRef.current = setInterval(() => {
      current += 1;
      if (current >= totalLines) {
        clearInterval(timerRef.current);
        setRevealed(totalLines);
      } else {
        setRevealed(current);
      }
    }, interval);
    return () => {
      window.clearTimeout(resetTimer);
      clearInterval(timerRef.current);
    };
  }, [totalLines, enabled, interval]);

  return enabled ? revealed : totalLines;
}

function basename(path) {
  return path?.split("/").pop() || path || "unknown";
}

function langFromPath(path) {
  const ext = path?.split(".").pop()?.toLowerCase();
  const map = {
    py: "python", js: "javascript", ts: "typescript", jsx: "jsx", tsx: "tsx",
    json: "json", md: "markdown", yml: "yaml", yaml: "yaml", sh: "bash",
    css: "css", html: "html", sql: "sql", rs: "rust", go: "go", java: "java",
  };
  return map[ext] || "";
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <button
      onClick={handleCopy}
      className="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-text-muted hover:bg-surface-hover hover:text-text-secondary transition-colors"
      title="Copy to clipboard"
    >
      {copied ? <Check size={11} className="text-emerald-400" /> : <Copy size={11} />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

/* ── Line-numbered code block ──────────────────────────────────── */
function CodeBlock({ code, startLine = 1, animate = true }) {
  const hasCode = Boolean(code);
  const lines = hasCode ? code.replace(/\n$/, "").split("\n") : [];
  const gutterWidth = String(startLine + lines.length - 1).length;
  const revealed = useLineReveal(lines.length, { enabled: animate && hasCode });
  const done = revealed >= lines.length;

  if (!hasCode) return null;

  return (
    <div className="fe-code-block overflow-x-auto rounded-b-lg bg-[#1a1a1a] font-mono text-xs leading-[1.6]">
      <table className="w-full border-collapse">
        <tbody>
          {lines.slice(0, revealed).map((line, i) => (
            <tr key={i} className={`hover:bg-white/3 ${i === revealed - 1 && !done ? "animate-fe-line" : ""}`}>
              <td
                className="select-none border-r border-border/20 px-2 text-right text-text-muted/40"
                style={{ width: `${gutterWidth + 2}ch` }}
              >
                {startLine + i}
              </td>
              <td className="px-3 text-text-primary/90 whitespace-pre">{line || "\u00a0"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {!done && (
        <div className="px-3 py-0.5">
          <span className="inline-block h-3.5 w-0.5 animate-pulse bg-accent-teal/70" />
        </div>
      )}
    </div>
  );
}

/* ── Diff view (str_replace) ───────────────────────────────────── */
function DiffView({ oldStr, newStr, animate = true }) {
  const hasDiff = Boolean(oldStr || newStr);
  const oldLines = oldStr ? oldStr.replace(/\n$/, "").split("\n") : [];
  const newLines = newStr ? newStr.replace(/\n$/, "").split("\n") : [];
  const allCount = oldLines.length + newLines.length;
  const revealed = useLineReveal(allCount, { enabled: animate && hasDiff, interval: 80 });
  const done = revealed >= allCount;

  const oldRevealed = Math.min(revealed, oldLines.length);
  const newRevealed = Math.max(0, revealed - oldLines.length);

  if (!hasDiff) return null;

  return (
    <div className="fe-code-block overflow-x-auto rounded-b-lg bg-[#1a1a1a] font-mono text-xs leading-[1.6]">
      {/* Removed lines */}
      {oldLines.slice(0, oldRevealed).map((line, i) => (
        <div key={`old-${i}`} className={`fe-diff-remove flex ${i === oldRevealed - 1 && revealed < oldLines.length ? "animate-fe-line" : ""}`}>
          <span className="fe-diff-gutter select-none shrink-0 w-7 text-right pr-2 text-red-400/60">−</span>
          <span className="px-3 whitespace-pre flex-1">{line || "\u00a0"}</span>
        </div>
      ))}
      {/* Separator — show once all old lines revealed */}
      {oldRevealed >= oldLines.length && <div className="border-t border-border/20 my-0" />}
      {/* Added lines */}
      {newLines.slice(0, newRevealed).map((line, i) => (
        <div key={`new-${i}`} className={`fe-diff-add flex ${i === newRevealed - 1 && !done ? "animate-fe-line" : ""}`}>
          <span className="fe-diff-gutter select-none shrink-0 w-7 text-right pr-2 text-emerald-400/60">+</span>
          <span className="px-3 whitespace-pre flex-1">{line || "\u00a0"}</span>
        </div>
      ))}
      {!done && (
        <div className="px-3 py-0.5">
          <span className="inline-block h-3.5 w-0.5 animate-pulse bg-accent-teal/70" />
        </div>
      )}
    </div>
  );
}

/* ── Insert view ───────────────────────────────────────────────── */
function InsertView({ newStr, insertLine, animate = true }) {
  const hasInsert = Boolean(newStr);
  const lines = hasInsert ? newStr.replace(/\n$/, "").split("\n") : [];
  const revealed = useLineReveal(lines.length, { enabled: animate && hasInsert, interval: 40 });
  const done = revealed >= lines.length;

  if (!hasInsert) return null;

  return (
    <div className="fe-code-block overflow-x-auto rounded-b-lg bg-[#1a1a1a] font-mono text-xs leading-[1.6]">
      <div className="px-3 py-1 text-[10px] text-text-muted border-b border-border/20">
        Inserted at line {insertLine ?? "?"}
      </div>
      {lines.slice(0, revealed).map((line, i) => (
        <div key={i} className={`fe-diff-add flex ${i === revealed - 1 && !done ? "animate-fe-line" : ""}`}>
          <span className="fe-diff-gutter select-none shrink-0 w-7 text-right pr-2 text-emerald-400/60">+</span>
          <span className="px-3 whitespace-pre flex-1">{line || "\u00a0"}</span>
        </div>
      ))}
      {!done && (
        <div className="px-3 py-0.5">
          <span className="inline-block h-3.5 w-0.5 animate-pulse bg-accent-teal/70" />
        </div>
      )}
    </div>
  );
}


/* ── Main component ────────────────────────────────────────────── */
export default function FileEditBlock({ message, animate = true }) {
  const { command, path, fileText, oldStr, newStr, insertLine, turn } = message;
  const meta = COMMAND_META[command] || COMMAND_META.view;
  const colors = ACCENT_CLASSES[meta.accent] || ACCENT_CLASSES.sky;
  const { Icon } = meta;
  const name = basename(path);
  const lang = langFromPath(path);

  const hasBody = command === "create" || command === "str_replace" || command === "insert";
  const [open, setOpen] = useState(hasBody);

  const copyText = command === "create" ? fileText : (newStr || oldStr || "");

  return (
    <div className={`fe-block rounded-lg border ${colors.glow} bg-charcoal/60 overflow-hidden animate-fe-in`}>
      {/* Header */}
      <button
        onClick={() => hasBody && setOpen(!open)}
        className="flex w-full items-center gap-2.5 px-3 py-2 text-left transition-colors hover:bg-white/2"
      >
        {/* Expand chevron (only for blocks with body) */}
        {hasBody ? (
          open ? <ChevronDown size={13} className="text-text-muted" /> : <ChevronRight size={13} className="text-text-muted" />
        ) : (
          <span className="w-[13px]" />
        )}

        {/* Icon */}
        <Icon size={14} className={`shrink-0 ${colors.badge.split(" ")[1]}`} />

        {/* File path */}
        <span className="flex-1 min-w-0 truncate text-xs">
          <span className="font-medium text-text-primary">{name}</span>
          {path && path !== name && (
            <span className="ml-1.5 text-text-muted">{path}</span>
          )}
        </span>

        {/* Badge */}
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ring-inset ${colors.badge}`}>
          {meta.label}
        </span>

        {/* Language tag */}
        {lang && (
          <span className="shrink-0 rounded bg-surface px-1.5 py-0.5 text-[10px] text-text-muted">
            {lang}
          </span>
        )}

        {/* Turn badge */}
        {turn != null && (
          <span className="shrink-0 text-[10px] text-text-muted">
            T{turn}
          </span>
        )}
      </button>

      {/* Body */}
      {open && hasBody && (
        <div className="border-t border-border/20">
          {/* Copy bar */}
          {copyText && (
            <div className="flex justify-end px-2 py-0.5 bg-[#1a1a1a]">
              <CopyButton text={copyText} />
            </div>
          )}

          {command === "create" && <CodeBlock code={fileText} animate={animate} />}
          {command === "str_replace" && <DiffView oldStr={oldStr} newStr={newStr} animate={animate} />}
          {command === "insert" && <InsertView newStr={newStr} insertLine={insertLine} animate={animate} />}
        </div>
      )}

      {/* Special messages for undo/view */}
      {command === "undo_edit" && (
        <div className="border-t border-border/20 px-3 py-2 text-xs text-text-muted">
          Reverted last edit to <span className="font-medium text-text-secondary">{name}</span>
        </div>
      )}
      {command === "view" && (
        <div className="border-t border-border/20 px-3 py-2 text-xs text-text-muted">
          Read file contents of <span className="font-medium text-text-secondary">{name}</span>
        </div>
      )}
    </div>
  );
}
