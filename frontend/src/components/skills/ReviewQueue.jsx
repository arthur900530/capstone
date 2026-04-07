import { useState, useEffect } from "react";
import {
  Loader2, AlertCircle, ClipboardCheck, CheckCircle, XCircle,
  ChevronDown, ChevronRight, MessageSquare, X, Eye,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import { fetchSubmissions, reviewSubmission, deleteSubmission, fetchSkillById } from "../../services/api";

/* ── Compact markdown renderer ──────────────────────────────────────────── */

const mdComponents = {
  h1: ({ children }) => <h1 className="mb-2 mt-1 text-sm font-semibold text-text-primary">{children}</h1>,
  h2: ({ children }) => <h2 className="mb-1.5 mt-3 border-b border-border/20 pb-1 text-xs font-semibold text-text-primary">{children}</h2>,
  h3: ({ children }) => <h3 className="mb-1 mt-2 text-xs font-semibold text-text-primary">{children}</h3>,
  p: ({ children }) => <p className="mb-2 text-xs leading-relaxed text-text-secondary">{children}</p>,
  ul: ({ children }) => <ul className="mb-2 ml-3 list-disc space-y-0.5 text-xs text-text-secondary">{children}</ul>,
  ol: ({ children }) => <ol className="mb-2 ml-3 list-decimal space-y-0.5 text-xs text-text-secondary">{children}</ol>,
  li: ({ children }) => <li className="text-xs text-text-secondary">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-text-primary">{children}</strong>,
  code: ({ className, children, ...props }) => {
    if (className?.includes("language-")) {
      return (
        <pre className="my-2 overflow-x-auto rounded-lg border border-border/20 bg-charcoal/80 px-3 py-2">
          <code className="text-[11px] font-mono leading-relaxed text-accent-light/90">{children}</code>
        </pre>
      );
    }
    return <code className="rounded bg-surface px-1 py-0.5 text-[11px] font-mono text-accent-teal" {...props}>{children}</code>;
  },
  pre: ({ children }) => <>{children}</>,
  hr: () => <hr className="my-3 border-border/20" />,
};

/* ── Side-by-side comparison modal ──────────────────────────────────────── */

function CompareModal({ submission, existingSkill, similarity, onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 flex max-h-[85vh] w-full max-w-6xl animate-scale-in flex-col rounded-2xl border border-border/30 bg-workspace shadow-2xl shadow-black/40">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border/30 px-5 py-3">
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium text-text-primary">Side-by-Side Comparison</span>
            {similarity && (
              <span className="rounded-full bg-yellow-500/10 px-2.5 py-0.5 text-[11px] font-medium text-yellow-400">
                {(similarity.overall_overlap_score * 100).toFixed(0)}% overlap
              </span>
            )}
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-text-muted transition-colors hover:bg-surface hover:text-text-secondary"
          >
            <X size={16} />
          </button>
        </div>

        {/* Two-column body */}
        <div className="flex flex-1 overflow-hidden">
          {/* Left: Submitted skill */}
          <div className="flex flex-1 flex-col border-r border-border/20">
            <div className="border-b border-border/20 px-5 py-2.5">
              <div className="flex items-center gap-2">
                <span className="rounded-full bg-purple-500/10 px-2 py-0.5 text-[10px] font-medium text-purple-400">
                  submitted
                </span>
                <span className="text-sm font-medium text-text-primary">{submission.proposed_name}</span>
              </div>
              {submission.proposed_description && (
                <p className="mt-1 text-xs text-text-muted">{submission.proposed_description}</p>
              )}
            </div>
            <div className="flex-1 overflow-y-auto px-5 py-4">
              {submission.proposed_skill_md ? (
                <ReactMarkdown components={mdComponents}>{submission.proposed_skill_md}</ReactMarkdown>
              ) : (
                <p className="text-xs text-text-muted italic">No definition provided</p>
              )}
            </div>
          </div>

          {/* Right: Existing skill */}
          <div className="flex flex-1 flex-col">
            <div className="border-b border-border/20 px-5 py-2.5">
              <div className="flex items-center gap-2">
                <span className="rounded-full bg-blue-500/10 px-2 py-0.5 text-[10px] font-medium text-blue-400">
                  existing
                </span>
                <span className="text-sm font-medium text-text-primary">{existingSkill.name}</span>
              </div>
              {existingSkill.description && (
                <p className="mt-1 text-xs text-text-muted">{existingSkill.description}</p>
              )}
            </div>
            <div className="flex-1 overflow-y-auto px-5 py-4">
              {existingSkill.definition ? (
                <ReactMarkdown components={mdComponents}>{existingSkill.definition}</ReactMarkdown>
              ) : (
                <p className="text-xs text-text-muted italic">No definition available</p>
              )}
            </div>
          </div>
        </div>

        {/* Similarity breakdown footer */}
        {similarity && (
          <div className="flex items-center gap-4 border-t border-border/20 px-5 py-2.5 text-[11px] text-text-muted">
            <span>Name: <span className="text-text-secondary">{(similarity.name_similarity * 100).toFixed(0)}%</span></span>
            <span>Content: <span className="text-text-secondary">{(similarity.content_similarity * 100).toFixed(0)}%</span></span>
            <span>Overall: <span className="font-medium text-text-primary">{(similarity.overall_overlap_score * 100).toFixed(0)}%</span></span>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Review item ────────────────────────────────────────────────────────── */

function ReviewItem({ sub, onDecision, onDelete, onCompare }) {
  const [expanded, setExpanded] = useState(false);
  const [reason, setReason] = useState("");
  const [acting, setActing] = useState(false);

  const isActionable = sub.status === "uploaded" || sub.status === "duplicate_check_complete";
  const isResolved = sub.status === "accepted" || sub.status === "discarded";
  const hasSimilarity = sub.similarity_results && sub.similarity_results.length > 0;

  const handleDecision = async (decision) => {
    setActing(true);
    try { await onDecision(sub.id, decision, reason); } finally { setActing(false); }
  };

  const handleDelete = async () => {
    setActing(true);
    try { await onDelete(sub.id); } finally { setActing(false); }
  };

  return (
    <div className={`rounded-xl border border-border/40 bg-surface p-4 ${isResolved ? "opacity-60" : ""}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h4 className="text-sm font-medium text-text-primary">{sub.proposed_name}</h4>
          {sub.proposed_description && (
            <p className="mt-1 text-xs text-text-secondary">{sub.proposed_description}</p>
          )}
          <div className="mt-2 flex items-center gap-2">
            <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
              sub.status === "accepted" ? "bg-green-500/10 text-green-400"
              : sub.status === "discarded" ? "bg-red-500/10 text-red-400"
              : sub.status === "duplicate_check_complete" ? "bg-yellow-500/10 text-yellow-400"
              : "bg-charcoal text-text-muted"
            }`}>
              {sub.status.replace(/_/g, " ")}
            </span>
            <span className="text-[10px] text-text-muted">
              {new Date(sub.created_at).toLocaleString()}
            </span>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-1.5">
          {isActionable && (
            <>
              <button
                onClick={() => handleDecision("accept")}
                disabled={acting}
                className="flex items-center gap-1 rounded-lg bg-green-500/10 px-2.5 py-1.5 text-xs font-medium text-green-400 transition-colors hover:bg-green-500/20 disabled:opacity-50"
              >
                {acting ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle size={13} />}
                Accept
              </button>
              <button
                onClick={() => handleDecision("discard")}
                disabled={acting}
                className="flex items-center gap-1 rounded-lg bg-red-500/10 px-2.5 py-1.5 text-xs font-medium text-red-400 transition-colors hover:bg-red-500/20 disabled:opacity-50"
              >
                <XCircle size={13} />
                Reject
              </button>
            </>
          )}
          <button
            onClick={handleDelete}
            disabled={acting}
            className="rounded-lg p-1.5 text-text-muted transition-colors hover:bg-red-500/10 hover:text-red-400 disabled:opacity-50"
            title="Remove from queue"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Reason input */}
      {isActionable && (
        <div className="mt-3 flex items-start gap-2">
          <MessageSquare size={13} className="mt-1.5 shrink-0 text-text-muted" />
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Decision reason (optional)..."
            rows={1}
            className="flex-1 resize-none rounded-lg border border-border/30 bg-charcoal/50 px-3 py-1.5 text-xs text-text-primary placeholder:text-text-muted outline-none transition-colors focus:border-accent-teal/40"
          />
        </div>
      )}

      {/* Similarity results — clickable to compare */}
      {hasSimilarity && (
        <div className="mt-3">
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1.5 text-[11px] font-medium text-text-muted"
          >
            {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            {sub.similarity_results.length} similar skill{sub.similarity_results.length !== 1 ? "s" : ""} found
          </button>
          {expanded && (
            <div className="mt-2 space-y-1.5">
              {sub.similarity_results.map((sr, i) => (
                <button
                  key={i}
                  onClick={() => onCompare(sub, sr)}
                  className="flex w-full items-center gap-3 rounded-lg border border-border/20 bg-charcoal/40 px-3 py-2 text-left transition-colors hover:border-accent-teal/30 hover:bg-charcoal/60"
                >
                  <Eye size={13} className="shrink-0 text-accent-teal" />
                  <span className="min-w-0 flex-1 truncate text-xs font-medium text-text-primary">
                    {sr.existing_skill_slug || "Unknown"}
                  </span>
                  <span className="shrink-0 rounded-full bg-surface px-1.5 py-0.5 text-[10px] font-medium text-text-secondary">
                    {(sr.overall_overlap_score * 100).toFixed(0)}% overlap
                  </span>
                  <span className="shrink-0 text-[10px] text-accent-teal">Compare</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Preview definition */}
      {sub.proposed_skill_md && (
        <div className="mt-3">
          <button
            onClick={() => setExpanded((v) => !v)}
            className="text-[11px] text-accent-teal hover:underline"
          >
            {expanded ? "Hide definition" : "Preview definition"}
          </button>
          {expanded && (
            <pre className="mt-2 max-h-40 overflow-auto rounded-lg border border-border/20 bg-charcoal/50 p-3 text-xs leading-relaxed text-text-secondary">
              {sub.proposed_skill_md.slice(0, 1000)}
              {sub.proposed_skill_md.length > 1000 && "..."}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Main queue ─────────────────────────────────────────────────────────── */

export default function ReviewQueue() {
  const [submissions, setSubmissions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [comparing, setComparing] = useState(null); // { submission, existingSkill, similarity }

  const load = async () => {
    try {
      const data = await fetchSubmissions();
      setSubmissions(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleDecision = async (id, decision, reason) => {
    await reviewSubmission(id, { decision, reason });
    await load();
  };

  const handleDelete = async (id) => {
    await deleteSubmission(id);
    await load();
  };

  const handleCompare = async (sub, similarity) => {
    try {
      const existingSkill = await fetchSkillById(similarity.existing_skill_slug);
      setComparing({ submission: sub, existingSkill, similarity });
    } catch {
      setError(`Could not load skill "${similarity.existing_skill_slug}"`);
    }
  };

  const handleClearResolved = async () => {
    const resolved = submissions.filter(s => s.status === "accepted" || s.status === "discarded");
    for (const sub of resolved) {
      await deleteSubmission(sub.id);
    }
    await load();
  };

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <Loader2 size={24} className="animate-spin text-accent-teal" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-1 items-center justify-center p-8">
        <div className="flex items-center gap-2 text-sm text-red-400">
          <AlertCircle size={16} />
          {error}
        </div>
      </div>
    );
  }

  if (submissions.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8">
        <ClipboardCheck size={32} className="text-text-muted" />
        <p className="text-sm text-text-muted">No submissions yet</p>
        <p className="text-xs text-text-muted">Skills submitted to the marketplace will appear here for review.</p>
      </div>
    );
  }

  const resolvedCount = submissions.filter(s => s.status === "accepted" || s.status === "discarded").length;

  return (
    <>
      <div className="flex-1 overflow-y-auto p-4">
        <div className="mx-auto max-w-3xl space-y-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs text-text-muted">
              {submissions.length} submission{submissions.length !== 1 ? "s" : ""}
            </span>
            {resolvedCount > 0 && (
              <button
                onClick={handleClearResolved}
                className="flex items-center gap-1 rounded-lg px-2.5 py-1 text-[11px] text-text-muted transition-colors hover:bg-surface hover:text-text-secondary"
              >
                <X size={11} />
                Clear {resolvedCount} resolved
              </button>
            )}
          </div>
          {submissions.map((sub) => (
            <ReviewItem
              key={sub.id}
              sub={sub}
              onDecision={handleDecision}
              onDelete={handleDelete}
              onCompare={handleCompare}
            />
          ))}
        </div>
      </div>

      {/* Comparison modal */}
      {comparing && (
        <CompareModal
          submission={comparing.submission}
          existingSkill={comparing.existingSkill}
          similarity={comparing.similarity}
          onClose={() => setComparing(null)}
        />
      )}
    </>
  );
}
