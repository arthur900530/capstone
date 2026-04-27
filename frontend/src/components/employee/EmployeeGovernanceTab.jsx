import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  Download,
  ExternalLink,
  FileText,
  Loader2,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import {
  employeeGovernanceUrl,
  fetchEmployeeGovernance,
} from "../../services/api";

function LoadingState() {
  return (
    <div className="flex flex-1 items-center justify-center">
      <Loader2 size={20} className="animate-spin text-accent-teal" />
    </div>
  );
}

function ErrorState({ message, onRetry }) {
  return (
    <div className="flex flex-1 items-center justify-center">
      <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4">
        <div className="mb-3 flex items-center gap-2 text-sm text-red-300">
          <AlertCircle size={16} />
          {message}
        </div>
        <button
          type="button"
          onClick={onRetry}
          className="rounded-md border border-red-400/40 px-3 py-1.5 text-xs font-medium text-red-100 hover:bg-red-400/10"
        >
          Retry
        </button>
      </div>
    </div>
  );
}

const NARRATIVE_ORDER = [
  "system_overview",
  "intended_use",
  "data_inputs",
  "evaluation_summary",
  "risk_summary",
  "controls_summary",
  "monitoring_plan",
  "limitations",
];

function Section({ title, children, className = "" }) {
  return (
    <section
      className={`rounded-lg border border-border/60 bg-[#2a2c31] p-4 shadow-[0_2px_12px_rgba(0,0,0,0.25)] ${className}`}
    >
      <h3 className="mb-3 border-b border-border/50 pb-2 text-sm font-semibold uppercase tracking-wider text-accent-light">
        {title}
      </h3>
      {children}
    </section>
  );
}

