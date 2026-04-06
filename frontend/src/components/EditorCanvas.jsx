import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import {
  X,
  FileCode2,
  FilePen,
  FilePlus2,
  Copy,
  Check,
  Code2,
  PanelLeftClose,
  PanelRightClose,
} from "lucide-react";

/* ── helpers ──────────────────────────────────────────────────── */

function basename(path) {
  return path?.split("/").pop() || path || "unknown";
}

function langFromExt(path) {
  const ext = path?.split(".").pop()?.toLowerCase();
  const map = {
    py: "python", js: "javascript", ts: "typescript", jsx: "jsx", tsx: "tsx",
    json: "json", md: "markdown", yml: "yaml", yaml: "yaml", sh: "bash",
    css: "css", html: "html", sql: "sql", rs: "rust", go: "go", java: "java",
    c: "c", cpp: "cpp", h: "c", hpp: "cpp", rb: "ruby", csv: "csv",
  };
  return map[ext] || ext || "";
}

/* ── Animated line reveal ─────────────────────────────────────── */

function useLineReveal(totalLines, { enabled = true, interval = 35 } = {}) {
  const [revealed, setRevealed] = useState(enabled ? 0 : totalLines);
  const timerRef = useRef(null);

  useEffect(() => {
    if (!enabled) { setRevealed(totalLines); return; }
    setRevealed(0);
    let current = 0;
    timerRef.current = setInterval(() => {
      current += 1;
      if (current >= totalLines) {
        clearInterval(timerRef.current);
        setRevealed(totalLines);
      } else {
        setRevealed(current);
      }
    }, interval);
    return () => clearInterval(timerRef.current);
  }, [totalLines, enabled, interval]);

  return revealed;
}

/* ── Copy button ──────────────────────────────────────────────── */

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

/* ── Tab bar ──────────────────────────────────────────────────── */

function TabBar({ openFiles, activeFile, modifiedFiles, onSelectFile, onCloseFile, onToggleCollapse }) {
  if (openFiles.length === 0) return null;

  return (
    <div className="flex items-center border-b border-border/30 bg-charcoal/80">
      <div className="flex flex-1 items-center gap-0 overflow-x-auto scrollbar-hide">
        {openFiles.map((filePath) => {
          const isActive = filePath === activeFile;
          const isModified = modifiedFiles?.has(filePath);
          return (
            <div
              key={filePath}
              className={`
                group relative flex items-center gap-1.5 border-r border-border/20
                px-3 py-1.5 text-[11px] cursor-pointer select-none shrink-0 transition-colors
                ${isActive
                  ? "bg-workspace text-text-primary border-b-2 border-b-accent-teal"
                  : "bg-charcoal text-text-muted hover:bg-surface hover:text-text-secondary"
                }
              `}
              onClick={() => onSelectFile(filePath)}
            >
              <FileCode2 size={12} className={isActive ? "text-accent-teal" : "text-text-muted"} />
              <span className="truncate max-w-[120px]">{basename(filePath)}</span>
              {isModified && (
                <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
              )}
              <button
                onClick={(e) => { e.stopPropagation(); onCloseFile(filePath); }}
                className="ml-1 rounded p-0.5 opacity-0 group-hover:opacity-100 hover:bg-surface-hover transition-opacity"
              >
                <X size={10} />
              </button>
            </div>
          );
        })}
      </div>
      {/* Collapse button */}
      {onToggleCollapse && (
        <button
          onClick={onToggleCollapse}
          className="shrink-0 px-2 py-1.5 text-text-muted hover:text-text-primary transition-colors"
          title="Collapse canvas"
        >
          <PanelRightClose size={14} />
        </button>
      )}
    </div>
  );
}

/* ── Diff overlay (for str_replace edits) ─────────────────────── */

function DiffOverlay({ oldStr, newStr, animate = true }) {
  const oldLines = (oldStr || "").replace(/\n$/, "").split("\n");
  const newLines = (newStr || "").replace(/\n$/, "").split("\n");
  const total = oldLines.length + newLines.length;
  const revealed = useLineReveal(total, { enabled: animate, interval: 60 });
  const done = revealed >= total;
  const oldRevealed = Math.min(revealed, oldLines.length);
  const newRevealed = Math.max(0, revealed - oldLines.length);

  return (
    <div className="my-2 rounded-lg border border-border/30 bg-[#1a1a1a] overflow-hidden">
      <div className="px-3 py-1 text-[10px] text-text-muted border-b border-border/20 flex items-center gap-1.5">
        <FilePen size={11} className="text-amber-400" />
        Replacement
      </div>
      <div className="font-mono text-xs leading-[1.6]">
        {oldLines.slice(0, oldRevealed).map((line, i) => (
          <div key={`o-${i}`} className={`fe-diff-remove flex ${i === oldRevealed - 1 && revealed < oldLines.length ? "animate-fe-line" : ""}`}>
            <span className="fe-diff-gutter select-none shrink-0 w-7 text-right pr-2 text-red-400/60">−</span>
            <span className="px-3 whitespace-pre flex-1">{line || "\u00a0"}</span>
          </div>
        ))}
        {oldRevealed >= oldLines.length && <div className="border-t border-border/20 my-0" />}
        {newLines.slice(0, newRevealed).map((line, i) => (
          <div key={`n-${i}`} className={`fe-diff-add flex ${i === newRevealed - 1 && !done ? "animate-fe-line" : ""}`}>
            <span className="fe-diff-gutter select-none shrink-0 w-7 text-right pr-2 text-emerald-400/60">+</span>
            <span className="px-3 whitespace-pre flex-1">{line || "\u00a0"}</span>
          </div>
        ))}
      </div>
      {!done && (
        <div className="px-3 py-0.5">
          <span className="inline-block h-3.5 w-0.5 animate-pulse bg-accent-teal/70" />
        </div>
      )}
    </div>
  );
}

