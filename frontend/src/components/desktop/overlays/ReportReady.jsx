import { CheckCircle2 } from "lucide-react";

export default function ReportReady({ visible, employeeName }) {
  if (!visible) return null;

  return (
    <>
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="bg-surface rounded-2xl p-8 shadow-2xl flex flex-col items-center gap-4 animate-badge">
          <div className="h-16 w-16 rounded-full bg-emerald-400/20 flex items-center justify-center">
            <CheckCircle2 size={32} className="text-emerald-400" />
          </div>
          <p className="text-xl font-semibold text-text-primary">Report Ready</p>
          <p className="text-sm text-text-muted text-center">
            {employeeName} has completed the task
          </p>
        </div>
      </div>
    </>
  );
}
