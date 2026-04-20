import { useState } from "react";
import { Wrench, Paperclip, ChevronDown, ChevronRight } from "lucide-react";
import { fileIcon } from "./utils";

export default function SkillListItem({ skill, isSelected, onSelect, onFileClick }) {
  const [expanded, setExpanded] = useState(false);
  const files = skill.files ?? [];

  const handleClick = () => {
    onSelect(skill.id);
    if (files.length > 0) setExpanded((v) => !v);
  };

  return (
    <li>
      <button
        onClick={handleClick}
        className={`flex w-full items-start gap-2 rounded-lg px-3 py-2.5 text-left transition-colors ${
          isSelected
            ? "bg-surface text-text-primary"
            : "text-text-secondary hover:bg-surface/50 hover:text-text-primary"
        }`}
      >
        <div className="mt-0.5 shrink-0 rounded-md p-1.5 bg-accent-teal/10 text-accent-teal">
          <Wrench size={13} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{skill.name}</p>
          <p className="mt-0.5 truncate text-[11px] text-text-muted">{skill.id}</p>
        </div>
        {files.length > 0 && (
          <div className="mt-0.5 flex shrink-0 items-center gap-0.5 text-text-muted">
            <Paperclip size={11} />
            <span className="text-[10px]">{files.length}</span>
            {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </div>
        )}
      </button>

      {expanded && files.length > 0 && (
        <div className="mb-1 ml-[42px] mr-2 rounded-md border border-border/30 bg-charcoal/50">
          {files.map((file, i) => {
            const { Icon, color } = fileIcon(file.name);
            return (
              <button
                key={file.name}
                onClick={() => onFileClick(skill.id, file.name)}
                className={`flex w-full items-center gap-2 px-2.5 py-1.5 text-left transition-colors hover:bg-surface/60 ${
                  i > 0 ? "border-t border-border/20" : ""
                }`}
              >
                <Icon size={11} className={`shrink-0 ${color}`} />
                <span
                  className={`min-w-0 flex-1 truncate text-[11px] ${
                    file.name === "SKILL.md"
                      ? "font-medium text-accent-teal"
                      : file.name === "LICENSE"
                        ? "text-yellow-500/80"
                        : "text-text-secondary"
                  }`}
                >
                  {file.name}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </li>
  );
}
