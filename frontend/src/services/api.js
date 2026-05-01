const API_BASE = "/api";

export async function fetchAgentSkills() {
  const res = await fetch(`${API_BASE}/agent-skills`);
  if (!res.ok) throw new Error(`Failed to load agent skills: ${res.status}`);
  return res.json();
}

export async function fetchSkillEvals() {
  const res = await fetch(`${API_BASE}/skill-evals`);
  if (!res.ok) throw new Error(`Failed to load skill evals: ${res.status}`);
  return res.json();
}

export async function runSkillEval(agentId) {
  const res = await fetch(
    `${API_BASE}/skill-evals/run?agent_id=${encodeURIComponent(agentId)}`,
    { method: "POST" },
  );
  if (!res.ok) throw new Error(`Failed to run skill eval: ${res.status}`);
  return res.json();
}

export async function fetchEvaluations() {
  const res = await fetch(`${API_BASE}/evaluations`);
  if (!res.ok) throw new Error(`Failed to load evaluations: ${res.status}`);
  return res.json();
}

export async function fetchChats() {
  const res = await fetch(`${API_BASE}/chats`);
  if (!res.ok) throw new Error(`Failed to load chats: ${res.status}`);
  return res.json();
}

export async function fetchChatById(chatId) {
  const res = await fetch(`${API_BASE}/chats/${chatId}`);
  if (!res.ok) throw new Error(`Failed to load chat: ${res.status}`);
  return res.json();
}

export async function renameChat(chatId, name) {
  const res = await fetch(`${API_BASE}/chats/${chatId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error(`Failed to rename chat: ${res.status}`);
  return res.json();
}

export async function deleteChat(chatId) {
  const res = await fetch(`${API_BASE}/chats/${chatId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Failed to delete chat: ${res.status}`);
  return res.json();
}

export async function fetchEmployeeMetrics(employeeId, { limit } = {}) {
  const query = Number.isFinite(limit) ? `?limit=${encodeURIComponent(limit)}` : "";
  const res = await fetch(`${API_BASE}/employees/${employeeId}/metrics${query}`);
  if (!res.ok) throw new Error(`Failed to load employee metrics: ${res.status}`);
  return res.json();
}

export async function backfillRecentAnnotations(
  employeeId,
  { limit, force = false } = {},
) {
  const params = new URLSearchParams();
  if (Number.isFinite(limit)) params.set("limit", String(limit));
  if (force) params.set("force", "true");
  const query = params.toString() ? `?${params.toString()}` : "";
  const res = await fetch(
    `${API_BASE}/employees/${employeeId}/task_runs/annotate_recent${query}`,
    { method: "POST" },
  );
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const body = await res.json();
      detail = body?.detail || detail;
    } catch {
      // keep default
    }
    throw new Error(`Failed to backfill annotations: ${detail}`);
  }
  return res.json();
}

export async function fetchTaskTrajectory(employeeId, sessionId, taskIndex) {
  const res = await fetch(
    `${API_BASE}/employees/${employeeId}/task_runs/${encodeURIComponent(sessionId)}/${encodeURIComponent(taskIndex)}/trajectory`,
  );
  if (res.status === 410) {
    const body = await res.json();
    return body?.detail || body;
  }
  if (!res.ok) throw new Error(`Failed to load task trajectory: ${res.status}`);
  return res.json();
}

export async function rateTaskRun(employeeId, sessionId, taskIndex, rating) {
  const res = await fetch(
    `${API_BASE}/employees/${employeeId}/task_runs/${encodeURIComponent(sessionId)}/${encodeURIComponent(taskIndex)}/rating`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rating }),
    },
  );
  if (res.status === 404) {
    const err = new Error("Task run not yet persisted");
    err.code = "TASK_RUN_NOT_FOUND";
    throw err;
  }
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const body = await res.json();
      detail = body?.detail || detail;
    } catch {
      // keep default
    }
    throw new Error(`Failed to save rating: ${detail}`);
  }
  return res.json();
}

export async function annotateTaskTrajectory(employeeId, sessionId, taskIndex, { force = false } = {}) {
  const query = force ? "?force=true" : "";
  const res = await fetch(
    `${API_BASE}/employees/${employeeId}/task_runs/${encodeURIComponent(sessionId)}/${encodeURIComponent(taskIndex)}/trajectory/annotate${query}`,
    { method: "POST" },
  );
  if (res.status === 410) {
    const body = await res.json();
    return body?.detail || body;
  }
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const body = await res.json();
      detail = body?.detail || detail;
    } catch {
      // keep default
    }
    throw new Error(`Failed to annotate trajectory: ${detail}`);
  }
  return res.json();
}

export async function fetchAgents() {
  const res = await fetch(`${API_BASE}/agents`);
  if (!res.ok) throw new Error(`Failed to load agents: ${res.status}`);
  return res.json();
}

export async function fetchSkills() {
  const res = await fetch(`${API_BASE}/skills`);
  if (!res.ok) throw new Error(`Failed to load skills: ${res.status}`);
  return res.json();
}

export async function suggestEmployeeSkills(description) {
  const res = await fetch(`${API_BASE}/employees/suggest-skills`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ description }),
  });
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const body = await res.json();
      detail = body?.detail || detail;
    } catch {
      // keep default
    }
    throw new Error(`Failed to suggest skills: ${detail}`);
  }
  return res.json();
}

export async function fetchSkillById(skillId) {
  const res = await fetch(`${API_BASE}/skills/${skillId}`);
  if (!res.ok) throw new Error(`Failed to load skill: ${res.status}`);
  return res.json();
}

export async function createSkill({ name, description, definition, files }) {
  const res = await fetch(`${API_BASE}/skills`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description, definition, files }),
  });
  if (!res.ok) throw new Error(`Failed to create skill: ${res.status}`);
  return res.json();
}

export async function updateSkill(skillId, { name, description, definition }) {
  const res = await fetch(`${API_BASE}/skills/${skillId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description, definition }),
  });
  if (!res.ok) throw new Error(`Failed to update skill: ${res.status}`);
  return res.json();
}

