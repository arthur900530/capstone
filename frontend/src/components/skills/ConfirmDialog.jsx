import { useEffect } from "react";
import { Loader2 } from "lucide-react";

export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  confirmColor = "teal",
  onConfirm,
  onCancel,
  loading = false,
}) {
  useEffect(() => {
    if (!open) return;
    const handleKey = (e) => { if (e.key === "Escape" && !loading) onCancel?.(); };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open, loading, onCancel]);

  if (!open) return null;

  const colorMap = {
    teal: "bg-accent-teal text-charcoal hover:bg-accent-light",
    red: "bg-red-500/80 text-white hover:bg-red-500",
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onCancel} />
      <div className="relative z-10 w-full max-w-sm animate-scale-in rounded-xl border border-border/50 bg-workspace shadow-2xl">
        <div className="px-5 pt-5 pb-2">
          <h3 className="text-sm font-semibold text-text-primary">{title}</h3>
          <p className="mt-2 text-xs leading-relaxed text-text-secondary">{message}</p>
        </div>
        <div className="flex items-center justify-end gap-2 px-5 pb-4 pt-3">
          <button
            onClick={onCancel}
            disabled={loading}
            className="rounded-lg px-3.5 py-1.5 text-xs text-text-secondary transition-colors hover:bg-surface hover:text-text-primary disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={loading}
            className={`flex items-center gap-1.5 rounded-lg px-3.5 py-1.5 text-xs font-medium transition-colors disabled:opacity-50 ${colorMap[confirmColor] || colorMap.teal}`}
          >
            {loading && <Loader2 size={12} className="animate-spin" />}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
