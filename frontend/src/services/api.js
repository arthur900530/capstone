const API_BASE = "/api";

export async function fetchEvaluations() {
  const res = await fetch(`${API_BASE}/evaluations`);
  if (!res.ok) throw new Error(`Failed to load evaluations: ${res.status}`);
  return res.json();
}

export async function fetchSkillEvals() {
  const res = await fetch(`${API_BASE}/skill-evals`);
  if (!res.ok) throw new Error(`Failed to load skill evals: ${res.status}`);
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
  const res = await fetch(`${API_BASE}/skills/${skillId}/files/${encodeURIComponent(filename)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`Failed to remove file: ${res.status}`);
  return res.json();
}

export async function fetchSkillFileContent(skillId, filename) {
  const res = await fetch(`${API_BASE}/skills/${skillId}/files/${encodeURIComponent(filename)}`);
  if (!res.ok) throw new Error(`Failed to load file: ${res.status}`);
  return res.json();
}

export async function deleteSkill(skillId) {
  const res = await fetch(`${API_BASE}/skills/${skillId}`, { method: "DELETE" });
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

export async function streamChat({ question, sessionId, model, maxTrials, confidenceThreshold, files, skillIds }, onEvent) {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      session_id: sessionId || undefined,
      model: model || undefined,
      max_trials: maxTrials,
      confidence_threshold: confidenceThreshold,
      files: files || undefined,
      skill_ids: skillIds?.length ? skillIds : undefined,
    }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    let currentEvent = "message";
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
        currentEvent = "message";
      }
    }
  }
}
