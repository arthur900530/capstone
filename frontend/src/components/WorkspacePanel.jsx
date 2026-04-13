import { useState, useEffect, useCallback } from "react";
import {
  FolderTree,
  RefreshCw,
  PanelRightClose,
  Search,
} from "lucide-react";
import FileTreeNode from "./FileTreeNode";
import { fetchWorkspaceTree } from "../services/api";

export default function WorkspacePanel({
  mountDir,
  activeFile,
  modifiedFiles,
  onSelectFile,
  onClose,
  refreshTrigger = 0,
}) {
  const [tree, setTree] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("");

  const loadTree = useCallback(async () => {
    if (!mountDir) return;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchWorkspaceTree(mountDir);
      setTree(data.tree || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [mountDir]);

  useEffect(() => {
    loadTree();
  }, [loadTree, refreshTrigger]);

  const filterTree = (nodes, query) => {
    if (!query) return nodes;
    const q = query.toLowerCase();
    return nodes
      .map((node) => {
        if (node.type === "directory") {
          const filtered = filterTree(node.children || [], q);
          if (filtered.length > 0 || node.name.toLowerCase().includes(q)) {
            return { ...node, children: filtered };
          }
          return null;
        }
        if (node.name.toLowerCase().includes(q)) return node;
        return null;
      })
      .filter(Boolean);
  };

  const displayTree = filterTree(tree, filter);
  const rootName = mountDir?.split("/").pop() || "workspace";

  return (
    <aside className="flex h-full w-[260px] shrink-0 flex-col border-l border-border/30 bg-charcoal">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-border/30 px-3 py-2.5">
        <FolderTree size={14} className="text-accent-teal" />
        <span className="flex-1 truncate text-xs font-semibold text-text-primary">
          {rootName}
        </span>
        <button
          onClick={loadTree}
          className="rounded p-1 text-text-muted transition-colors hover:bg-surface-hover hover:text-text-secondary"
          title="Refresh"
        >
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
        </button>
        <button
          onClick={onClose}
          className="rounded p-1 text-text-muted transition-colors hover:bg-surface-hover hover:text-text-secondary"
          title="Close panel"
        >
          <PanelRightClose size={13} />
        </button>
      </div>

      {/* Search filter */}
      <div className="border-b border-border/20 px-2 py-1.5">
        <div className="flex items-center gap-1.5 rounded-md bg-surface px-2 py-1">
          <Search size={12} className="text-text-muted" />
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter files..."
            className="flex-1 bg-transparent text-[11px] text-text-primary outline-none placeholder:text-text-muted"
          />
        </div>
      </div>

      {/* Tree */}
      <div className="flex-1 overflow-y-auto px-1 py-1">
        {error && (
          <div className="px-2 py-3 text-xs text-red-400">{error}</div>
        )}
        {!error && displayTree.length === 0 && !loading && (
          <div className="px-2 py-3 text-xs text-text-muted">
            {filter ? "No matching files" : "Empty workspace"}
          </div>
        )}
        {displayTree.map((node) => (
          <FileTreeNode
            key={node.path}
            node={node}
            depth={0}
            activeFile={activeFile}
            modifiedFiles={modifiedFiles}
            onSelectFile={onSelectFile}
          />
        ))}
      </div>

      {/* Footer: file count */}
      <div className="border-t border-border/20 px-3 py-1.5 text-[10px] text-text-muted">
        {countFiles(tree)} files
      </div>
    </aside>
  );
}

function countFiles(nodes) {
  let count = 0;
  for (const n of nodes) {
    if (n.type === "file") count++;
    else if (n.children) count += countFiles(n.children);
  }
  return count;
}
