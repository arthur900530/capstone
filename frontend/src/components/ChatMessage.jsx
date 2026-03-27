import { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import {
  Wrench,
  Brain,
  ShieldCheck,
  RefreshCw,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  Loader2,
  CheckCircle2,
} from "lucide-react";


function useTypingEffect(text, { speed = 18, enabled = true } = {}) {
  const [displayed, setDisplayed] = useState(() => (enabled ? "" : text));
  const [done, setDone] = useState(() => !enabled);

  useEffect(() => {
    if (!enabled) {
      setDisplayed(text);
      setDone(true);
      return;
    }

    setDisplayed("");
    setDone(false);

    const words = text.split(/(\s+)/);
    let current = "";
    let index = 0;

    const id = setInterval(() => {
      if (index >= words.length) {
        clearInterval(id);
        setDone(true);
        return;
      }
      current += words[index];
      index++;
      setDisplayed(current);
    }, speed);

    return () => clearInterval(id);
  }, [text, speed, enabled]);

  return { displayed, done };
}

function ConfidenceBadge({ score }) {
  const pct = Math.round(score * 100);
  const color =
    pct >= 70
      ? "text-emerald-400 bg-emerald-400/10"
      : pct >= 40
        ? "text-yellow-400 bg-yellow-400/10"
        : "text-red-400 bg-red-400/10";

  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${color}`}>
      {pct}% confident
    </span>
  );
}

function CollapsibleBlock({ icon: Icon, title, badge, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="rounded-lg border border-border/50 bg-charcoal/40">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-text-secondary hover:text-text-primary"
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <Icon size={14} className="text-accent-teal" />
        <span className="font-medium">{title}</span>
        {badge}
      </button>
      {open && (
        <div className="border-t border-border/30 px-3 py-2 text-xs leading-relaxed text-text-secondary">
          {children}
        </div>
      )}
    </div>
  );
}

function AnswerBlock({ message, animate }) {
  const { displayed, done: typingDone } = useTypingEffect(message.content, { enabled: animate });

  return (
    <div className="max-w-[90%] rounded-2xl rounded-bl-sm bg-surface px-4 py-3">
      <p className="mb-2 text-[10px] font-medium uppercase tracking-wider text-accent-teal">
        Response
      </p>
      <div className="prose-dark text-sm leading-relaxed text-text-primary">
        <ReactMarkdown
          components={{
            p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
            strong: ({ children }) => <strong className="font-semibold text-accent-light">{children}</strong>,
            ul: ({ children }) => <ul className="mb-2 list-disc pl-5 last:mb-0">{children}</ul>,
            ol: ({ children }) => <ol className="mb-2 list-decimal pl-5 last:mb-0">{children}</ol>,
            li: ({ children }) => <li className="mb-1">{children}</li>,
            a: ({ href, children }) => (
              <a href={href} target="_blank" rel="noopener noreferrer" className="text-accent-teal underline hover:text-accent-light">
                {children}
              </a>
            ),
            code: ({ children }) => (
              <code className="rounded bg-charcoal px-1.5 py-0.5 text-xs font-mono text-accent-light">{children}</code>
            ),
          }}
        >
          {displayed}
        </ReactMarkdown>
        {!typingDone && (
          <span className="inline-block h-4 w-0.5 animate-pulse bg-accent-teal/70" />
        )}
      </div>
    </div>
  );
}

function TypedBubble({ text, animate }) {
  const { displayed, done } = useTypingEffect(text, { enabled: animate });
  return (
    <div className="max-w-[80%] rounded-2xl rounded-bl-sm bg-surface px-4 py-3 text-sm leading-relaxed text-text-primary">
      {displayed}
      {!done && (
        <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-accent-teal/70" />
      )}
    </div>
  );
}


export default function ChatMessage({ message, animate = true }) {
  const { role, type, content } = message;

  if (role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-accent-deep/30 px-4 py-3 text-sm text-text-primary">
          {content}
        </div>
      </div>
    );
  }

  if (type === "status") {
    const done = message.done;
    return (
      <div className="flex items-center gap-2 text-xs text-text-muted">
        {done ? (
          <CheckCircle2 size={12} className="text-emerald-400" />
        ) : (
          <Loader2 size={12} className="animate-spin text-accent-teal" />
        )}
        {content}
      </div>
    );
  }

  if (type === "trial_start") {
    return (
      <div className="flex items-center gap-2 py-1">
        <div className="h-px flex-1 bg-border/50" />
        <span className="text-xs font-medium text-accent-teal">
          Trial {message.trial}/{message.maxTrials}
        </span>
        <div className="h-px flex-1 bg-border/50" />
      </div>
    );
  }

  if (type === "tool_call") {
    const TOOL_LABELS = {
      web_search: "Web Search",
      edgar_search: "SEC Filing Search",
      parse_html: "Reading Page",
      retrieve_info: "Analyzing Documents",
      retrieve_information: "Analyzing Documents",
      submit_result: "Submitting Answer",
      submit_final_result: "Submitting Answer",
      finish: "Task Complete",
      FinishTool: "Task Complete",
      terminal: "Terminal",
      file_editor: "File Editor",
      task_tracker: "Task Tracker",
      delegate: "Delegate",
    };
    const label = TOOL_LABELS[message.tool] || message.tool;

    return (
      <div className="flex items-start gap-2 text-xs">
        <Wrench size={13} className="mt-0.5 shrink-0 text-accent-teal/70" />
        <div>
          <span className="font-medium text-text-primary">
            Turn {message.turn} &middot; {label}
          </span>
          {message.detail && (
            <p className="mt-0.5 text-text-muted">{message.detail}</p>
          )}
        </div>
      </div>
    );
  }

  if (type === "tool_result") {
    return (
      <div className="ml-5 rounded border-l-2 border-accent-teal/20 pl-3 text-xs text-text-muted">
        {content.length > 300 ? content.slice(0, 300) + "..." : content}
      </div>
    );
  }

  if (type === "reasoning") {
    return (
      <CollapsibleBlock icon={Brain} title="Agent Reasoning">
        <p className="whitespace-pre-wrap">{content}</p>
      </CollapsibleBlock>
    );
  }

  if (type === "self_eval") {
    return (
      <CollapsibleBlock
        icon={ShieldCheck}
        title="Self-Evaluation"
        badge={<ConfidenceBadge score={message.confidenceScore} />}
      >
        <p className="whitespace-pre-wrap">{content}</p>
      </CollapsibleBlock>
    );
  }

  if (type === "reflection") {
    return (
      <CollapsibleBlock icon={RefreshCw} title="Reflection" defaultOpen>
        <p className="whitespace-pre-wrap">{content}</p>
      </CollapsibleBlock>
    );
  }

  if (type === "error") {
    return (
      <div className="flex items-start gap-2 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">
        <AlertCircle size={14} className="mt-0.5 shrink-0" />
        <span>{content}</span>
      </div>
    );
  }

  if (type === "answer") {
    return <AnswerBlock message={message} animate={animate} />;
  }

  if (type === "chat_response") {
    return <TypedBubble text={content} animate={animate} />;
  }

  return (
    <div className="text-sm text-text-secondary">
      {content}
    </div>
  );
}
