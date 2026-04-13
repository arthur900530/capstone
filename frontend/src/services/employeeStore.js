/**
 * localStorage CRUD for employee entities.
 * No backend persistence — this is a frontend-only store.
 */

const STORAGE_KEY = "digital_employees";

function readAll() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || [];
  } catch {
    return [];
  }
}

function writeAll(employees) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(employees));
}

const ACTIVE_THRESHOLD_MS = 10 * 60 * 1000; // 10 minutes

function deriveStatus(emp) {
  if (emp.lastActiveAt) {
    const elapsed = Date.now() - new Date(emp.lastActiveAt).getTime();
    return elapsed < ACTIVE_THRESHOLD_MS ? "active" : "idle";
  }
  return "idle";
}

export function getEmployees() {
  return readAll().map((e) => ({ ...e, status: deriveStatus(e) }));
}

export function getEmployeeById(id) {
  const emp = readAll().find((e) => e.id === id);
  return emp ? { ...emp, status: deriveStatus(emp) } : null;
}

export function markActive(id) {
  updateEmployee(id, { lastActiveAt: new Date().toISOString() });
}

export function createEmployee({
  name,
  task,
  pluginId,
  skillIds,
  model,
  useReflexion = false,
  maxTrials = 3,
  confidenceThreshold = 0.7,
  files = [],
}) {
  const employee = {
    id: crypto.randomUUID(),
    name,
    task,
    pluginId,
    skillIds,
    model,
    useReflexion,
    maxTrials,
    confidenceThreshold,
    status: "idle",
    chatSessionIds: [],
    files,
    createdAt: new Date().toISOString(),
  };
  const all = readAll();
  all.push(employee);
  writeAll(all);
  return employee;
}

export function updateEmployee(id, updates) {
  const all = readAll();
  const idx = all.findIndex((e) => e.id === id);
  if (idx === -1) return null;
  all[idx] = { ...all[idx], ...updates };
  writeAll(all);
  return all[idx];
}

export function deleteEmployee(id) {
  const all = readAll();
  writeAll(all.filter((e) => e.id !== id));
}

export function addChatSession(employeeId, sessionId) {
  const all = readAll();
  const emp = all.find((e) => e.id === employeeId);
  if (!emp) return;
  if (!emp.chatSessionIds.includes(sessionId)) {
    emp.chatSessionIds.push(sessionId);
    writeAll(all);
  }
}
