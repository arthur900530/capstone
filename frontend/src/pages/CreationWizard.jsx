import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import StepDescribe from "../components/wizard/StepDescribe";
import StepPlugin from "../components/wizard/StepPlugin";
import StepLearnSkills from "../components/wizard/StepLearnSkills";
import StepLaunch from "../components/wizard/StepLaunch";
import PLUGINS from "../data/plugins";
import EMPLOYEE_TEMPLATES from "../data/employeeTemplates";
import { createEmployee } from "../services/employeeStore";
import { useApp } from "../context/appContextCore";

const STEPS = ["Describe", "Plugin", "Learn Skills", "Launch"];

export default function CreationWizard() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { skills, refreshEmployees } = useApp();

  // Pre-fill from template if ?template=id
  const templateId = searchParams.get("template");
  const template = EMPLOYEE_TEMPLATES.find((t) => t.id === templateId);
  const templatePlugins = template
    ? PLUGINS.filter((p) => template.pluginIds.includes(p.id))
    : [];

  const [step, setStep] = useState(0);
  const [description, setDescription] = useState("");
  const [selectedPluginIds, setSelectedPluginIds] = useState(
    template?.pluginIds || [],
  );
  const [skillIds, setSkillIds] = useState(
    templatePlugins.length > 0
      ? [...new Set(templatePlugins.flatMap((p) => p.skillIds))]
      : [],
  );
  const [config, setConfig] = useState({
    model: templatePlugins[0]?.defaultModel || "",
    maxTrials: 3,
    confidenceThreshold: 0.7,
    useReflexion: false,
  });
  const [name, setName] = useState(template?.suggestedName || "");
  // The template's display name doubles as a sensible default job title/role
  // ("Equity Research Analyst", etc.) — the user can override it on the
  // Launch step before creating the employee.
  const [position, setPosition] = useState(template?.name || "");

  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState(null);

  const handleCreate = async () => {
    if (creating) return;
    setCreating(true);
    setCreateError(null);
    try {
      const emp = await createEmployee({
        name: name.trim(),
        position: position.trim(),
        description,
        pluginIds: selectedPluginIds,
        skillIds,
        model: config.model || undefined,
        useReflexion: config.useReflexion,
        maxTrials: config.maxTrials,
        confidenceThreshold: config.confidenceThreshold,
      });
      await refreshEmployees();
      navigate(`/employee/${emp.id}`);
    } catch (err) {
      setCreating(false);
      setCreateError(err?.message || "Failed to create employee.");
    }
  };

  return (
    <div className="flex flex-1 flex-col overflow-y-auto">
      <div className="border-b border-border/30 px-6 py-4">
        <div className="mx-auto flex max-w-3xl items-center gap-4">
          <button
            onClick={() => navigate("/")}
            className="text-text-muted hover:text-text-secondary"
          >
            <ArrowLeft size={18} />
          </button>
          <h1 className="text-lg font-semibold text-text-primary">
            Create Employee
          </h1>
        </div>
      </div>

      <div className="border-b border-border/20 px-6 py-3">
        <div className="mx-auto flex max-w-3xl items-center justify-center gap-2">
          {STEPS.map((label, i) => (
            <div key={label} className="flex items-center gap-2">
              <div
                className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold ${
                  i <= step
                    ? "bg-accent-teal text-workspace"
                    : "bg-surface text-text-muted"
                }`}
              >
                {i + 1}
              </div>
              <span
                className={`text-xs ${
                  i <= step ? "text-text-primary" : "text-text-muted"
                }`}
              >
                {label}
              </span>
              {i < STEPS.length - 1 && (
                <div
                  className={`mx-1 h-px w-8 ${
                    i < step ? "bg-accent-teal" : "bg-border/40"
                  }`}
                />
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="flex-1 px-6 py-8">
        {step === 0 && (
          <StepDescribe
            description={description}
            onChange={setDescription}
            onNext={() => setStep(1)}
          />
        )}
        {step === 1 && (
          <StepPlugin
            description={description}
            selectedPluginIds={selectedPluginIds}
            onSelectPlugins={setSelectedPluginIds}
            skillIds={skillIds}
            onSkillIdsChange={setSkillIds}
            config={config}
            onConfigChange={setConfig}
            allSkills={skills}
            onBack={() => setStep(0)}
            onNext={() => setStep(2)}
          />
        )}
        {step === 2 && (
          <StepLearnSkills
            description={description}
            pluginIds={selectedPluginIds}
            skillIds={skillIds}
            onSkillIdsChange={setSkillIds}
            onBack={() => setStep(1)}
            onNext={() => setStep(3)}
          />
        )}
        {step === 3 && (
          <StepLaunch
            name={name}
            onNameChange={setName}
            position={position}
            onPositionChange={setPosition}
            description={description}
            pluginIds={selectedPluginIds}
            skillIds={skillIds}
            config={config}
            creating={creating}
            error={createError}
            onBack={() => setStep(2)}
            onCreate={handleCreate}
          />
        )}
      </div>
    </div>
  );
}
