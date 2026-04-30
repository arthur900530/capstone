import { Download, FlaskConical, Loader2, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  deleteTestCase,
  exportTestCase,
  exportTestSuite,
  generateTestCases,
  listTestCaseRuns,
  listTestCases,
  runTestCase,
  updateTestCase,
} from "../../services/api";
import TestCaseCard from "./TestCaseCard";
import TestCaseRunDetail from "./TestCaseRunDetail";
import TestCaseRunEventsDrawer from "./TestCaseRunEventsDrawer";

// Browser-side helper: turn a JSON object into a downloaded file. The Blob
// route is the only cross-browser option that does NOT round-trip through
// `data:` URLs (which break for payloads larger than a few hundred KB).
function downloadJson(filename, payload) {
  const json = JSON.stringify(payload, null, 2);
  const blob = new Blob([json], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

// Sanitise free-form text for use in a filename so the download works
// across operating systems. Filesystems disagree on which characters are
// legal — this whitelist (alphanumeric, dash, underscore) is universally safe.
function slugifyForFilename(value, fallback = "untitled") {
  const slug = (value || "")
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
  return slug || fallback;
}

function todayStamp() {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}${mm}${dd}`;
}

// Pretty-print a millisecond duration as "Xm Ys" (or "Ys" under a minute).
// Used by the Run-all progress panel for elapsed + ETA.
function formatDuration(ms) {
  const totalSeconds = Math.max(0, Math.round(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
}

// Estimate remaining time using the rolling average of completed durations.
// Caller guarantees `progress.durations.length > 0`.
function estimateRemaining(progress) {
  const sum = progress.durations.reduce((acc, d) => acc + d, 0);
  const avg = sum / progress.durations.length;
  return avg * (progress.total - progress.completed);
}

export default function AutoTestsTab({ employee }) {
  const [count, setCount] = useState(5);
  const [cases, setCases] = useState([]);
  const [runsByCase, setRunsByCase] = useState({});
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [runningAll, setRunningAll] = useState(false);
  const [runningCaseId, setRunningCaseId] = useState(null);
  const [error, setError] = useState(null);
  const [activeRun, setActiveRun] = useState(null);
  // The id of the test-case run whose event stream is currently displayed
  // in the drawer. Stage 1 only needs the run id — the drawer fetches the
  // events itself.
  const [trajectoryRunId, setTrajectoryRunId] = useState(null);
  const [trajectoryCaseId, setTrajectoryCaseId] = useState(null);
  // Live progress for the "Run all draft tests" batch. Null when idle.
  // Shape: { total, completed, currentTitle, startedAt (Date.now), durations: ms[] }
  const [runAllProgress, setRunAllProgress] = useState(null);
  const [exportingSuite, setExportingSuite] = useState(false);
  // Tick state — its only job is to force a re-render every second so the
  // elapsed-time label in the progress panel updates between case completions.
  const [, setNowTick] = useState(0);

  useEffect(() => {
    if (!runningAll) return undefined;
    const id = setInterval(() => setNowTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, [runningAll]);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const caseRes = await listTestCases(employee.id);
      const loadedCases = caseRes.cases || [];
      setCases(loadedCases);
      const runPairs = await Promise.all(
        loadedCases.map(async (testCase) => {
          const runRes = await listTestCaseRuns(employee.id, testCase.id);
          return [testCase.id, runRes.runs || []];
        }),
      );
      setRunsByCase(Object.fromEntries(runPairs));
    } catch (err) {
      setError(err.message || "Failed to load test cases");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [employee.id]);

  const draftCount = useMemo(
    () => cases.filter((item) => item.status === "draft").length,
    [cases],
  );

  const handleGenerate = async () => {
    setGenerating(true);
    setError(null);
    try {
      await generateTestCases(employee.id, count);
      await load();
    } catch (err) {
      setError(err.message || "Failed to generate test cases");
    } finally {
      setGenerating(false);
    }
  };

  const handleRunCase = async (caseId) => {
    setRunningCaseId(caseId);
    setError(null);
    try {
      await runTestCase(employee.id, caseId);
      await load();
    } catch (err) {
      setError(err.message || "Failed to run test case");
    } finally {
      setRunningCaseId(null);
    }
  };

  const handleExportSuite = async () => {
    setExportingSuite(true);
    setError(null);
    try {
      const data = await exportTestSuite(employee.id);
      const slug = slugifyForFilename(employee.name, "employee");
      downloadJson(`auto-tests_${slug}_${todayStamp()}.json`, data);
    } catch (err) {
      setError(err.message || "Failed to export test suite");
    } finally {
      setExportingSuite(false);
    }
  };

  const handleExportCase = async (caseId, caseTitle) => {
    setError(null);
    try {
      const data = await exportTestCase(employee.id, caseId);
      const slug = slugifyForFilename(caseTitle, "test-case");
      downloadJson(`auto-test_${slug}.json`, data);
    } catch (err) {
      setError(err.message || "Failed to export test case");
    }
  };

  const handleRunAll = async () => {
    // Snapshot the draft cases up-front so newly-created drafts mid-run
    // don't sneak into this batch.
    const drafts = cases.filter((item) => item.status === "draft");
    if (drafts.length === 0) return;

    setRunningAll(true);
    setError(null);
    setRunAllProgress({
      total: drafts.length,
      completed: 0,
      currentTitle: drafts[0]?.title ?? null,
      startedAt: Date.now(),
      durations: [],
    });

    try {
      for (let i = 0; i < drafts.length; i += 1) {
        const tc = drafts[i];
        setRunAllProgress((p) => (p ? { ...p, currentTitle: tc.title } : p));
        const t0 = Date.now();
        try {
          await runTestCase(employee.id, tc.id);
        } catch (err) {
          // Per-case failure shouldn't abort the batch — surface the most
          // recent error in the banner and continue with the remaining cases.
          setError(err.message || `Failed to run "${tc.title}"`);
        }
        const dt = Date.now() - t0;
        setRunAllProgress((p) =>
          p
            ? {
                ...p,
                completed: p.completed + 1,
                durations: [...p.durations, dt],
              }
            : p,
        );
      }
      await load();
    } finally {
      setRunningAll(false);
      setRunAllProgress(null);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <Loader2 size={20} className="animate-spin text-accent-teal" />
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-5xl space-y-4">
        <div className="flex flex-wrap items-end justify-between gap-3 rounded-xl border border-border/40 bg-surface p-4">
          <div>
            <p className="text-sm font-semibold text-text-primary">Auto Tests</p>
            <p className="text-xs text-text-muted">
              Generate a comprehensive suite of happy-path, normal, and edge-case tests for this employee.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="number"
              min={1}
              max={100}
              value={count}
              onChange={(e) => setCount(Number(e.target.value) || 1)}
              className="w-20 rounded-lg border border-border/50 bg-workspace px-2 py-1.5 text-sm"
            />
            <button
              type="button"
              className="rounded-lg bg-accent-teal px-6 py-2.5 text-sm font-medium text-workspace"
              onClick={handleGenerate}
              disabled={generating}
            >
              <span className="inline-flex items-center gap-2">
                {generating ? <Loader2 size={14} className="animate-spin" /> : <ShieldCheck size={14} />}
                Generate
              </span>
            </button>
            {draftCount > 0 ? (
              <button
                type="button"
                className="rounded-lg border border-border/60 px-4 py-2.5 text-sm"
                onClick={handleRunAll}
                disabled={runningAll}
              >
                <span className="inline-flex items-center gap-2">
                  {runningAll ? <Loader2 size={14} className="animate-spin" /> : null}
                  Run all draft tests
                </span>
              </button>
            ) : null}
            {cases.length > 0 ? (
              <button
                type="button"
                className="rounded-lg border border-border/60 px-4 py-2.5 text-sm"
                onClick={handleExportSuite}
                disabled={exportingSuite || runningAll || runningCaseId !== null}
                title="Download all cases and runs as JSON"
              >
                <span className="inline-flex items-center gap-2">
                  {exportingSuite ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
                  Export suite
                </span>
              </button>
            ) : null}
          </div>
        </div>

        {error ? (
          <div className="rounded-lg bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</div>
        ) : null}

        {runAllProgress ? (
          <div className="space-y-2 rounded-xl border border-border/40 bg-surface p-4">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium text-text-primary">
                Running tests: {runAllProgress.completed} of {runAllProgress.total}
              </span>
              <span className="text-text-muted">
                elapsed {formatDuration(Date.now() - runAllProgress.startedAt)}
                {runAllProgress.durations.length > 0
                  ? ` · ETA ${formatDuration(estimateRemaining(runAllProgress))}`
                  : ""}
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-workspace">
              <div
                className="h-full bg-accent-teal transition-[width] duration-300"
                style={{
                  width: `${
                    runAllProgress.total > 0
                      ? (runAllProgress.completed / runAllProgress.total) * 100
                      : 0
                  }%`,
                }}
              />
            </div>
            {runAllProgress.currentTitle ? (
              <p className="truncate text-xs text-text-muted">
                Now running:{" "}
                <span className="text-text-secondary">{runAllProgress.currentTitle}</span>
              </p>
            ) : null}
          </div>
        ) : null}

        {cases.length === 0 ? (
          <div className="flex min-h-[320px] flex-col items-center justify-center rounded-xl border border-border/40 bg-surface text-center">
            <FlaskConical size={36} className="mb-3 text-text-muted" />
            <p className="text-base font-medium text-text-primary">Generate a comprehensive test suite for this employee</p>
            <button
              type="button"
              className="mt-4 rounded-lg bg-accent-teal px-6 py-2.5 text-sm font-medium text-workspace"
              onClick={handleGenerate}
              disabled={generating}
            >
              {generating ? "Generating..." : "Generate test suite"}
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {cases.map((testCase) => (
              <TestCaseCard
                key={testCase.id}
                testCase={testCase}
                latestRun={(runsByCase[testCase.id] || [])[0]}
                runLoading={runningCaseId === testCase.id}
                onRun={handleRunCase}
                onDelete={async (caseId) => {
                  await deleteTestCase(employee.id, caseId);
                  await load();
                }}
                onUpdate={async (caseId, updates) => {
                  await updateTestCase(employee.id, caseId, updates);
                  await load();
                }}
                onOpenRun={(run) => setActiveRun(run)}
                onExport={handleExportCase}
              />
            ))}
          </div>
        )}
      </div>

      {activeRun ? (
        <TestCaseRunDetail
          run={activeRun}
          onClose={() => setActiveRun(null)}
          onOpenTrajectory={(run) => {
            setActiveRun(null);
            setTrajectoryRunId(run.id);
            setTrajectoryCaseId(run.test_case_id);
          }}
        />
      ) : null}
      {trajectoryRunId ? (
        <TestCaseRunEventsDrawer
          employeeId={employee.id}
          caseId={trajectoryCaseId}
          runId={trajectoryRunId}
          onClose={() => {
            setTrajectoryRunId(null);
            setTrajectoryCaseId(null);
          }}
        />
      ) : null}
    </div>
  );
}
