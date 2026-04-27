import { useEffect, useState } from "react";
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

function Section({ title, children }) {
  return (
    <section className="rounded-lg border border-border/60 bg-[#2a2c31] p-4 shadow-[0_2px_12px_rgba(0,0,0,0.25)]">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-secondary">
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

export default function EmployeeGovernanceTab({ employee }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);

  async function load({ showSpinner = true } = {}) {
    if (showSpinner) setLoading(true);
    setRefreshing(!showSpinner);
    setError(null);
    try {
      setData(await fetchEmployeeGovernance(employee.id));
    } catch (err) {
      setError(err?.message || "Failed to load governance package");
    } finally {
      if (showSpinner) setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchEmployeeGovernance(employee.id)
      .then((res) => {
        if (!cancelled) setData(res);
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
  }, [employee.id]);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} onRetry={() => load()} />;

  const context = data?.context || {};
  const sections = data?.sections || {};
  const risk = context.risk || {};
  const references = context.policy_references || [];
  const controls = context.controls || [];
  const llm = data?.llm || {};

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
              onClick={() => load({ showSpinner: false })}
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

        <div className="grid gap-4 lg:grid-cols-2">
          {Object.entries(sections).map(([key, value]) => (
            <Section key={key} title={sectionTitle(key)}>
              <p className="text-sm leading-6 text-text-secondary">
                {value || "Not specified"}
              </p>
            </Section>
          ))}
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <Section title="Deterministic risk drivers">
            <ul className="space-y-2">
              {(risk.reasons || []).map((reason) => (
                <li key={reason} className="text-sm leading-5 text-text-secondary">
                  {reason}
                </li>
              ))}
            </ul>
          </Section>
          <Section title="Required controls">
            <ul className="space-y-2">
              {controls.map((control) => (
                <li key={control} className="text-sm leading-5 text-text-secondary">
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
