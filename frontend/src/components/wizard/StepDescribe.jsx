export default function StepDescribe({ description, onChange, onNext }) {
  return (
    <div className="mx-auto max-w-2xl">
      <h2 className="mb-2 text-xl font-semibold text-text-primary">
        What do you need your digital employee to do?
      </h2>
      <p className="mb-6 text-sm text-text-muted">
        A short description is fine — we&apos;ll expand it into a full system
        prompt you can review and edit later from your employee&apos;s page.
      </p>

      <textarea
        autoFocus
        rows={5}
        value={description}
        onChange={(e) => onChange(e.target.value)}
        placeholder="e.g. SEC filings expert for AAPL — focus on revenue trends"
        className="w-full resize-none rounded-xl border border-border/40 bg-surface px-4 py-3 text-sm text-text-primary placeholder:text-text-muted/60 focus:border-accent-teal/50 focus:outline-none focus:ring-1 focus:ring-accent-teal/30"
      />

      <div className="mt-6 flex justify-end">
        <button
          onClick={onNext}
          disabled={!description.trim()}
          className="rounded-lg bg-accent-teal px-6 py-2.5 text-sm font-medium text-workspace transition-colors hover:bg-accent-teal/90 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Next
        </button>
      </div>
    </div>
  );
}