export async function addSkillFiles(skillId, files) {
  const res = await fetch(`${API_BASE}/skills/${skillId}/files`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(files),
  });
  if (!res.ok) throw new Error(`Failed to add files: ${res.status}`);
  return res.json();
}

export async function removeSkillFile(skillId, filename) {
  const res = await fetch(
    `${API_BASE}/skills/${skillId}/files/${encodeURIComponent(filename)}`,
    {
      method: "DELETE",
    },
  );
  if (!res.ok) throw new Error(`Failed to remove file: ${res.status}`);
  return res.json();
}

export async function fetchSkillFileContent(skillId, filename) {
  const res = await fetch(
    `${API_BASE}/skills/${skillId}/files/${encodeURIComponent(filename)}`,
  );
  if (!res.ok) throw new Error(`Failed to load file: ${res.status}`);
  return res.json();
}

export async function deleteSkill(skillId) {
  const res = await fetch(`${API_BASE}/skills/${skillId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`Failed to delete skill: ${res.status}`);
  return res.json();
}

export async function trainSkillsFromMedia(files) {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  const res = await fetch(`${API_BASE}/skills/train`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Training failed: ${text}`);
  }
  return res.json();
}

export async function uploadFiles(sessionId, files) {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  const url = sessionId
    ? `${API_BASE}/upload?session_id=${encodeURIComponent(sessionId)}`
    : `${API_BASE}/upload`;
  const res = await fetch(url, { method: "POST", body: form });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Upload failed: ${text}`);
  }
  return res.json();
}

export async function streamChat(
  {
    question,
    sessionId,
    model,
    maxTrials,
    confidenceThreshold,
    useReflexion,
    files,
    skillIds,
    mountDir,
    employeeId,
    employee,
  },
  onEvent,
) {
  // Only forward employee persona fields that are actually set so the backend
  // never sees a payload like {name: undefined, position: "", task: ""}.
  // The backend prefers its own DB lookup via employee_id; this client-side
  // copy is a fallback for DB-less setups.
  const employeePayload = employee
    ? Object.fromEntries(
        Object.entries({
          name: employee.name,
          position: employee.position,
          task: employee.task,
        }).filter(([, v]) => typeof v === "string" && v.trim() !== ""),
      )
    : null;

  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      session_id: sessionId || undefined,
      model: model || undefined,
      max_trials: maxTrials,
      confidence_threshold: confidenceThreshold,
      use_reflexion: useReflexion ?? false,
      files: files || undefined,
      skill_ids: skillIds?.length ? skillIds : undefined,
      mount_dir: mountDir || undefined,
      employee_id: employeeId || undefined,
      employee:
        employeePayload && Object.keys(employeePayload).length > 0
          ? employeePayload
          : undefined,
    }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent = "message";
  const terminalEvents = new Set(["done", "answer", "chat_response", "error"]);

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("event:")) {
        currentEvent = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        const raw = line.slice(5).trim();
        if (!raw) continue;
        try {
          const data = JSON.parse(raw);
          onEvent(currentEvent, data);
        } catch {
          onEvent(currentEvent, { text: raw });
        }
        if (terminalEvents.has(currentEvent)) {
          await reader.cancel();
          return;
        }
        currentEvent = "message";
      }
    }
  }
}


// ── Marketplace APIs ─────────────────────────────────────────────────────────

export async function browseMarketplaceSkills(params = {}) {
  const qs = new URLSearchParams();
  if (params.q) qs.set("q", params.q);
  if (params.status) qs.set("status", params.status);
  if (params.source_type) qs.set("source_type", params.source_type);
  if (params.tag) qs.set("tag", params.tag);
  if (params.page) qs.set("page", params.page);
  const url = `${API_BASE}/marketplace/skills${qs.toString() ? "?" + qs : ""}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to browse marketplace: ${res.status}`);
  return res.json();
}

export async function getMarketplaceSkill(slug) {
  const res = await fetch(`${API_BASE}/marketplace/skills/${slug}`);
  if (!res.ok) throw new Error(`Failed to load marketplace skill: ${res.status}`);
  return res.json();
}

export async function installSkill(slug) {
  const res = await fetch(`${API_BASE}/marketplace/skills/${slug}/install`, { method: "POST" });
  if (!res.ok) throw new Error(`Failed to install skill: ${res.status}`);
  return res.json();
}

export async function uninstallSkill(slug) {
  const res = await fetch(`${API_BASE}/marketplace/skills/${slug}/uninstall`, { method: "POST" });
  if (!res.ok) throw new Error(`Failed to uninstall skill: ${res.status}`);
  return res.json();
}

export async function createSubmission({ name, description, skill_md, submission_type }) {
  const res = await fetch(`${API_BASE}/marketplace/submissions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description, skill_md, submission_type }),
  });
  if (!res.ok) throw new Error(`Failed to create submission: ${res.status}`);
  return res.json();
}

