import { FlaskConical, Loader2, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  deleteTestCase,
  generateTestCases,
  listTestCaseRuns,
  listTestCases,
  runAllTestCases,
  runTestCase,
  updateTestCase,
} from "../../services/api";
import TaskTrajectoryDrawer from "./TaskTrajectoryDrawer";
import TestCaseCard from "./TestCaseCard";
import TestCaseRunDetail from "./TestCaseRunDetail";

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
  const [trajectoryTask, setTrajectoryTask] = useState(null);

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

  const handleRunAll = async () => {
    setRunningAll(true);
    setError(null);
    try {
      await runAllTestCases(employee.id);
      await load();
    } catch (err) {
      setError(err.message || "Failed to run all test cases");
    } finally {
      setRunningAll(false);
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
            <p className="text-xs text-text-muted">Generate and run edge-case tests for this employee.</p>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="number"
              min={1}
              max={20}
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
          </div>
        </div>

        {error ? (
          <div className="rounded-lg bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</div>
        ) : null}

        {cases.length === 0 ? (
          <div className="flex min-h-[320px] flex-col items-center justify-center rounded-xl border border-border/40 bg-surface text-center">
            <FlaskConical size={36} className="mb-3 text-text-muted" />
            <p className="text-base font-medium text-text-primary">Generate edge-case tests for this employee</p>
            <button
              type="button"
              className="mt-4 rounded-lg bg-accent-teal px-6 py-2.5 text-sm font-medium text-workspace"
              onClick={handleGenerate}
              disabled={generating}
            >
              {generating ? "Generating..." : "Generate edge-case tests"}
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
            setTrajectoryTask({
              sessionId: run.agent_session_id,
              taskIndex: 0,
              run: { prompt_preview: "Auto test trajectory" },
            });
          }}
        />
      ) : null}
      {trajectoryTask ? (
        <TaskTrajectoryDrawer
          employeeId={employee.id}
          task={trajectoryTask}
          onClose={() => setTrajectoryTask(null)}
        />
      ) : null}
    </div>
  );
}
