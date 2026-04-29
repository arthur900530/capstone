import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
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
  "document_control_governance",
  "purpose_scope_intended_use",
  "model_data_overview",
  "risk_assessment_controls",
  "evaluation_outputs",
  "performance_testing_validation",
  "deployment_monitoring_lifecycle",
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

function SectionContent({ value }) {
  const normalized = normalizeDisplayValue(value);

  if (
    normalized &&
    typeof normalized === "object" &&
    Array.isArray(normalized.rows)
  ) {
    const columns = Array.isArray(normalized.columns)
      ? normalized.columns
      : ["Metric", "Value"];
    return (
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr>
              {columns.map((column) => (
                <th
                  key={column}
                  className="border border-border/50 bg-surface/60 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-text-primary"
                >
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {normalized.rows.map((row, rowIndex) => {
              const cells = Array.isArray(row) ? row : [row];
              return (
                <tr key={rowIndex} className="odd:bg-workspace/30">
                  {cells.map((cell, cellIndex) => (
                    <td
                      key={`${rowIndex}-${cellIndex}`}
                      className="border border-border/40 px-3 py-2 align-top leading-6 text-text-secondary"
                    >
                      {String(cell ?? "Not specified")}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  }

  if (Array.isArray(normalized)) {
    return (
      <ul className="space-y-2 pl-4">
        {normalized.map((item, index) => (
          <li
            key={`${String(item)}-${index}`}
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
                  {item.map((entry, index) => (
                    <li
                      key={`${String(entry)}-${index}`}
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
    <ul className="space-y-2 pl-4">
      <li className="list-disc text-sm leading-6 text-text-secondary marker:text-accent-teal">
        {normalized}
      </li>
    </ul>
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
  const references = context.policy_references || [];
  const llm = data?.llm || {};
  const narrativeEntries = NARRATIVE_ORDER
    .filter((key) => Object.prototype.hasOwnProperty.call(sections, key))
    .map((key) => [key, sections[key]]);
  const approvalSection = Array.isArray(sections.approval_notes)
    ? sections.approval_notes.join("\n")
    : sections.approval_notes || "";
  const generatedApprovalNote = String(approvalSection).startsWith("Not specified")
    ? ""
    : approvalSection;
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
              href={employeeGovernanceUrl(employee.id)}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-2 rounded-md border border-border/70 px-3 py-2 text-xs font-medium text-text-secondary hover:border-accent-teal/50 hover:text-accent-teal"
            >
              <ExternalLink size={14} />
              HTML
            </a>
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-2">
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
            Notes are saved to the employee record and are not generated by the LLM.
          </p>
        </Section>
      </div>
    </div>
  );
}
