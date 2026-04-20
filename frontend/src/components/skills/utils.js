import {
  BookOpen,
  Scale,
  FileText,
  FileCode,
  Code,
  File,
} from "lucide-react";

export function fileIcon(name) {
  const lower = name.toLowerCase();
  if (lower === "skill.md") return { Icon: BookOpen, color: "text-accent-teal" };
  if (lower === "license") return { Icon: Scale, color: "text-yellow-500" };
  if (lower.endsWith(".md")) return { Icon: FileText, color: "text-blue-400" };
  if (lower.endsWith(".py") || lower.endsWith(".sh")) return { Icon: FileCode, color: "text-green-400" };
  if (lower.endsWith(".json") || lower.endsWith(".yaml") || lower.endsWith(".yml")) return { Icon: Code, color: "text-orange-400" };
  if (lower.endsWith(".csv")) return { Icon: FileText, color: "text-purple-400" };
  return { Icon: File, color: "text-text-muted" };
}

export function isMonoFile(name) {
  const lower = name.toLowerCase();
  return (
    lower.endsWith(".json") ||
    lower.endsWith(".yaml") ||
    lower.endsWith(".yml") ||
    lower.endsWith(".csv") ||
    lower.endsWith(".py") ||
    lower.endsWith(".sh")
  );
}
