/**
 * Employee CRUD — backed by /api/employees.
 * All functions are async since they hit the backend.
 */

const API = "/api/employees";

export async function getEmployees() {
  try {
    const res = await fetch(API);
    if (!res.ok) throw new Error();
    return await res.json();
  } catch {
    return [];
  }
}

export async function getEmployeeById(id) {
  try {
    const res = await fetch(`${API}/${id}`);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function createEmployee({
  name,
  position = "",
  description = "",
  pluginIds = [],
  skillIds,
  model,
  useReflexion = false,
  maxTrials = 3,
  confidenceThreshold = 0.7,
}) {
  // The wizard sends a short ``description``; the backend expands it into
  // the full system prompt (``task``) via an LLM call. We intentionally don't
  // send ``task`` from the client so the generation is fire-and-forget.
  const res = await fetch(API, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name,
      position,
      description,
      pluginIds,
      skillIds,
      model,
      useReflexion,
      maxTrials,
      confidenceThreshold,
    }),
  });
  if (!res.ok) {
    let detail = `Failed to create employee (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* keep default */
    }
    throw new Error(detail);
  }
  return await res.json();
}

export async function updateEmployee(id, updates) {
  const res = await fetch(`${API}/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  if (!res.ok) return null;
  return await res.json();
}

export async function deleteEmployee(id) {
  await fetch(`${API}/${id}`, { method: "DELETE" });
}

export async function addChatSession(employeeId, sessionId) {
  try {
    const emp = await getEmployeeById(employeeId);
    if (!emp) return;
    const ids = emp.chatSessionIds || [];
    if (!ids.includes(sessionId)) {
      await updateEmployee(employeeId, {
        chatSessionIds: [...ids, sessionId],
      });
    }
  } catch {
    /* best-effort */
  }
}

export async function markActive(id) {
  await updateEmployee(id, { lastActiveAt: new Date().toISOString() });
}
