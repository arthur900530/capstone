import { useState, useEffect } from "react";
import {
  Search, Plus, Sparkles, LayoutGrid, List, Loader2,
  Wrench, X, Check, Download, AlertCircle, Store, Upload as UploadIcon,
} from "lucide-react";
import { fetchSkills, installSkill, uninstallSkill, deleteSkill } from "../../services/api";
import SkillCard from "./SkillCard";
import SkillDetailPanel from "./SkillDetailPanel";
import CreateSkillModal from "./CreateSkillModal";
import TrainSkillModal from "./TrainSkillModal";
import SubmitSkillModal from "./SubmitSkillModal";

export default function SkillBrowser({ selectedSkillIds, onToggleSkill, onSkillsChanged }) {
  const [skills, setSkills] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [search, setSearch] = useState("");
  const [viewMode, setViewMode] = useState("grid");
  const [typeFilter, setTypeFilter] = useState("all");
  const [subTab, setSubTab] = useState("browse");
  const [showCreate, setShowCreate] = useState(false);
  const [showTrain, setShowTrain] = useState(false);
  const [showSubmit, setShowSubmit] = useState(null);

  useEffect(() => {
    let cancelled = false;
    fetchSkills()
      .then((data) => { if (!cancelled) setSkills(data); })
      .catch((err) => { if (!cancelled) setError(err.message); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const filtered = skills.filter((s) => {
    const matchesSearch = !search ||
      s.name.toLowerCase().includes(search.toLowerCase()) ||
      s.id.toLowerCase().includes(search.toLowerCase());
    const matchesType = typeFilter === "all" ||
      (typeFilter === "builtin" && (s.is_builtin || s.type === "builtin")) ||
      (typeFilter === "user" && (!s.is_builtin && s.type !== "builtin"));
    return matchesSearch && matchesType;
  });

  const selectedSkill = skills.find((s) => s.id === selectedId);

  const refreshList = async () => {
    const refreshed = await fetchSkills();
    setSkills(refreshed);
    onSkillsChanged?.();
  };

  const handleCreated = (skill) => {
    setSkills((prev) => [...prev, skill]);
    setSelectedId(skill.id);
    setSubTab("browse");
    onToggleSkill(skill.id);
    onSkillsChanged?.();
  };

  const handleTrained = async (newSkills) => {
    await refreshList();
    setSubTab("browse");
    if (newSkills.length > 0) {
      setSelectedId(newSkills[0].id);
      onToggleSkill(newSkills[0].id);
    }
  };

  const isSelected = (skillId) => selectedSkillIds.includes(skillId);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 size={20} className="animate-spin text-accent-teal" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="flex items-center gap-2 text-sm text-red-400">
          <AlertCircle size={16} />
          {error}
        </div>
      </div>
    );
  }

  return (
    <>
      {/* Sub-tabs */}
      <div className="flex items-center gap-1">
        {[
          { id: "browse", label: "Browse", icon: Store },
          { id: "create", label: "Create", icon: UploadIcon },
        ].map(({ id, label, icon: TabIcon }) => (
          <button
            key={id}
            onClick={() => setSubTab(id)}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
              subTab === id
                ? "bg-surface text-text-primary"
                : "text-text-muted hover:bg-surface/50 hover:text-text-secondary"
            }`}
          >
            <TabIcon size={13} />
            {label}
          </button>
        ))}
      </div>

      {subTab === "browse" ? (
        <>
          {/* Toolbar */}
          <div className="mt-3 flex items-center gap-2">
            <div className="relative flex-1">
              <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search skills…"
                className="w-full rounded-lg border border-border/40 bg-workspace py-1.5 pl-8 pr-3 text-xs text-text-primary placeholder:text-text-muted outline-none transition-colors focus:border-accent-teal"
              />
            </div>
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="shrink-0 rounded-lg border border-border/40 bg-workspace px-2.5 py-1.5 text-xs text-text-primary outline-none transition-colors focus:border-accent-teal"
            >
              <option value="all">All Types</option>
              <option value="builtin">Builtin</option>
              <option value="user">User</option>
            </select>
            <div className="flex shrink-0 items-center rounded-lg border border-border/40 bg-workspace">
              <button
                onClick={() => setViewMode("grid")}
                className={`rounded-l-lg p-1.5 transition-colors ${
                  viewMode === "grid" ? "bg-surface text-text-primary" : "text-text-muted hover:text-text-secondary"
                }`}
              >
                <LayoutGrid size={14} />
              </button>
              <button
                onClick={() => setViewMode("list")}
                className={`rounded-r-lg p-1.5 transition-colors ${
                  viewMode === "list" ? "bg-surface text-text-primary" : "text-text-muted hover:text-text-secondary"
                }`}
              >
                <List size={14} />
              </button>
            </div>
          </div>

          {/* Grid / List */}
          <div className="mt-3">
            {filtered.length === 0 ? (
              <div className="flex flex-col items-center justify-center gap-3 py-12 text-center">
                <Wrench size={28} className="text-text-muted" />
                <p className="text-sm text-text-muted">
                  {search ? "No matching skills" : "No skills yet"}
                </p>
              </div>
            ) : viewMode === "grid" ? (
              <div className="grid auto-rows-fr grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                {filtered.map((skill) => (
                  <div key={skill.id} className="relative min-h-0">
                    <SkillCard
                      skill={skill}
                      isSelected={skill.id === selectedId}
                      onClick={() => setSelectedId(skill.id === selectedId ? null : skill.id)}
                      viewMode="grid"
                    />
                    {/* Selection overlay */}
                    <button
                      onClick={(e) => { e.stopPropagation(); onToggleSkill(skill.id); }}
                      className={`absolute right-2 top-2 z-10 flex h-6 w-6 items-center justify-center rounded-full border transition-colors ${
                        isSelected(skill.id)
                          ? "border-accent-teal bg-accent-teal text-workspace"
                          : "border-border/60 bg-surface/80 text-text-muted hover:border-accent-teal/50 hover:text-accent-teal"
                      }`}
                    >
                      {isSelected(skill.id) ? <Check size={12} /> : <Plus size={12} />}
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="space-y-1">
                {filtered.map((skill) => (
                  <div key={skill.id} className="flex items-center gap-1">
                    <div className="min-w-0 flex-1">
                      <SkillCard
                        skill={skill}
                        isSelected={skill.id === selectedId}
                        onClick={() => setSelectedId(skill.id === selectedId ? null : skill.id)}
                        viewMode="list"
                      />
                    </div>
                    <button
                      onClick={() => onToggleSkill(skill.id)}
                      className={`shrink-0 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors ${
                        isSelected(skill.id)
                          ? "bg-accent-teal/20 text-accent-teal"
                          : "bg-surface text-text-muted hover:text-text-secondary"
                      }`}
                    >
                      {isSelected(skill.id) ? "Remove" : "Add"}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      ) : (
        /* Create tab */
        <div className="mt-3 flex flex-col items-center justify-center gap-4 rounded-xl border border-border/30 bg-surface/30 py-12">
          <div className="text-center">
            <h3 className="text-lg font-medium text-text-primary">Create or Train Skills</h3>
            <p className="mt-1 text-sm text-text-muted">
              Author a new skill manually or train from media files.
            </p>
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => setShowCreate(true)}
              className="flex items-center gap-2 rounded-xl border border-border/40 bg-surface px-6 py-4 text-sm font-medium text-text-primary transition-colors hover:border-accent-teal/30 hover:bg-surface-hover"
            >
              <Plus size={18} className="text-accent-teal" />
              Create Manually
            </button>
            <button
              onClick={() => setShowTrain(true)}
              className="flex items-center gap-2 rounded-xl border border-border/40 bg-surface px-6 py-4 text-sm font-medium text-text-primary transition-colors hover:border-purple-400/30 hover:bg-surface-hover"
            >
              <Sparkles size={18} className="text-purple-400" />
              Train from Media
            </button>
          </div>
        </div>
      )}

      {/* Detail modal */}
      {selectedSkill && (
        <div className="fixed inset-0 z-40 flex items-center justify-center p-8">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setSelectedId(null)} />
          <div className="relative z-10 flex max-h-[80vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-border/30 bg-workspace shadow-2xl">
            {/* Add/Remove bar */}
            <div className="flex items-center justify-between border-b border-border/30 bg-surface/50 px-4 py-2">
              <span className="text-xs text-text-muted">
                {isSelected(selectedSkill.id) ? "This skill is assigned to the employee" : "Click below to assign this skill"}
              </span>
              <button
                onClick={() => onToggleSkill(selectedSkill.id)}
                className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                  isSelected(selectedSkill.id)
                    ? "bg-red-500/10 text-red-400 hover:bg-red-500/20"
                    : "bg-accent-teal px-4 text-workspace hover:bg-accent-teal/90"
                }`}
              >
                {isSelected(selectedSkill.id) ? (
                  <><X size={12} /> Remove from Employee</>
                ) : (
                  <><Plus size={12} /> Add to Employee</>
                )}
              </button>
            </div>
            <div className="flex-1 overflow-hidden">
              <SkillDetailPanel
                skill={selectedSkill}
                onClose={() => setSelectedId(null)}
                onSaved={(updated) => {
                  setSkills((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
                }}
                onInstall={async (id) => {
                  await installSkill(id);
                  await refreshList();
                  if (!isSelected(id)) onToggleSkill(id);
                }}
                onUninstall={async (id) => {
                  await uninstallSkill(id);
                  await refreshList();
                }}
                onDelete={async (id) => {
                  setSelectedId(null);
                  setSkills((prev) => prev.filter((s) => s.id !== id));
                  await deleteSkill(id);
                  await refreshList();
                }}
              />
            </div>
          </div>
        </div>
      )}

      <CreateSkillModal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onCreated={handleCreated}
      />
      <TrainSkillModal
        open={showTrain}
        onClose={() => setShowTrain(false)}
        onTrained={handleTrained}
      />
      <SubmitSkillModal
        open={!!showSubmit}
        onClose={() => setShowSubmit(null)}
        skill={selectedSkill}
        version={showSubmit?.version}
        onSubmitted={() => showSubmit?.onSuccess?.()}
      />
    </>
  );
}