/* ── Insert overlay ───────────────────────────────────────────── */

function InsertOverlay({ newStr, insertLine, animate = true }) {
  const lines = (newStr || "").replace(/\n$/, "").split("\n");
  const revealed = useLineReveal(lines.length, { enabled: animate, interval: 35 });
  const done = revealed >= lines.length;

  return (
    <div className="my-2 rounded-lg border border-border/30 bg-[#1a1a1a] overflow-hidden">
      <div className="px-3 py-1 text-[10px] text-text-muted border-b border-border/20 flex items-center gap-1.5">
        <FilePlus2 size={11} className="text-emerald-400" />
        Inserted at line {insertLine ?? "?"}
      </div>
      <div className="font-mono text-xs leading-[1.6]">
        {lines.slice(0, revealed).map((line, i) => (
          <div key={i} className={`fe-diff-add flex ${i === revealed - 1 && !done ? "animate-fe-line" : ""}`}>
            <span className="fe-diff-gutter select-none shrink-0 w-7 text-right pr-2 text-emerald-400/60">+</span>
            <span className="px-3 whitespace-pre flex-1">{line || "\u00a0"}</span>
          </div>
        ))}
      </div>
      {!done && (
        <div className="px-3 py-0.5">
          <span className="inline-block h-3.5 w-0.5 animate-pulse bg-accent-teal/70" />
        </div>
      )}
    </div>
  );
}

/* ── File content viewer ──────────────────────────────────────── */

