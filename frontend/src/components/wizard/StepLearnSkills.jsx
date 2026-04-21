import { X } from "lucide-react";
import { useApp } from "../../context/AppContext";
import SkillBrowser from "../skills/SkillBrowser";

export default function StepLearnSkills({ skillIds, onSkillIdsChange, onBack, onNext }) {
  const { refreshSkills } = useApp();

  const toggleSkill = (sid) => {
    onSkillIdsChange(
      skillIds.includes(sid)
        ? skillIds.filter((s) => s !== sid)
        : [...skillIds, sid],
    );
  };

  return (
    <div className="mx-auto max-w-3xl">
      <h2 className="mb-2 text-xl font-semibold text-text-primary">
        Learn Skills
      </h2>
      <p className="mb-4 text-sm text-text-muted">
        Browse the marketplace to discover skills, or create your own. Selected
        skills will be assigned to this employee.
      </p>

      {/* Selected skills summary */}
      {skillIds.length > 0 && (
        <div className="mb-4 rounded-xl border border-border/40 bg-surface p-3">
          <p className="mb-2 text-xs font-medium text-text-muted">
            {skillIds.length} skill{skillIds.length !== 1 ? "s" : ""} selected
          </p>
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
          </div>
        </div>
      )}

      <SkillBrowser
        selectedSkillIds={skillIds}
        onToggleSkill={toggleSkill}
        onSkillsChanged={refreshSkills}
      />

      <div className="mt-8 flex justify-between">
        <button
          onClick={onBack}
          className="rounded-lg border border-border/40 px-6 py-2.5 text-sm font-medium text-text-secondary transition-colors hover:bg-surface"
        >
          Back
        </button>
        <button
          onClick={onNext}
          className="rounded-lg bg-accent-teal px-6 py-2.5 text-sm font-medium text-workspace transition-colors hover:bg-accent-teal/90"
        >
          Next
        </button>
      </div>
    </div>
  );
}
