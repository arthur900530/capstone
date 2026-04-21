import { useState } from "react";
import { Loader2, AlertCircle, X, Send, CheckCircle } from "lucide-react";
import { createSubmission } from "../../services/api";

export default function SubmitSkillModal({ open, onClose, skill, version, onSubmitted }) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);

  if (!open || !skill) return null;

  const handleSubmit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await createSubmission({
        name: skill.name,
        description: skill.description,
        skill_md: skill.definition,
        submission_type: "authored",
      });
      setSuccess(true);
      onSubmitted?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 w-full max-w-md rounded-xl border border-border/50 bg-workspace shadow-2xl">
        <div className="flex items-center justify-between border-b border-border/40 px-5 py-4">
          <div className="flex items-center gap-2">
            <Send size={16} className="text-accent-teal" />
            <h3 className="text-sm font-semibold text-text-primary">Submit to Marketplace</h3>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-text-muted transition-colors hover:bg-surface hover:text-text-secondary"
          >
            <X size={16} />
          </button>
        </div>

        <div className="space-y-4 px-5 py-4">
          {success ? (
            <div className="flex flex-col items-center gap-3 py-4">
              <CheckCircle size={32} className="text-green-400" />
              <p className="text-sm font-medium text-text-primary">Skill submitted!</p>
              <p className="text-xs text-text-muted text-center">
                Your skill is being analyzed for duplicates. Check the Review tab for results.
              </p>
            </div>
          ) : (
            <>
              <div className="rounded-lg border border-border/40 bg-charcoal/50 p-3">
                <p className="text-xs font-medium text-text-secondary">Submitting:</p>
                <p className="mt-1 text-sm font-medium text-text-primary">
                  {skill.name}
                  {version && <span className="ml-1.5 text-xs text-text-muted">v{version}</span>}
                </p>
                {skill.description && (
                  <p className="mt-1 text-xs text-text-muted">{skill.description}</p>
                )}
              </div>

              <p className="text-xs text-text-muted">
                This will submit your skill for marketplace review. The system will automatically
                check for duplicate or overlapping skills.
              </p>

              {error && (
                <div className="flex items-center gap-2 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">
                  <AlertCircle size={13} />
                  {error}
                </div>
              )}
            </>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-border/40 px-5 py-3">
          {success ? (
            <button
              onClick={onClose}
              className="rounded-lg bg-accent-teal px-3.5 py-1.5 text-sm font-medium text-charcoal transition-colors hover:bg-accent-light"
            >
              Done
            </button>
          ) : (
            <>
              <button
                onClick={onClose}
                className="rounded-lg px-3.5 py-1.5 text-sm text-text-secondary transition-colors hover:bg-surface hover:text-text-primary"
              >
                Cancel
              </button>
              <button
                onClick={handleSubmit}
                disabled={submitting}
                className="flex items-center gap-1.5 rounded-lg bg-accent-teal px-3.5 py-1.5 text-sm font-medium text-charcoal transition-colors hover:bg-accent-light disabled:opacity-50"
              >
                {submitting ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
                Submit
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
