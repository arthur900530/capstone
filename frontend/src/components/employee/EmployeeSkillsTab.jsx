import { useState } from "react";
import { X, Plus } from "lucide-react";
import { updateEmployee } from "../../services/employeeStore";
import { useApp } from "../../context/appContextCore";
import SkillBrowser from "../skills/SkillBrowser";

export default function EmployeeSkillsTab({ employee, onEmployeeUpdated }) {
  const { refreshSkills } = useApp();
  const [skillIds, setSkillIds] = useState(employee.skillIds || []);
  const [newSkillInput, setNewSkillInput] = useState("");
  const [saving, setSaving] = useState(false);

  const persistSkills = async (nextIds) => {
    setSkillIds(nextIds);
    setSaving(true);
    try {
      const updated = await updateEmployee(employee.id, { skillIds: nextIds });
      if (updated) onEmployeeUpdated(updated);
    } finally {
      setSaving(false);
    }
  };

  const toggleSkill = (sid) => {
    const nextIds = skillIds.includes(sid)
      ? skillIds.filter((s) => s !== sid)
      : [...skillIds, sid];
    persistSkills(nextIds);
  };

  const addCustomSkill = () => {
    const trimmed = newSkillInput.trim();
    if (trimmed && !skillIds.includes(trimmed)) {
      persistSkills([...skillIds, trimmed]);
      setNewSkillInput("");
    }
  };

  return (
    <div className="mx-auto max-w-5xl flex-1 overflow-y-auto px-6 py-6">
      {/* Current skills */}
      <div className="mb-6">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-text-primary">
            Assigned Skills
            {saving && (
              <span className="ml-2 text-xs font-normal text-text-muted">Saving…</span>
            )}
          </h3>
          <span className="text-xs text-text-muted">
            {skillIds.length} skill{skillIds.length !== 1 ? "s" : ""}
          </span>
        </div>

        <div className="rounded-xl border border-border/40 bg-surface p-4">
          <div className="flex flex-wrap gap-2">
            {skillIds.map((sid) => (
              <span
                key={sid}
                className="flex items-center gap-1.5 rounded-full bg-accent-teal/20 px-3 py-1 text-xs font-medium text-accent-teal"
              >
                {sid}
                <button
                  onClick={() => toggleSkill(sid)}
                  className="text-accent-teal/60 hover:text-accent-teal"
                >
                  <X size={12} />
                </button>
              </span>
            ))}
            {skillIds.length === 0 && (
              <span className="text-xs text-text-muted">No skills assigned</span>
            )}
          </div>

          <div className="mt-4 flex gap-2">
            <input
              value={newSkillInput}
              onChange={(e) => setNewSkillInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addCustomSkill();
                }
              }}
              placeholder="Add skill by name..."
              className="flex-1 rounded-lg border border-border/40 bg-workspace px-3 py-1.5 text-xs text-text-primary placeholder:text-text-muted/60 focus:border-accent-teal/50 focus:outline-none"
            />
            <button
              onClick={addCustomSkill}
              disabled={!newSkillInput.trim()}
              className="flex items-center gap-1 rounded-lg bg-accent-teal/10 px-3 py-1.5 text-xs font-medium text-accent-teal transition-colors hover:bg-accent-teal/20 disabled:opacity-40"
            >
              <Plus size={12} />
              Add
            </button>
          </div>
        </div>
      </div>

      {/* Marketplace browser */}
      <div>
        <h3 className="mb-3 text-sm font-semibold text-text-primary">
          Discover Skills
        </h3>
        <SkillBrowser
          selectedSkillIds={skillIds}
          onToggleSkill={toggleSkill}
          onSkillsChanged={refreshSkills}
        />
      </div>
    </div>
  );
}
