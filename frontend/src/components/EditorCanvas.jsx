import { useState, useEffect, useRef, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  X,
  FileCode2,
  FilePen,
  FilePlus2,
  Copy,
  Check,
  Code2,
  Eye,
  FileText,
  PanelLeftClose,
  PanelRightClose,
} from "lucide-react";
import { workspaceRawUrl } from "../services/api";

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
    pdf: "pdf",
  };
  return map[ext] || ext || "";
}

const MARKDOWN_EXTS = new Set(["md", "markdown", "mdown", "mkd"]);
const IMAGE_EXTS = new Set(["png", "jpg", "jpeg", "gif", "bmp", "webp", "svg", "ico"]);
const TEXT_EXTS = new Set([
  "txt", "log", "csv", "tsv",
  "py", "js", "jsx", "ts", "tsx", "mjs", "cjs",
  "json", "yml", "yaml", "toml", "ini", "cfg", "env",
  "sh", "bash", "zsh", "fish",
  "css", "scss", "less", "html", "htm", "xml", "svg",
  "sql", "rs", "go", "java", "kt", "swift",
  "c", "cc", "cpp", "h", "hpp", "rb", "lua", "r", "php", "pl",
  "dockerfile", "makefile", "gitignore",
]);

function getExt(path) {
  if (!path) return "";
  const name = path.split("/").pop() || "";
  const lower = name.toLowerCase();
  // Files like "Dockerfile" / "Makefile" with no extension: treat the name as the ext.
  if (!lower.includes(".")) return lower;
  return lower.split(".").pop() || "";
}

function fileKind(path) {
  const ext = getExt(path);
  if (!ext) return "text";
  if (ext === "pdf") return "pdf";
  if (MARKDOWN_EXTS.has(ext)) return "markdown";
  if (IMAGE_EXTS.has(ext)) return "image";
  return "text";
}

/* ── Animated line reveal ─────────────────────────────────────── */

