import { useState } from "react";
import {
  ChevronRight,
  ChevronDown,
  FileCode2,
  FileText,
  FileJson,
  File,
  Folder,
  FolderOpen,
} from "lucide-react";

function getFileIconType(name) {
  const ext = name.split(".").pop()?.toLowerCase();
  if (["py", "js", "jsx", "ts", "tsx"].includes(ext)) return "code";
  if (ext === "json") return "json";
  if (["md", "txt", "csv", "log"].includes(ext)) return "text";
  return "file";
}

function FileNodeIcon({ name, className }) {
  const type = getFileIconType(name);
  if (type === "code") return <FileCode2 size={14} className={className} />;
  if (type === "json") return <FileJson size={14} className={className} />;
  if (type === "text") return <FileText size={14} className={className} />;
  return <File size={14} className={className} />;
}

export default function FileTreeNode({
  node,
  depth = 0,
  activeFile,
  modifiedFiles,
  onSelectFile,
}) {
  const [expanded, setExpanded] = useState(depth < 2);
  const isDir = node.type === "directory";
  const isActive = !isDir && node.path === activeFile;
  const isModified = modifiedFiles?.has(node.path);

  const handleClick = () => {
    if (isDir) {
      setExpanded((v) => !v);
    } else {
      onSelectFile?.(node.path);
    }
  };

  return (
    <div>
      <button
        onClick={handleClick}
        className={`
          group flex w-full items-center gap-1.5 rounded-md px-2 py-[5px] text-left text-[12px] transition-colors
          ${isActive
            ? "bg-accent-teal/15 text-accent-light"
            : "text-text-secondary hover:bg-surface-hover hover:text-text-primary"
          }
        `}
        style={{ paddingLeft: `${depth * 14 + 8}px` }}
      >
        {/* Chevron for directories */}
        {isDir ? (
          expanded ? (
            <ChevronDown size={12} className="shrink-0 text-text-muted" />
          ) : (
            <ChevronRight size={12} className="shrink-0 text-text-muted" />
          )
        ) : (
          <span className="w-3 shrink-0" />
        )}

        {/* File/folder icon */}
        {isDir ? (
          expanded ? (
            <FolderOpen size={14} className="shrink-0 text-amber-400/70" />
          ) : (
            <Folder size={14} className="shrink-0 text-amber-400/70" />
          )
        ) : (
          <FileNodeIcon
            name={node.name}
            className={`shrink-0 ${isActive ? "text-accent-teal" : "text-text-muted"}`}
          />
        )}

        {/* Name */}
        <span className="flex-1 truncate">{node.name}</span>

        {/* Modified indicator */}
        {isModified && (
          <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400 animate-pulse" />
        )}
      </button>

      {/* Children */}
      {isDir && expanded && node.children?.length > 0 && (
        <div>
          {node.children.map((child) => (
            <FileTreeNode
              key={child.path}
              node={child}
              depth={depth + 1}
              activeFile={activeFile}
              modifiedFiles={modifiedFiles}
              onSelectFile={onSelectFile}
            />
          ))}
        </div>
      )}
    </div>
  );
}
