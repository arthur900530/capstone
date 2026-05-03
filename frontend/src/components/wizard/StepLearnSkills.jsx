import { useEffect, useState } from "react";
import { Loader2, Sparkles, X } from "lucide-react";
import { useApp } from "../../context/appContextCore";
import { suggestEmployeeSkills } from "../../services/api";
import SkillBrowser from "../skills/SkillBrowser";

export default function StepLearnSkills({
  description,
  pluginIds,
  skillIds,
  onSkillIdsChange,
  onBack,
  onNext,
}) {
  const { refreshSkills } = useApp();
  const [isSuggesting, setIsSuggesting] = useState(false);
  const [suggestionError, setSuggestionError] = useState(null);
  const [hasSuggested, setHasSuggested] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const shouldSuggest =
      pluginIds.length === 0 &&
      skillIds.length === 0 &&
      description.trim() &&
      !hasSuggested;

    if (!shouldSuggest) return undefined;

    const startTimer = setTimeout(() => {
      setIsSuggesting(true);
      setSuggestionError(null);
    }, 0);

    suggestEmployeeSkills(description)
      .then((data) => {
        if (cancelled) return;
        const suggested = Array.isArray(data?.skillIds) ? data.skillIds : [];
        if (suggested.length > 0) {
          onSkillIdsChange(suggested);
        }
      })
      .catch((err) => {
        if (!cancelled) setSuggestionError(err.message);
      })
      .finally(() => {
        if (!cancelled) {
          setIsSuggesting(false);
          setHasSuggested(true);
        }
      });

    return () => {
      cancelled = true;
      clearTimeout(startTimer);
    };
  }, [description, hasSuggested, onSkillIdsChange, pluginIds.length, skillIds.length]);

  const toggleSkill = (sid) => {
    onSkillIdsChange(
      skillIds.includes(sid)
        ? skillIds.filter((s) => s !== sid)
        : [...skillIds, sid],
    );
  };

  const addSkills = (newSkillIds) => {
    onSkillIdsChange([...new Set([...skillIds, ...newSkillIds])]);
  };

  return (
    <div className="mx-auto max-w-3xl">
      <h2 className="mb-2 text-xl font-semibold text-text-primary">
         Skills
      </h2>
      <p className="mb-4 text-sm text-text-muted">
        Browse the marketplace to discover skills, or create your own. Selected
        skills will be assigned to this employee.
      </p>

      {pluginIds.length === 0 && description.trim() && (
        <div className="mb-4 rounded-xl border border-border/40 bg-surface p-3">
          <div className="flex items-start gap-2">
            <Sparkles size={15} className="mt-0.5 text-accent-teal" />
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium text-text-primary">
                Auto skill suggestions
              </p>
              {isSuggesting ? (
                <div className="mt-1 flex items-center gap-2 text-xs text-text-muted">
                  <Loader2 size={12} className="animate-spin" />
                  Matching skills from the employee description...
                </div>
              ) : suggestionError ? (
                <p className="mt-1 text-xs text-red-400">{suggestionError}</p>
              ) : (
                <p className="mt-1 text-xs text-text-muted">
                  Suggested skills are preselected here when no plugin is chosen.
                </p>
              )}
            </div>
          </div>
        </div>
      )}

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
        onAddSkills={addSkills}
        onSkillsChanged={refreshSkills}
        defaultSubTab="create"
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