function useLineReveal(totalLines, { enabled = true, interval = 35 } = {}) {
  const [revealed, setRevealed] = useState(enabled ? 0 : totalLines);
  const timerRef = useRef(null);

  useEffect(() => {
    if (!enabled) return;
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

function FileViewer({ content, filePath, editEvents, hideHeader = false }) {
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
      {!hideHeader && lang && (
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


/* ── Markdown viewer (Preview / Source toggle) ────────────────── */

const MARKDOWN_COMPONENTS = {
  h1: ({ children }) => <h1 className="mb-3 mt-4 text-xl font-semibold text-text-primary">{children}</h1>,
  h2: ({ children }) => <h2 className="mb-2 mt-4 text-lg font-semibold text-text-primary">{children}</h2>,
  h3: ({ children }) => <h3 className="mb-2 mt-3 text-base font-semibold text-text-primary">{children}</h3>,
  h4: ({ children }) => <h4 className="mb-2 mt-3 text-sm font-semibold text-text-primary">{children}</h4>,
  p: ({ children }) => <p className="mb-3 leading-relaxed last:mb-0">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold text-accent-light">{children}</strong>,
  em: ({ children }) => <em className="italic text-text-secondary">{children}</em>,
  ul: ({ children }) => <ul className="mb-3 list-disc pl-6 last:mb-0">{children}</ul>,
  ol: ({ children }) => <ol className="mb-3 list-decimal pl-6 last:mb-0">{children}</ol>,
  li: ({ children }) => <li className="mb-1">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="my-3 border-l-2 border-accent-teal/50 pl-3 italic text-text-secondary">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-4 border-border/30" />,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-accent-teal underline hover:text-accent-light"
    >
      {children}
    </a>
  ),
  code: ({ inline, children }) =>
    inline ? (
      <code className="rounded bg-charcoal px-1.5 py-0.5 text-[12px] font-mono text-accent-light">
        {children}
      </code>
    ) : (
      <code className="font-mono text-[12px]">{children}</code>
    ),
  pre: ({ children }) => (
    <pre className="my-3 overflow-x-auto rounded-md border border-border/30 bg-[#0d0d0d] p-3 text-[12px] leading-[1.6] text-text-primary">
      {children}
    </pre>
  ),
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto">
      <table className="w-full border-collapse text-[12px]">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border border-border/30 bg-surface px-2 py-1 text-left font-semibold text-text-primary">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border border-border/30 px-2 py-1 text-text-secondary">{children}</td>
  ),
};

function MarkdownViewer({ content, filePath }) {
  const [view, setView] = useState("preview"); // 'preview' | 'source'

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border/20 bg-[#1a1a1a]/95 px-3 py-1 backdrop-blur-sm">
        <span className="flex items-center gap-1.5 text-[10px] text-text-muted">
          <FileText size={11} className="text-accent-teal" />
          {filePath}
        </span>
        <div className="flex items-center gap-2">
          <div className="flex overflow-hidden rounded border border-border/30">
            <button
              onClick={() => setView("preview")}
              className={`flex items-center gap-1 px-1.5 py-0.5 text-[10px] transition-colors ${
                view === "preview"
                  ? "bg-accent-teal/15 text-accent-teal"
                  : "text-text-muted hover:bg-surface-hover hover:text-text-secondary"
              }`}
              title="Rendered Markdown"
            >
              <Eye size={10} />
              Preview
            </button>
            <button
              onClick={() => setView("source")}
              className={`flex items-center gap-1 px-1.5 py-0.5 text-[10px] transition-colors ${
                view === "source"
                  ? "bg-accent-teal/15 text-accent-teal"
                  : "text-text-muted hover:bg-surface-hover hover:text-text-secondary"
              }`}
              title="Raw source"
            >
              <Code2 size={10} />
              Source
            </button>
          </div>
          <CopyButton text={content} />
        </div>
      </div>

      {view === "preview" ? (
        <div className="flex-1 overflow-auto px-6 py-4">
          <div className="mx-auto max-w-3xl text-sm text-text-primary">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={MARKDOWN_COMPONENTS}
            >
              {content || ""}
            </ReactMarkdown>
          </div>
        </div>
      ) : (
        <FileViewer content={content} filePath={filePath} editEvents={[]} hideHeader />
      )}
    </div>
  );
}

/* ── PDF viewer (browser-native via iframe) ───────────────────── */

function PdfViewer({ filePath, mountDir }) {
  if (!mountDir) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <p className="text-sm text-text-muted">PDF preview requires a workspace mount.</p>
      </div>
    );
  }
  const url = workspaceRawUrl(mountDir, filePath);
  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border/20 bg-[#1a1a1a]/95 px-3 py-1 backdrop-blur-sm">
        <span className="flex items-center gap-1.5 text-[10px] text-text-muted">
          <FileText size={11} className="text-accent-teal" />
          {filePath}
        </span>
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[10px] text-accent-teal underline hover:text-accent-light"
        >
          Open
        </a>
      </div>
      <iframe
        key={url}
        src={url}
        title={filePath}
        className="flex-1 w-full border-0 bg-white"
      />
    </div>
  );
}

/* ── Image viewer ─────────────────────────────────────────────── */

function ImageViewer({ filePath, mountDir }) {
  if (!mountDir) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <p className="text-sm text-text-muted">Image preview requires a workspace mount.</p>
      </div>
    );
  }
  const url = workspaceRawUrl(mountDir, filePath);
  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-border/20 bg-[#1a1a1a]/95 px-3 py-1 backdrop-blur-sm">
        <span className="text-[10px] text-text-muted">{filePath}</span>
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[10px] text-accent-teal underline hover:text-accent-light"
        >
          Open
        </a>
      </div>
      <div className="flex flex-1 items-center justify-center overflow-auto bg-[#0a0a0a] p-4">
        <img src={url} alt={filePath} className="max-h-full max-w-full object-contain" />
      </div>
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
  mountDir,
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
  const kind = useMemo(() => fileKind(activeFile), [activeFile]);

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

  // Binary previews don't depend on `content` being loaded.
  const isBinaryPreview = kind === "pdf" || kind === "image";

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
      ) : !isBinaryPreview && content === null ? (
        <div className="flex flex-1 items-center justify-center">
          <div className="flex items-center gap-2 text-sm text-text-muted">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-accent-teal/30 border-t-accent-teal" />
            Loading…
          </div>
        </div>
      ) : kind === "pdf" ? (
        <PdfViewer filePath={activeFile} mountDir={mountDir} />
      ) : kind === "image" ? (
        <ImageViewer filePath={activeFile} mountDir={mountDir} />
      ) : kind === "markdown" ? (
        <MarkdownViewer content={content} filePath={activeFile} />
      ) : createEvent && createEvent.fileText ? (
        <CreateViewer content={createEvent.fileText} filePath={activeFile} />
      ) : (
        <FileViewer content={content} filePath={activeFile} editEvents={editEvents} />
      )}
    </div>
  );
}
