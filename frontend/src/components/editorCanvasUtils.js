const MARKDOWN_EXTS = new Set(["md", "markdown", "mdown", "mkd"]);
const IMAGE_EXTS = new Set(["png", "jpg", "jpeg", "gif", "bmp", "webp", "svg", "ico"]);
const TEXT_EXTS = new Set([
  "txt", "log", "csv", "tsv",
  "py", "js", "jsx", "ts", "tsx", "mjs", "cjs",
  "json", "yml", "yaml", "toml", "ini", "cfg", "env",
  "sh", "bash", "zsh", "fish",
  "css", "scss", "less", "html", "htm", "xml", "svg",
  "sql", "rs", "go", "java", "kt", "swift",
  "c", "cc", "cpp", "h", "hpp", "rb", "lua", "r", "php", "pl",
  "dockerfile", "makefile", "gitignore",
]);

const AUTO_OPEN_IGNORED_BASENAMES = new Set([
  "TASKS.json",
  "TASKS.md",
  "reflexion_memory.json",
  "base_state.json",
]);
const AUTO_OPEN_IGNORED_SEGMENTS = new Set([
  "subagents",
  "events",
  "conversations",
]);
const AUTO_OPEN_IGNORED_BASENAME_PATTERNS = [
  /^event-\d{5}-[0-9a-fA-F-]{8,}\.json$/,
];
const AUTO_OPEN_IGNORED_SEGMENT_SUBSTRINGS = ["tmp"];

function getExt(path) {
  if (!path) return "";
  const name = path.split("/").pop() || "";
  const lower = name.toLowerCase();
  if (!lower.includes(".")) return lower;
  return lower.split(".").pop() || "";
}

function basenameOf(path) {
  if (!path) return "";
  return path.split("/").pop() || "";
}

function isAgentInternalPath(path) {
  if (!path) return false;
  const base = basenameOf(path);
  if (AUTO_OPEN_IGNORED_BASENAMES.has(base)) return true;
  if (AUTO_OPEN_IGNORED_BASENAME_PATTERNS.some((re) => re.test(base))) return true;
  const parts = path.split("/");
  for (let i = 0; i < parts.length - 1; i++) {
    if (AUTO_OPEN_IGNORED_SEGMENTS.has(parts[i])) return true;
  }
  for (const part of parts) {
    if (!part) continue;
    const lower = part.toLowerCase();
    if (AUTO_OPEN_IGNORED_SEGMENT_SUBSTRINGS.some((tok) => lower.includes(tok))) {
      return true;
    }
  }
  return false;
}

export function isCanvasPreviewable(path) {
  if (isAgentInternalPath(path)) return false;
  const ext = getExt(path);
  if (!ext) return false;
  if (ext === "pdf") return true;
  if (MARKDOWN_EXTS.has(ext)) return true;
  if (IMAGE_EXTS.has(ext)) return true;
  if (TEXT_EXTS.has(ext)) return true;
  return false;
}
