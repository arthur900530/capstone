// JS port of backend.workflow.compute_workflow_completion + a few helpers
// for rendering subtree-level chips inside <WorkflowTree>.
//
// Per-step adherence is binary (satisfied true/false). The rollup is
// counted across LEAF steps so a parent step that wraps three leaves
// contributes three units to passed/total.

function pathsAreEqual(a, b) {
  if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}

export function alignmentForPath(alignment, path) {
  if (!alignment || !Array.isArray(alignment.steps)) return null;
  for (const step of alignment.steps) {
    if (pathsAreEqual(step?.path, path)) return step;
  }
  return null;
}

function isLeaf(step) {
  return !Array.isArray(step?.children) || step.children.length === 0;
}

function* iterLeafPaths(steps, prefix = []) {
  if (!Array.isArray(steps)) return;
  for (let i = 0; i < steps.length; i++) {
    const step = steps[i];
    const path = [...prefix, i];
    if (isLeaf(step)) {
      yield path;
    } else {
      yield* iterLeafPaths(step.children, path);
    }
  }
}

export function leafPaths(rootSteps) {
  return Array.from(iterLeafPaths(rootSteps));
}

export function computeWorkflowCompletion(workflow, alignment) {
  const root = workflow?.root_steps || [];
  const leaves = leafPaths(root);
  const total = leaves.length;
  if (total === 0) {
    return { passed: 0, total: 0, rate: null };
  }
  let passed = 0;
  for (const path of leaves) {
    const entry = alignmentForPath(alignment, path);
    if (entry?.satisfied === true) passed += 1;
  }
  return { passed, total, rate: passed / total };
}

// Subtree rollup for the chip rendered next to non-leaf workflow steps.
export function subtreeCompletion(step, prefix, alignment) {
  if (isLeaf(step)) {
    const entry = alignmentForPath(alignment, prefix);
    if (!entry) return { passed: 0, total: 1, rate: 0 };
    return entry.satisfied === true
      ? { passed: 1, total: 1, rate: 1 }
      : { passed: 0, total: 1, rate: 0 };
  }
  let passed = 0;
  let total = 0;
  for (let i = 0; i < step.children.length; i++) {
    const child = step.children[i];
    const inner = subtreeCompletion(child, [...prefix, i], alignment);
    passed += inner.passed;
    total += inner.total;
  }
  return { passed, total, rate: total === 0 ? null : passed / total };
}

export function formatRate(rate) {
  if (rate === null || rate === undefined || Number.isNaN(rate)) return "—";
  return `${Math.round(rate * 100)}%`;
}

// "1:23" / "1:23.4" style formatting for a video timestamp in seconds.
export function formatTimestamp(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return null;
  const total = Math.max(0, Number(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const wholeSecs = Math.floor(total % 60);
  const decimal = Math.floor((total - Math.floor(total)) * 10);
  const mm = String(minutes).padStart(hours > 0 ? 2 : 1, "0");
  const ss = String(wholeSecs).padStart(2, "0");
  const head = hours > 0 ? `${hours}:${mm}` : mm;
  const tail = decimal > 0 ? `${ss}.${decimal}` : ss;
  return `${head}:${tail}`;
}
