import { useState, useEffect } from "react";
import {
  Loader2, AlertCircle, ClipboardCheck, CheckCircle, XCircle,
  GitMerge, ChevronDown, ChevronRight, MessageSquare,
} from "lucide-react";
import { fetchSubmissions, reviewSubmission } from "../../services/api";

function ReviewItem({ sub, onDecision }) {
  const [expanded, setExpanded] = useState(false);
  const [reason, setReason] = useState("");
  const [acting, setActing] = useState(false);

  const isActionable = sub.status === "uploaded" || sub.status === "duplicate_check_complete";
  const hasSimilarity = sub.similarity_results && sub.similarity_results.length > 0;

  const handleDecision = async (decision) => {
    setActing(true);
    try {
      await onDecision(sub.id, decision, reason);
    } finally {
      setActing(false);
    }
  };

  return (
    <div className="rounded-xl border border-border/40 bg-surface p-4">
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
              : sub.status === "kept_both" ? "bg-blue-500/10 text-blue-400"
              : sub.status === "duplicate_check_complete" ? "bg-yellow-500/10 text-yellow-400"
              : "bg-charcoal text-text-muted"
            }`}>
              {sub.status.replace(/_/g, " ")}
            </span>
            <span className="text-[10px] text-text-muted">
              {new Date(sub.created_at).toLocaleString()}
            </span>
            {sub.submission_type && (
              <span className="text-[10px] text-text-muted">
                via {sub.submission_type}
              </span>
            )}
          </div>
        </div>

        {isActionable && (
          <div className="flex shrink-0 items-center gap-1.5">
            <button
              onClick={() => handleDecision("accept")}
              disabled={acting}
              className="flex items-center gap-1 rounded-lg bg-green-500/10 px-2.5 py-1.5 text-xs font-medium text-green-400 transition-colors hover:bg-green-500/20 disabled:opacity-50"
            >
              {acting ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle size={13} />}
              Accept
            </button>
            <button
              onClick={() => handleDecision("keep_both")}
              disabled={acting}
              className="flex items-center gap-1 rounded-lg bg-yellow-500/10 px-2.5 py-1.5 text-xs font-medium text-yellow-400 transition-colors hover:bg-yellow-500/20 disabled:opacity-50"
            >
              <GitMerge size={13} />
              Keep Both
            </button>
            <button
              onClick={() => handleDecision("discard")}
              disabled={acting}
              className="flex items-center gap-1 rounded-lg bg-red-500/10 px-2.5 py-1.5 text-xs font-medium text-red-400 transition-colors hover:bg-red-500/20 disabled:opacity-50"
            >
              <XCircle size={13} />
              Discard
            </button>
          </div>
        )}
      </div>

      {/* Reason input for actionable submissions */}
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

      {/* Similarity results */}
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
            <div className="mt-2 rounded-lg border border-border/30 bg-charcoal/40 p-3">
              <div className="space-y-2">
                {sub.similarity_results.map((sr, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <span className="min-w-0 flex-1 truncate text-xs font-medium text-text-primary">
                      {sr.existing_skill_slug || "Unknown"}
                    </span>
                    <div className="flex items-center gap-2">
                      {sr.name_similarity > 0 && (
                        <span className="text-[10px] text-text-muted" title="Name similarity">
                          name: {(sr.name_similarity * 100).toFixed(0)}%
                        </span>
                      )}
                      {sr.content_similarity > 0 && (
                        <span className="text-[10px] text-text-muted" title="Content similarity">
                          content: {(sr.content_similarity * 100).toFixed(0)}%
                        </span>
                      )}
                      <span className="rounded-full bg-surface px-1.5 py-0.5 text-[10px] font-medium text-text-secondary">
                        {(sr.overall_overlap_score * 100).toFixed(0)}% overlap
                      </span>
                      <span className={`rounded-full px-1.5 py-0.5 text-[10px] ${
                        sr.decision_recommendation === "accept"
                          ? "bg-green-500/10 text-green-400"
                          : sr.decision_recommendation === "discard"
                            ? "bg-red-500/10 text-red-400"
                            : "bg-yellow-500/10 text-yellow-400"
                      }`}>
                        {sr.decision_recommendation}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Preview definition snippet */}
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

export default function ReviewQueue() {
  const [submissions, setSubmissions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

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
    try {
      await reviewSubmission(id, { decision, reason });
      await load();
    } catch (err) {
      setError(err.message);
    }
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

  return (
    <div className="flex-1 overflow-y-auto p-4">
      <div className="mx-auto max-w-3xl space-y-3">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs text-text-muted">{submissions.length} submission{submissions.length !== 1 ? "s" : ""}</span>
        </div>
        {submissions.map((sub) => (
          <ReviewItem key={sub.id} sub={sub} onDecision={handleDecision} />
        ))}
      </div>
    </div>
  );
}
