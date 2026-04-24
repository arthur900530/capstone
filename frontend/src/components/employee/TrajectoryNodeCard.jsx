import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Brain,
  ChevronDown,
  ChevronRight,
  CircleCheckBig,
  CircleX,
  FileCode2,
  Globe,
  MessageSquareText,
  RefreshCw,
  Terminal,
  Wrench,
} from "lucide-react";

function formatDuration(time) {
  if (!time?.before || !time?.after) return null;
  const start = Date.parse(time.before);
  const end = Date.parse(time.after);
  if (Number.isNaN(start) || Number.isNaN(end)) return null;
  const ms = Math.max(0, end - start);
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function categoryMeta(category) {
  switch (category) {
    case "reasoning":
      return { icon: Brain, label: "Reasoning", tone: "text-sky-300 bg-sky-400/10" };
    case "file":
      return { icon: FileCode2, label: "File", tone: "text-amber-300 bg-amber-400/10" };
    case "terminal":
      return { icon: Terminal, label: "Terminal", tone: "text-emerald-300 bg-emerald-400/10" };
    case "browse":
      return { icon: Globe, label: "Browse", tone: "text-cyan-300 bg-cyan-400/10" };
    case "reflection":
      return { icon: RefreshCw, label: "Reflection", tone: "text-purple-300 bg-purple-500/10" };
    case "answer":
    case "chat":
      return { icon: MessageSquareText, label: "Answer", tone: "text-teal-300 bg-teal-400/10" };
    default:
      return { icon: Wrench, label: "Action", tone: "text-text-secondary bg-surface" };
  }
}

function statusMeta(status) {
  switch (status) {
    case "success":
      return {
        icon: CircleCheckBig,
        label: "Success",
        tone: "text-emerald-300 bg-emerald-400/10",
      };
    case "failure":
      return {
        icon: CircleX,
        label: "Failure",
        tone: "text-rose-300 bg-rose-400/10",
      };
    default:
      return null;
  }
}

function CodeBlock({ children }) {
  if (!children) return null;
  return (
    <pre className="overflow-x-auto rounded-lg border border-border/40 bg-workspace/80 p-3 text-[11px] leading-relaxed text-text-secondary">
      <code>{children}</code>
    </pre>
  );
}

function JsonBlock({ value }) {
  if (!value || (typeof value === "object" && Object.keys(value).length === 0)) {
    return null;
  }
  return <CodeBlock>{JSON.stringify(value, null, 2)}</CodeBlock>;
}

function FileEditDetails({ extra }) {
  if (!extra) return null;
  if (extra.old_str || extra.new_str) {
    return (
      <div className="space-y-2">
        {extra.old_str ? (
          <div>
            <p className="mb-1 text-[11px] font-medium uppercase tracking-wider text-rose-300">
              Previous
            </p>
            <CodeBlock>{extra.old_str}</CodeBlock>
          </div>
        ) : null}
        {extra.new_str ? (
          <div>
            <p className="mb-1 text-[11px] font-medium uppercase tracking-wider text-emerald-300">
              Updated
            </p>
            <CodeBlock>{extra.new_str}</CodeBlock>
          </div>
        ) : null}
      </div>
    );
  }

  if (extra.file_text) {
    return (
      <div>
        <p className="mb-1 text-[11px] font-medium uppercase tracking-wider text-text-muted">
          File snapshot
        </p>
        <CodeBlock>{extra.file_text}</CodeBlock>
      </div>
    );
  }

  return null;
}

function MarkdownAnswer({ text }) {
  if (!text) return null;
  return (
    <div className="prose-dark text-sm leading-relaxed text-text-primary">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
          ul: ({ children }) => <ul className="mb-2 list-disc pl-5 last:mb-0">{children}</ul>,
          ol: ({ children }) => <ol className="mb-2 list-decimal pl-5 last:mb-0">{children}</ol>,
          li: ({ children }) => <li className="mb-1">{children}</li>,
          code: ({ children }) => (
            <code className="rounded bg-charcoal px-1.5 py-0.5 text-xs text-accent-light">
              {children}
            </code>
          ),
          pre: ({ children }) => <div className="my-3">{children}</div>,
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="text-accent-teal underline"
            >
              {children}
            </a>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

export default function TrajectoryNodeCard({ node }) {
  const extra = node?.state?.extra || {};
  const category = extra.category || "other";
  const categoryInfo = categoryMeta(category);
  const statusInfo = statusMeta(node?.status);
  const duration = useMemo(() => formatDuration(node?.time), [node?.time]);
  const [open, setOpen] = useState(category === "reflection" || category === "answer");

  if (!node) return null;

  const CategoryIcon = categoryInfo.icon;
  const StatusIcon = statusInfo?.icon;
  const toolOutput = node.state?.tool_output;
  const trialIndex = extra.trial_index;
  const isAnswer = extra.event_type === "answer" || extra.event_type === "chat_response";
  const isFileEdit = extra.event_type === "file_edit";

  return (
    <div className="rounded-xl border border-border/50 bg-[#2a2c31] shadow-[0_2px_12px_rgba(0,0,0,0.18)]">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-start justify-between gap-3 px-4 py-3 text-left"
      >
        <div className="min-w-0 flex-1">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${categoryInfo.tone}`}>
              <CategoryIcon size={11} />
              {categoryInfo.label}
            </span>
            {typeof trialIndex === "number" ? (
              <span className="rounded-full bg-surface px-2 py-0.5 text-[10px] text-text-muted">
                Trial {trialIndex}
              </span>
            ) : null}
            {statusInfo ? (
              <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${statusInfo.tone}`}>
                <StatusIcon size={11} />
                {statusInfo.label}
              </span>
            ) : null}
            {duration ? (
              <span className="rounded-full bg-surface px-2 py-0.5 text-[10px] text-text-muted">
                {duration}
              </span>
            ) : null}
          </div>
          {node.goal ? (
            <p className="mb-1 text-xs text-accent-light whitespace-pre-wrap">{node.goal}</p>
          ) : null}
          <p className="text-sm font-medium text-text-primary break-words">{node.action}</p>
        </div>
        <div className="pt-0.5 text-text-muted">
          {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </div>
      </button>

      {open ? (
        <div className="space-y-3 border-t border-border/40 px-4 py-3 text-xs text-text-secondary">
          {extra.event_type === "tool_call" ? (
            <>
              {extra.detail ? (
                <div>
                  <p className="mb-1 text-[11px] font-medium uppercase tracking-wider text-text-muted">
                    Detail
                  </p>
                  <p className="whitespace-pre-wrap">{extra.detail}</p>
                </div>
              ) : null}
              <JsonBlock value={extra.args} />
            </>
          ) : null}

          {isFileEdit ? <FileEditDetails extra={extra} /> : null}

          {toolOutput ? (
            <div>
              <p className="mb-1 text-[11px] font-medium uppercase tracking-wider text-text-muted">
                {isAnswer ? "Response" : category === "reflection" ? "Reflection" : "Output"}
              </p>
              {isAnswer ? <MarkdownAnswer text={toolOutput} /> : <CodeBlock>{toolOutput}</CodeBlock>}
            </div>
          ) : null}

          {node.status_reason ? (
            <div>
              <p className="mb-1 text-[11px] font-medium uppercase tracking-wider text-text-muted">
                Evaluation
              </p>
              <p className="whitespace-pre-wrap">{node.status_reason}</p>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
