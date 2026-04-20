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
  },
  onEvent,
) {
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

