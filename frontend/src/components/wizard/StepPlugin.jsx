import { useState } from "react";
import { ChevronDown, Plus, X, List, Share2 } from "lucide-react";
import PLUGINS from "../../data/plugins";
import PluginCard from "../PluginCard";
import SkillGraph from "./SkillGraph";

const MODEL_OPTIONS = [
  { value: "openai/gpt-5.1", label: "GPT-5.1" },
  { value: "openai/gpt-4o", label: "GPT-4o" },
  { value: "anthropic/claude-sonnet-4-5-20250929", label: "Claude Sonnet" },
  { value: "anthropic/claude-haiku-3-5-20241022", label: "Claude Haiku" },
];

export default function StepPlugin({
  selectedPluginIds,
  onSelectPlugins,
  skillIds,
  onSkillIdsChange,
  config,
  onConfigChange,
  allSkills,
  onBack,
  onNext,
}) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showSkillEditor, setShowSkillEditor] = useState(false);
  const [skillViewMode, setSkillViewMode] = useState("list");
  const [newSkillInput, setNewSkillInput] = useState("");

  const handlePluginToggle = (plugin) => {
    const alreadySelected = selectedPluginIds.includes(plugin.id);
    let nextIds;
    if (alreadySelected) {
      nextIds = selectedPluginIds.filter((id) => id !== plugin.id);
    } else {
      nextIds = [...selectedPluginIds, plugin.id];
    }
    onSelectPlugins(nextIds);

    // Merge skill IDs from all selected plugins
    const mergedPlugins = PLUGINS.filter((p) => nextIds.includes(p.id));
    const mergedSkills = [...new Set(mergedPlugins.flatMap((p) => p.skillIds))];
    onSkillIdsChange(mergedSkills);

    // Use model from the most recently added plugin
    if (!alreadySelected) {
      onConfigChange({ ...config, model: plugin.defaultModel });
    }
  };

  const toggleSkill = (sid) => {
    onSkillIdsChange(
      skillIds.includes(sid)
        ? skillIds.filter((s) => s !== sid)
        : [...skillIds, sid],
    );
  };

  const removeSkill = (sid) => {
    onSkillIdsChange(skillIds.filter((s) => s !== sid));
  };

  const addCustomSkill = () => {
    const trimmed = newSkillInput.trim();
    if (trimmed && !skillIds.includes(trimmed)) {
      onSkillIdsChange([...skillIds, trimmed]);
      setNewSkillInput("");
    }
  };

  const hasSelection = selectedPluginIds.length > 0;

  return (
    <div className="mx-auto max-w-3xl">
      <h2 className="mb-2 text-xl font-semibold text-text-primary">
        Choose plugins <span className="text-sm font-normal text-text-muted">(optional)</span>
      </h2>
      <p className="mb-6 text-sm text-text-muted">
        Select plugins to bundle skills tailored to a role, or skip this step to auto select skills.
      </p>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {PLUGINS.map((plugin) => (
          <PluginCard
            key={plugin.id}
            plugin={plugin}
            selected={selectedPluginIds.includes(plugin.id)}
            onClick={() => handlePluginToggle(plugin)}
          />
        ))}
      </div>

      {/* Skill editor */}
      {hasSelection && (
        <div className="mt-6">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowSkillEditor((v) => !v)}
              className="text-sm font-medium text-accent-teal hover:underline"
            >
              {showSkillEditor ? "Hide" : "Edit"} skills
            </button>

            {showSkillEditor && (
              <div className="flex rounded-lg border border-border/40 bg-workspace p-0.5">
                <button
                  onClick={() => setSkillViewMode("list")}
                  className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                    skillViewMode === "list"
                      ? "bg-surface text-text-primary shadow-sm"
                      : "text-text-muted hover:text-text-secondary"
                  }`}
                >
                  <List size={12} />
                  List
                </button>
                <button
                  onClick={() => setSkillViewMode("graph")}
                  className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                    skillViewMode === "graph"
                      ? "bg-surface text-text-primary shadow-sm"
                      : "text-text-muted hover:text-text-secondary"
                  }`}
                >
                  <Share2 size={12} />
                  Graph
                </button>
              </div>
            )}
          </div>

          {showSkillEditor && skillViewMode === "list" && (
            <div className="mt-3 rounded-xl border border-border/40 bg-surface p-4">
              <p className="mb-3 text-xs text-text-muted">
                Add, remove, or create skills for this employee:
              </p>

              <div className="flex flex-wrap gap-2">
                {skillIds.map((sid) => (
                  <span
                    key={sid}
                    className="flex items-center gap-1.5 rounded-full bg-accent-teal/20 px-3 py-1 text-xs font-medium text-accent-teal"
                  >
                    {sid}
                    <button
                      onClick={() => removeSkill(sid)}
                      className="text-accent-teal/60 hover:text-accent-teal"
                    >
                      <X size={12} />
                    </button>
                  </span>
                ))}
                {skillIds.length === 0 && (
                  <span className="text-xs text-text-muted">No skills selected</span>
                )}
              </div>

              {allSkills.length > 0 && (
                <div className="mt-4">
                  <p className="mb-2 text-xs font-medium text-text-muted">
                    Available skills:
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {allSkills.map((skill) => {
                      const id = skill.id || skill.name;
                      const active = skillIds.includes(id);
                      return (
                        <button
                          key={id}
                          onClick={() => toggleSkill(id)}
                          className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                            active
                              ? "bg-accent-teal/20 text-accent-teal"
                              : "bg-surface-hover text-text-muted hover:text-text-secondary"
                          }`}
                        >
                          {skill.name || id}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

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
          )}

          {showSkillEditor && skillViewMode === "graph" && (
            <SkillGraph
              pluginIds={selectedPluginIds}
              skillIds={skillIds}
              onToggleSkill={toggleSkill}
            />
          )}
        </div>
      )}

      {/* Model & advanced config */}
      <div className="mt-6 border-t border-border/20 pt-4">
        <button
          onClick={() => setShowAdvanced((v) => !v)}
          className="flex items-center gap-2 text-sm text-text-muted hover:text-text-secondary"
        >
          <ChevronDown
            size={14}
            className={`transition-transform ${showAdvanced ? "rotate-180" : ""}`}
          />
          Edit Model &amp; Settings
        </button>

        {showAdvanced && (
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-text-muted">
                Model
              </label>
              <select
                value={config.model}
                onChange={(e) =>
                  onConfigChange({ ...config, model: e.target.value })
                }
                className="w-full rounded-lg border border-border/40 bg-surface px-3 py-2 text-sm text-text-primary focus:border-accent-teal/50 focus:outline-none"
              >
                {MODEL_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex items-end gap-4">
              <label className="flex items-center gap-2 text-sm text-text-secondary">
                <input
                  type="checkbox"
                  checked={config.useReflexion}
                  onChange={(e) =>
                    onConfigChange({ ...config, useReflexion: e.target.checked })
                  }
                  className="rounded accent-accent-teal"
                />
                Enable Reflexion
              </label>
            </div>

            <div>
              <label className="mb-1.5 block text-xs font-medium text-text-muted">
                Max Trials
              </label>
              <input
                type="number"
                min={1}
                max={10}
                value={config.maxTrials}
                onChange={(e) =>
                  onConfigChange({
                    ...config,
                    maxTrials: parseInt(e.target.value) || 3,
                  })
                }
                className="w-full rounded-lg border border-border/40 bg-surface px-3 py-2 text-sm text-text-primary focus:border-accent-teal/50 focus:outline-none"
              />
            </div>

            <div>
              <label className="mb-1.5 block text-xs font-medium text-text-muted">
                Confidence Threshold
              </label>
              <input
                type="number"
                min={0}
                max={1}
                step={0.1}
                value={config.confidenceThreshold}
                onChange={(e) =>
                  onConfigChange({
                    ...config,
                    confidenceThreshold: parseFloat(e.target.value) || 0.7,
                  })
                }
                className="w-full rounded-lg border border-border/40 bg-surface px-3 py-2 text-sm text-text-primary focus:border-accent-teal/50 focus:outline-none"
              />
            </div>
          </div>
        )}
      </div>

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
          {hasSelection ? "Next" : "Auto Select"}
        </button>
      </div>
    </div>
  );
}