function FileViewer({ content, filePath, editEvents }) {
  const lines = useMemo(
    () => (content || "").replace(/\n$/, "").split("\n"),
    [content],
  );
  const gutterWidth = String(lines.length).length;
  const lang = langFromExt(filePath);

  const fileEdits = useMemo(
    () => (editEvents || []).filter((e) => e.path === filePath),
    [editEvents, filePath],
  );

  const scrollRef = useRef(null);

  useEffect(() => {
    if (fileEdits.length > 0) {
      const el = document.getElementById("canvas-edit-overlay");
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [fileEdits.length]);

  return (
    <div ref={scrollRef} className="flex-1 overflow-auto">
      {lang && (
        <div className="sticky top-0 z-10 flex justify-between items-center px-3 py-1 bg-[#1a1a1a]/95 backdrop-blur-sm border-b border-border/20">
          <span className="text-[10px] text-text-muted">{filePath}</span>
          <div className="flex items-center gap-2">
            <span className="rounded bg-surface px-1.5 py-0.5 text-[10px] text-text-muted">{lang}</span>
            <CopyButton text={content} />
          </div>
        </div>
      )}

      <div className="font-mono text-xs leading-[1.7]">
        <table className="w-full border-collapse">
          <tbody>
            {lines.map((line, i) => (
              <tr key={i} className="hover:bg-white/2">
                <td
                  className="select-none border-r border-border/15 px-2 text-right text-text-muted/30 sticky left-0 bg-[#111]"
                  style={{ width: `${gutterWidth + 2}ch` }}
                >
                  {i + 1}
                </td>
                <td className="px-3 text-text-primary/85 whitespace-pre">{line || "\u00a0"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {fileEdits.length > 0 && (
        <div id="canvas-edit-overlay" className="border-t border-border/20 px-4 py-3">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-accent-teal">
            Recent Edits
          </p>
          {fileEdits.map((edit, i) => {
            if (edit.command === "str_replace") {
              return <DiffOverlay key={i} oldStr={edit.oldStr} newStr={edit.newStr} />;
            }
            if (edit.command === "insert") {
              return <InsertOverlay key={i} newStr={edit.newStr} insertLine={edit.insertLine} />;
            }
            return null;
          })}
        </div>
      )}
    </div>
  );
}

/* ── Create file viewer (animated reveal) ─────────────────────── */

function CreateViewer({ content, filePath }) {
  const lines = useMemo(
    () => (content || "").replace(/\n$/, "").split("\n"),
    [content],
  );
  const gutterWidth = String(lines.length).length;
  const lang = langFromExt(filePath);
  const revealed = useLineReveal(lines.length, { enabled: true, interval: 35 });
  const done = revealed >= lines.length;

  return (
    <div className="flex-1 overflow-auto">
      {lang && (
        <div className="sticky top-0 z-10 flex justify-between items-center px-3 py-1 bg-[#1a1a1a]/95 backdrop-blur-sm border-b border-border/20">
          <div className="flex items-center gap-1.5 text-[10px] text-emerald-400">
            <FilePlus2 size={11} />
            Created — {filePath}
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded bg-surface px-1.5 py-0.5 text-[10px] text-text-muted">{lang}</span>
            <CopyButton text={content} />
          </div>
        </div>
      )}

      <div className="font-mono text-xs leading-[1.7]">
        <table className="w-full border-collapse">
          <tbody>
            {lines.slice(0, revealed).map((line, i) => (
              <tr key={i} className={`${i === revealed - 1 && !done ? "animate-fe-line" : ""}`}>
                <td
                  className="select-none border-r border-border/15 px-2 text-right text-emerald-400/30 sticky left-0 bg-[#111]"
                  style={{ width: `${gutterWidth + 2}ch` }}
                >
                  {i + 1}
                </td>
                <td className="px-3 text-emerald-300/80 whitespace-pre">{line || "\u00a0"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!done && (
        <div className="px-3 py-0.5">
          <span className="inline-block h-3.5 w-0.5 animate-pulse bg-accent-teal/70" />
        </div>
      )}
    </div>
  );
}


/* ── Empty state ──────────────────────────────────────────────── */

function EmptyCanvas() {
  return (
    <div className="flex flex-1 items-center justify-center">
      <div className="text-center">
        <Code2 size={32} className="mx-auto mb-3 text-text-muted/30" />
        <p className="text-sm text-text-muted">Select a file to view</p>
        <p className="mt-1 text-[11px] text-text-muted/60">
          Click a file in the workspace tree, or wait for the agent to make edits
        </p>
      </div>
    </div>
  );
}

/* ── Collapsed strip ──────────────────────────────────────────── */

function CollapsedStrip({ activeFile, openFiles, modifiedFiles, onToggleCollapse }) {
  return (
    <div className="flex w-10 shrink-0 flex-col items-center border-l border-border/20 bg-[#111111]">
      <button
        onClick={onToggleCollapse}
        className="flex h-9 w-full items-center justify-center text-text-muted transition-colors hover:bg-surface-hover hover:text-accent-teal"
        title="Expand canvas"
      >
        <PanelLeftClose size={14} />
      </button>
      <div className="flex-1 flex flex-col items-center gap-1 pt-2">
        {openFiles.slice(0, 6).map((f) => {
          const isActive = f === activeFile;
          const isModified = modifiedFiles?.has(f);
          return (
            <div
              key={f}
              title={basename(f)}
              className={`relative h-6 w-6 rounded flex items-center justify-center transition-colors ${
                isActive
                  ? "bg-accent-teal/15 text-accent-teal"
                  : "text-text-muted hover:bg-surface-hover hover:text-text-secondary"
              }`}
            >
              <FileCode2 size={12} />
              {isModified && (
                <span className="absolute -top-0.5 -right-0.5 h-1.5 w-1.5 rounded-full bg-amber-400" />
              )}
            </div>
          );
        })}
        {openFiles.length > 6 && (
          <span className="text-[9px] text-text-muted">+{openFiles.length - 6}</span>
        )}
      </div>
    </div>
  );
}

/* ── Main EditorCanvas component ──────────────────────────────── */

export default function EditorCanvas({
  openFiles,
  activeFile,
  fileContents,
  modifiedFiles,
  editEvents,
  onSelectFile,
  onCloseFile,
  collapsed = false,
  onToggleCollapse,
}) {
  const content = fileContents?.[activeFile] ?? null;
  const createEvent = useMemo(
    () => (editEvents || []).find((e) => e.path === activeFile && e.command === "create"),
    [editEvents, activeFile],
  );

  if (collapsed) {
    return (
      <CollapsedStrip
        activeFile={activeFile}
        openFiles={openFiles}
        modifiedFiles={modifiedFiles}
        onToggleCollapse={onToggleCollapse}
      />
    );
  }

  return (
    <div className="flex flex-1 flex-col bg-[#111111] min-w-[300px]">
      <TabBar
        openFiles={openFiles}
        activeFile={activeFile}
        modifiedFiles={modifiedFiles}
        onSelectFile={onSelectFile}
        onCloseFile={onCloseFile}
        onToggleCollapse={onToggleCollapse}
      />

      {!activeFile || openFiles.length === 0 ? (
        <EmptyCanvas />
      ) : content === null ? (
        <div className="flex flex-1 items-center justify-center">
          <div className="flex items-center gap-2 text-sm text-text-muted">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-accent-teal/30 border-t-accent-teal" />
            Loading…
          </div>
        </div>
      ) : createEvent ? (
        <CreateViewer content={createEvent.fileText} filePath={activeFile} />
      ) : (
        <FileViewer content={content} filePath={activeFile} editEvents={editEvents} />
      )}
    </div>
  );
}