export async function fetchSubmissions(status) {
  const qs = status ? `?status=${status}` : "";
  const res = await fetch(`${API_BASE}/marketplace/submissions${qs}`);
  if (!res.ok) throw new Error(`Failed to load submissions: ${res.status}`);
  return res.json();
}

export async function getSubmission(submissionId) {
  const res = await fetch(`${API_BASE}/marketplace/submissions/${submissionId}`);
  if (!res.ok) throw new Error(`Failed to load submission: ${res.status}`);
  return res.json();
}

export async function reviewSubmission(submissionId, { decision, reason }) {
  const res = await fetch(`${API_BASE}/marketplace/submissions/${submissionId}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, reason }),
  });
  if (!res.ok) throw new Error(`Failed to submit decision: ${res.status}`);
  return res.json();
}

export async function deleteSubmission(submissionId) {
  const res = await fetch(`${API_BASE}/marketplace/submissions/${submissionId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Failed to delete submission: ${res.status}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Employee project files
// ---------------------------------------------------------------------------
// Project files are attached to an employee (not a chat session) and get
// staged into the agent's workspace at the start of every turn. They are
// distinct from chat-uploaded files, which are one-shot per session.

export async function listProjectFiles(employeeId) {
  const res = await fetch(
    `${API_BASE}/employees/${encodeURIComponent(employeeId)}/project_files`,
  );
  if (!res.ok) throw new Error(`Failed to load project files: ${res.status}`);
  return res.json();
}

export async function uploadProjectFiles(employeeId, files) {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  const res = await fetch(
    `${API_BASE}/employees/${encodeURIComponent(employeeId)}/project_files`,
    { method: "POST", body: form },
  );
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const body = await res.json();
      detail = body?.detail || detail;
    } catch {
      // keep default
    }
    throw new Error(`Upload failed: ${detail}`);
  }
  return res.json();
}

export async function deleteProjectFile(employeeId, fileId) {
  const res = await fetch(
    `${API_BASE}/employees/${encodeURIComponent(employeeId)}/project_files/${encodeURIComponent(fileId)}`,
    { method: "DELETE" },
  );
  if (!res.ok) throw new Error(`Failed to delete project file: ${res.status}`);
  return res.json();
}

export function projectFileRawUrl(employeeId, fileId) {
  return `${API_BASE}/employees/${encodeURIComponent(employeeId)}/project_files/${encodeURIComponent(fileId)}/raw`;
}

async function _extractDetail(res, fallback) {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
    if (typeof body?.detail === "object") return JSON.stringify(body.detail);
  } catch {
    // ignore parse errors
  }
  return `${fallback} (HTTP ${res.status})`;
}

