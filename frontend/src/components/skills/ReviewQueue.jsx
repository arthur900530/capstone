import { useState, useEffect } from "react";
import { Loader2, AlertCircle, ClipboardCheck, CheckCircle, XCircle, GitMerge } from "lucide-react";
import { fetchSubmissions, reviewSubmission } from "../../services/api";

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

  const handleDecision = async (id, decision) => {
    try {
      await reviewSubmission(id, { decision, reason: "" });
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
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-4">
      <div className="mx-auto max-w-3xl space-y-3">
        {submissions.map((sub) => (
          <div
            key={sub.id}
            className="rounded-xl border border-border/40 bg-surface p-4"
          >
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
                    : "bg-surface text-text-muted"
                  }`}>
                    {sub.status}
                  </span>
                  <span className="text-[10px] text-text-muted">
                    {new Date(sub.created_at).toLocaleString()}
                  </span>
                </div>
              </div>

              {/* Actions — only show for actionable statuses */}
              {(sub.status === "uploaded" || sub.status === "duplicate_check_complete") && (
                <div className="flex shrink-0 items-center gap-1.5">
                  <button
                    onClick={() => handleDecision(sub.id, "accept")}
                    className="flex items-center gap-1 rounded-lg bg-green-500/10 px-2.5 py-1.5 text-xs font-medium text-green-400 transition-colors hover:bg-green-500/20"
                    title="Accept"
                  >
                    <CheckCircle size={13} />
                    Accept
                  </button>
                  <button
                    onClick={() => handleDecision(sub.id, "keep_both")}
                    className="flex items-center gap-1 rounded-lg bg-yellow-500/10 px-2.5 py-1.5 text-xs font-medium text-yellow-400 transition-colors hover:bg-yellow-500/20"
                    title="Keep Both"
                  >
                    <GitMerge size={13} />
                    Keep Both
                  </button>
                  <button
                    onClick={() => handleDecision(sub.id, "discard")}
                    className="flex items-center gap-1 rounded-lg bg-red-500/10 px-2.5 py-1.5 text-xs font-medium text-red-400 transition-colors hover:bg-red-500/20"
                    title="Discard"
                  >
                    <XCircle size={13} />
                    Discard
                  </button>
                </div>
              )}
            </div>

            {/* Similarity results */}
            {sub.similarity_results && sub.similarity_results.length > 0 && (
              <div className="mt-3 rounded-lg border border-border/30 bg-charcoal/50 p-3">
                <p className="mb-2 text-[11px] font-medium text-text-secondary">Similar Skills</p>
                <div className="space-y-1.5">
                  {sub.similarity_results.map((sr, i) => (
                    <div key={i} className="flex items-center gap-3 text-xs">
                      <span className="min-w-0 flex-1 truncate text-text-primary">
                        {sr.existing_skill_slug || "Unknown"}
                      </span>
                      <span className="text-text-muted">
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
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