function sectionTitle(key) {
  return key
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function normalizeDisplayValue(value) {
  if (value == null || value === "") return "Not specified";
  if (Array.isArray(value)) return value;
  if (typeof value === "object") return value;
  if (typeof value !== "string") return String(value);

  const trimmed = value.trim();
  if (!trimmed) return "Not specified";

  if (
    (trimmed.startsWith("{") && trimmed.endsWith("}")) ||
    (trimmed.startsWith("[") && trimmed.endsWith("]"))
  ) {
    try {
      return JSON.parse(trimmed);
    } catch {
      // Keep the original text if it is not valid JSON.
    }
  }
  return trimmed;
}

function parseLegacyEvaluationSummary(value) {
  if (typeof value !== "string") return null;
  const labels = [
    "Source",
    "Tasks",
    "Avg Task Score",
    "Avg Leaf Rate",
    "Avg User Rating",
    "Rated Tasks",
    "Annotated Tasks",
    "Unannotated Tasks",
    "Avg Tool Calls",
    "Avg Trials",
    "Reflexion Rate",
    "Tool Mix",
    "Recent Task Count",
  ];
  const matches = [...value.matchAll(
    /(Source|Tasks|Avg Task Score|Avg Leaf Rate|Avg User Rating|Rated Tasks|Annotated Tasks|Unannotated Tasks|Avg Tool Calls|Avg Trials|Reflexion Rate|Tool Mix|Recent Task Count):\s*/g,
  )];
  if (matches.length < 2) return null;

  return matches.map((match, index) => {
    const next = matches[index + 1];
    const raw = value.slice(match.index + match[0].length, next?.index ?? value.length);
    const label = labels.includes(match[1]) ? match[1] : sectionTitle(match[1]);
    return [label, raw.replace(/\.\s*$/, "").trim()];
  });
}

function SectionContent({ value }) {
  const legacyEvaluation = parseLegacyEvaluationSummary(value);
  if (legacyEvaluation) {
    return (
      <dl className="space-y-2">
        {legacyEvaluation.map(([key, item]) => (
          <div key={key} className="grid gap-1 rounded-md border border-border/40 bg-surface/40 p-3 sm:grid-cols-[180px_minmax(0,1fr)]">
            <dt className="text-xs font-semibold text-text-primary">{key}</dt>
            <dd className="mt-1 text-sm leading-6 text-text-secondary">
              {key === "Tool Mix" ? (
                <ul className="space-y-1 pl-4">
                  {item
                    .replace(/^\[\[/, "")
                    .replace(/\]\]$/, "")
                    .split(/\],\s*\[/)
                    .map((entry) => entry.replace(/['"]/g, "").split(",").map((part) => part.trim()))
                    .map(([tool, count]) => (
                      <li key={`${tool}-${count}`} className="list-disc marker:text-accent-teal">
                        {tool}: {count}
                      </li>
                    ))}
                </ul>
              ) : (
                item || "Not specified"
              )}
            </dd>
          </div>
        ))}
      </dl>
    );
  }

  const normalized = normalizeDisplayValue(value);

  if (Array.isArray(normalized)) {
    return (
      <ul className="space-y-2 pl-4">
        {normalized.map((item) => (
          <li
            key={String(item)}
            className="list-disc text-sm leading-6 text-text-secondary marker:text-accent-teal"
          >
            {String(item)}
          </li>
        ))}
      </ul>
    );
  }

  if (typeof normalized === "object") {
    return (
      <dl className="space-y-2">
        {Object.entries(normalized).map(([key, item]) => (
          <div key={key} className="grid gap-1 rounded-md border border-border/40 bg-surface/40 p-3 sm:grid-cols-[180px_minmax(0,1fr)]">
            <dt className="text-xs font-semibold text-text-primary">
              {key}
            </dt>
            <dd className="mt-1 text-sm leading-6 text-text-secondary">
              {Array.isArray(item) ? (
                <ul className="space-y-1 pl-4">
                  {item.map((entry) => (
                    <li
                      key={String(entry)}
                      className="list-disc marker:text-accent-teal"
                    >
                      {String(entry)}
                    </li>
                  ))}
                </ul>
              ) : (
                String(item ?? "Not specified")
              )}
            </dd>
          </div>
        ))}
      </dl>
    );
  }

  return (
    <p className="text-sm leading-6 text-text-secondary">
      {normalized}
    </p>
  );
}

function formatPercent(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "Not specified";
  return `${(n * 100).toFixed(1)}%`;
}

function MetricTile({ label, value, sub }) {
  return (
    <div className="rounded-md border border-border/40 bg-surface/40 p-3">
      <div className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">
        {label}
      </div>
      <div className="mt-1 text-lg font-semibold text-text-primary">
        {value}
      </div>
      {sub ? <div className="mt-1 text-xs text-text-muted">{sub}</div> : null}
    </div>
  );
}

export default function EmployeeGovernanceTab({
  employee,
  cachedPackage,
  onPackageLoaded,
  approvalNote,
  onApprovalNoteChange,
  onApprovalNoteSave,
}) {
  const [data, setData] = useState(cachedPackage || null);
  const [loading, setLoading] = useState(!cachedPackage);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const lastSavedApprovalNoteRef = useRef(approvalNote ?? "");

  async function load({ showSpinner = true, force = false } = {}) {
    if (showSpinner) setLoading(true);
    setRefreshing(!showSpinner);
    setError(null);
    try {
      const packageData = await fetchEmployeeGovernance(employee.id, { force });
      setData(packageData);
      onPackageLoaded?.(packageData);
    } catch (err) {
      setError(err?.message || "Failed to load governance package");
    } finally {
      if (showSpinner) setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    if (cachedPackage) {
      setData(cachedPackage);
      setLoading(false);
      setError(null);
      return undefined;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchEmployeeGovernance(employee.id)
      .then((res) => {
        if (!cancelled) {
          setData(res);
          onPackageLoaded?.(res);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || "Failed to load governance package");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [cachedPackage, employee.id, onPackageLoaded]);

  useEffect(() => {
    const note = approvalNote ?? "";
    if (note === lastSavedApprovalNoteRef.current) return undefined;

    const timer = window.setTimeout(async () => {
      try {
        await onApprovalNoteSave?.(note);
        lastSavedApprovalNoteRef.current = note;
      } catch {
        // Keep the local edit visible; a later edit or blur can retry.
      }
    }, 600);

    return () => window.clearTimeout(timer);
  }, [approvalNote, onApprovalNoteSave]);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={() => load()} />;

  const context = data?.context || {};
  const sections = data?.sections || {};
  const risk = context.risk || {};
  const references = context.policy_references || [];
  const controls = context.controls || [];
  const llm = data?.llm || {};
  const evaluation = context.evaluation || {};
  const narrativeEntries = NARRATIVE_ORDER
    .filter((key) => Object.prototype.hasOwnProperty.call(sections, key))
    .map((key) => [key, sections[key]]);
  const generatedApprovalNote = String(sections.approval_notes || "").startsWith("Not specified")
    ? ""
    : sections.approval_notes || "";
  const displayedApprovalNote = approvalNote ?? generatedApprovalNote;

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-5xl space-y-5 p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="mb-2 flex items-center gap-2">
              <ShieldCheck size={18} className="text-accent-teal" />
              <h2 className="text-sm font-semibold text-text-primary">
                Financial services governance package
              </h2>
            </div>
            <p className="max-w-3xl text-xs leading-5 text-text-muted">
              Generated documentation for model-risk and AI-governance review.
              The package cites financial-services governance references and
              does not assert regulatory approval.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => load({ showSpinner: false, force: true })}
              className="flex items-center gap-2 rounded-md border border-border/70 px-3 py-2 text-xs font-medium text-text-secondary hover:border-accent-teal/50 hover:text-accent-teal"
            >
              <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
              Refresh
            </button>
            <a
              href={employeeGovernanceUrl(employee.id, "html")}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-2 rounded-md border border-border/70 px-3 py-2 text-xs font-medium text-text-secondary hover:border-accent-teal/50 hover:text-accent-teal"
            >
              <ExternalLink size={14} />
              HTML
            </a>
            <a
              href={employeeGovernanceUrl(employee.id, "pdf")}
              className="flex items-center gap-2 rounded-md bg-accent-teal px-3 py-2 text-xs font-semibold text-white hover:bg-accent-deep"
            >
              <Download size={14} />
              PDF
            </a>
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-3">
          <Section title="Risk tier">
            <div className="text-2xl font-semibold text-text-primary">
              {risk.tier || "Not specified"}
            </div>
            <p className="mt-1 text-xs text-text-muted">
              Deterministic score {risk.score ?? "Not specified"}
            </p>
          </Section>
          <Section title="LLM drafting">
            <div className="text-sm font-medium text-text-primary">
              {llm.used ? "LLM narrative used" : "Template fallback used"}
            </div>
            <p className="mt-1 text-xs text-text-muted">
              Model: {llm.model || "Not specified"}
            </p>
          </Section>
          <Section title="Generated">
            <div className="text-sm font-medium text-text-primary">
              {context.generated_at
                ? new Date(context.generated_at).toLocaleString()
                : "Not specified"}
            </div>
            <p className="mt-1 text-xs text-text-muted">
              {data?.disclaimer}
            </p>
          </Section>
        </div>

        <Section title="Evaluation metrics">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <MetricTile
              label="Tasks"
              value={evaluation.tasks ?? 0}
              sub={`${evaluation.annotated_tasks ?? 0} annotated`}
            />
            <MetricTile
              label="Task score"
              value={formatPercent(evaluation.avg_task_score)}
              sub="Weighted trajectory score"
            />
            <MetricTile
              label="User rating"
              value={
                Number(evaluation.avg_user_rating)
                  ? `${Number(evaluation.avg_user_rating).toFixed(2)} / 5`
                  : "Not specified"
              }
              sub={`${evaluation.rated_tasks ?? 0} rated task(s)`}
            />
            <MetricTile
              label="Reflexion"
              value={formatPercent(evaluation.reflexion_rate)}
              sub={`${evaluation.avg_trials ?? 0} avg trials`}
            />
          </div>
        </Section>

        <Section title="Reference governance policies">
          <div className="space-y-3">
            {references.map((ref) => (
              <a
                key={ref.url}
                href={ref.url}
                target="_blank"
                rel="noreferrer"
                className="block rounded-md border border-border/50 bg-surface/40 p-3 transition-colors hover:border-accent-teal/40"
              >
                <div className="flex items-center gap-2 text-sm font-medium text-accent-light">
                  <FileText size={14} />
                  {ref.name}
                  <ExternalLink size={12} />
                </div>
                <p className="mt-1 text-xs leading-5 text-text-muted">
                  {ref.summary}
                </p>
              </a>
            ))}
          </div>
        </Section>

        <div className="space-y-4">
          {narrativeEntries.map(([key, value]) => (
            <Section key={key} title={sectionTitle(key)}>
              <SectionContent value={value} />
            </Section>
          ))}
        </div>

        <Section title="Approval notes">
          <textarea
            value={displayedApprovalNote}
            onChange={(event) => onApprovalNoteChange?.(event.target.value)}
            onBlur={(event) => onApprovalNoteSave?.(event.target.value)}
            placeholder="Add reviewer, admin, or governance approval notes."
            className="min-h-32 w-full resize-y rounded-md border border-border/60 bg-surface/50 p-3 text-sm leading-6 text-text-primary outline-none transition-colors placeholder:text-text-muted focus:border-accent-teal/70"
          />
          <p className="mt-2 text-xs text-text-muted">
            Notes are preserved while this employee page is open and are not generated by the LLM.
          </p>
        </Section>

        <div className="grid gap-4 lg:grid-cols-2">
          <Section title="Deterministic risk drivers">
            <ul className="space-y-2 pl-4">
              {(risk.reasons || []).map((reason) => (
                <li
                  key={reason}
                  className="list-disc text-sm leading-6 text-text-secondary marker:text-accent-teal"
                >
                  {reason}
                </li>
              ))}
            </ul>
          </Section>
          <Section title="Required controls">
            <ul className="space-y-2 pl-4">
              {controls.map((control) => (
                <li
                  key={control}
                  className="list-disc text-sm leading-6 text-text-secondary marker:text-accent-teal"
                >
                  {control}
                </li>
              ))}
            </ul>
          </Section>
        </div>
      </div>
    </div>
  );
}