export async function getAutoTestsConfig() {
  const res = await fetch(`${API_BASE}/employees/auto_tests_config`);
  if (!res.ok) throw new Error(await _extractDetail(res, "Failed to load auto-tests config"));
  return res.json();
}

/** Omit ``count`` to use ``TEST_SUITE_GENERATION_COUNT`` from ``backend/config.py``. */
export async function generateTestCases(employeeId, count) {
  const path = `${API_BASE}/employees/${encodeURIComponent(employeeId)}/test_cases/generate`;
  const url =
    count === undefined || count === null
      ? path
      : `${path}?count=${encodeURIComponent(count)}`;
  const res = await fetch(url, { method: "POST" });
  if (!res.ok) throw new Error(await _extractDetail(res, "Failed to generate test cases"));
  return res.json();
}

export async function listTestCases(employeeId) {
  const res = await fetch(
    `${API_BASE}/employees/${encodeURIComponent(employeeId)}/test_cases`,
  );
  if (!res.ok) throw new Error(await _extractDetail(res, "Failed to load test cases"));
  return res.json();
}

export async function updateTestCase(employeeId, caseId, updates) {
  const res = await fetch(
    `${API_BASE}/employees/${encodeURIComponent(employeeId)}/test_cases/${encodeURIComponent(caseId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    },
  );
  if (!res.ok) throw new Error(await _extractDetail(res, "Failed to update test case"));
  return res.json();
}

export async function deleteTestCase(employeeId, caseId) {
  const res = await fetch(
    `${API_BASE}/employees/${encodeURIComponent(employeeId)}/test_cases/${encodeURIComponent(caseId)}`,
    { method: "DELETE" },
  );
  if (!res.ok) throw new Error(await _extractDetail(res, "Failed to delete test case"));
  return res.json();
}

export async function deleteTestSuite(employeeId) {
  const res = await fetch(
    `${API_BASE}/employees/${encodeURIComponent(employeeId)}/test_cases`,
    { method: "DELETE" },
  );
  if (!res.ok) throw new Error(await _extractDetail(res, "Failed to delete test suite"));
  return res.json();
}

export async function runTestCase(employeeId, caseId) {
  const res = await fetch(
    `${API_BASE}/employees/${encodeURIComponent(employeeId)}/test_cases/${encodeURIComponent(caseId)}/run`,
    { method: "POST" },
  );
  if (!res.ok) throw new Error(await _extractDetail(res, "Failed to run test case"));
  return res.json();
}

export async function runAllTestCases(employeeId) {
  const res = await fetch(
    `${API_BASE}/employees/${encodeURIComponent(employeeId)}/test_cases/run_all`,
    { method: "POST" },
  );
  if (!res.ok) throw new Error(await _extractDetail(res, "Failed to run all test cases"));
  return res.json();
}

export async function listTestCaseRuns(employeeId, caseId) {
  const res = await fetch(
    `${API_BASE}/employees/${encodeURIComponent(employeeId)}/test_cases/${encodeURIComponent(caseId)}/runs`,
  );
  if (!res.ok) throw new Error(await _extractDetail(res, "Failed to load test case runs"));
  return res.json();
}

// Memory-only: backend keeps the captured agent event stream for each
// test-case run in a process-local dict. After a server restart the events
// for older runs are gone — the response will have `available: false` and
// an empty list, which the drawer renders as a friendly empty state.
export async function fetchTestCaseRunEvents(employeeId, caseId, runId) {
  const res = await fetch(
    `${API_BASE}/employees/${encodeURIComponent(employeeId)}/test_cases/${encodeURIComponent(caseId)}/runs/${encodeURIComponent(runId)}/events`,
  );
  if (!res.ok) throw new Error(await _extractDetail(res, "Failed to load run events"));
  return res.json();
}

// Fetch the JSON export for a single test case (case + run history).
// The backend includes the in-memory event stream only when
// `includeEvents` is true; default off to keep payloads small.
export async function exportTestCase(employeeId, caseId, { includeEvents = false } = {}) {
  const query = includeEvents ? "?include_events=true" : "";
  const res = await fetch(
    `${API_BASE}/employees/${encodeURIComponent(employeeId)}/test_cases/${encodeURIComponent(caseId)}/export${query}`,
  );
  if (!res.ok) throw new Error(await _extractDetail(res, "Failed to export test case"));
  return res.json();
}

// Fetch the JSON export for the entire test suite of an employee.
export async function exportTestSuite(employeeId, { includeEvents = false } = {}) {
  const query = includeEvents ? "?include_events=true" : "";
  const res = await fetch(
    `${API_BASE}/employees/${encodeURIComponent(employeeId)}/test_cases/export${query}`,
  );
  if (!res.ok) throw new Error(await _extractDetail(res, "Failed to export test suite"));
  return res.json();
}

// ---------------------------------------------------------------------------
// Workspace browsing
// ---------------------------------------------------------------------------

export async function fetchWorkspaceTree(dirPath) {
  const res = await fetch(
    `${API_BASE}/workspace/tree?path=${encodeURIComponent(dirPath)}`,
  );
  if (!res.ok) throw new Error(`Failed to load workspace tree: ${res.status}`);
  return res.json();
}

export async function fetchWorkspaceFile(rootDir, filePath) {
  const res = await fetch(
    `${API_BASE}/workspace/file?root=${encodeURIComponent(rootDir)}&path=${encodeURIComponent(filePath)}`,
  );
  if (!res.ok) throw new Error(`Failed to load file: ${res.status}`);
  return res.json();
}

export function workspaceRawUrl(rootDir, filePath) {
  return `${API_BASE}/workspace/raw?root=${encodeURIComponent(rootDir)}&path=${encodeURIComponent(filePath)}`;
}

// Opens the host OS's native folder picker dialog via the backend. Only
// meaningful when the backend runs on the same machine as the user.
// Resolves to { path: string | null, cancelled: boolean, platform: string }.
export async function pickWorkspaceDirectory() {
  const res = await fetch(`${API_BASE}/workspace/pick-directory`, {
    method: "POST",
  });
  if (!res.ok) {
    let detail = `Failed to open folder picker: ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      // ignore JSON parse errors
    }
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

