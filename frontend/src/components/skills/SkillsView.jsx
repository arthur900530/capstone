import { useState, useEffect } from "react";
import { Wrench, Plus, Loader2, AlertCircle, Search, Sparkles } from "lucide-react";
import { fetchSkills } from "../../services/api";
import SkillListItem from "./SkillListItem";
import SkillEditor from "./SkillEditor";
import CreateSkillModal from "./CreateSkillModal";
import TrainSkillModal from "./TrainSkillModal";

export default function SkillsView({ onSkillsChanged }) {
  const [skills, setSkills] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [viewingFile, setViewingFile] = useState(null);
  const [search, setSearch] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [showTrain, setShowTrain] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchSkills()
      .then((data) => {
        if (!cancelled) {
          setSkills(data);
          setSelectedId((prev) => prev ?? (data.length > 0 ? data[0].id : null));
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const filtered = skills.filter(
    (s) =>
      s.name.toLowerCase().includes(search.toLowerCase()) ||
      s.id.toLowerCase().includes(search.toLowerCase()),
  );

  const selectedSkill = skills.find((s) => s.id === selectedId);

  const handleSelectSkill = (id) => {
    setViewingFile(null);
    setSelectedId(id);
  };

  const handleFileClick = (skillId, filename) => {
    setSelectedId(skillId);
    setViewingFile(filename);
  };

  const handleCreated = (skill) => {
    setSkills((prev) => [...prev, skill]);
    setSelectedId(skill.id);
    setViewingFile(null);
    onSkillsChanged?.();
  };

  const handleTrained = async (newSkills) => {
    const refreshed = await fetchSkills();
    setSkills(refreshed);
    if (newSkills.length > 0) {
      setSelectedId(newSkills[0].id);
      setViewingFile(null);
    }
    onSkillsChanged?.();
  };

  const handleSaved = (updated) => {
    setSkills((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
  };

  const handleDeleted = (id) => {
    setSkills((prev) => prev.filter((s) => s.id !== id));
    setSelectedId((prev) => {
      if (prev !== id) return prev;
      const remaining = skills.filter((s) => s.id !== id);
      return remaining.length > 0 ? remaining[0].id : null;
    });
    onSkillsChanged?.();
  };

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <Loader2 size={24} className="animate-spin text-accent-teal" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="flex items-center gap-2 text-sm text-red-400">
          <AlertCircle size={16} />
          {error}
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="flex flex-1 overflow-hidden pt-12 lg:pt-0">
        {/* Skill list panel */}
        <div className="flex w-[280px] shrink-0 flex-col border-r border-border/40 bg-charcoal/30">
          <div className="border-b border-border/40 p-3">
            <div className="mb-2.5 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Wrench size={15} className="text-accent-teal" />
                <h2 className="text-sm font-semibold text-text-primary">Skills</h2>
                <span className="rounded-full bg-surface px-1.5 py-0.5 text-[10px] text-text-muted">
                  {skills.length}
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => setShowTrain(true)}
                  className="flex items-center gap-1 rounded-lg bg-purple-500/10 px-2 py-1 text-xs font-medium text-purple-400 transition-colors hover:bg-purple-500/20"
                >
                  <Sparkles size={13} />
                  Train
                </button>
                <button
                  onClick={() => setShowCreate(true)}
                  className="flex items-center gap-1 rounded-lg bg-accent-teal/10 px-2 py-1 text-xs font-medium text-accent-teal transition-colors hover:bg-accent-teal/20"
                >
                  <Plus size={13} />
                  New
                </button>
              </div>
            </div>
            <div className="relative">
              <Search
                size={14}
                className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted"
              />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search skills…"
                className="w-full rounded-lg border border-border/40 bg-charcoal py-1.5 pl-8 pr-3 text-xs text-text-primary placeholder:text-text-muted outline-none transition-colors focus:border-accent-teal"
              />
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-2">
            {filtered.length === 0 ? (
              <p className="px-3 py-6 text-center text-xs text-text-muted">
                {search ? "No matching skills" : "No skills yet"}
              </p>
            ) : (
              <ul className="space-y-0.5">
                {filtered.map((skill) => (
                  <SkillListItem
                    key={skill.id}
                    skill={skill}
                    isSelected={skill.id === selectedId}
                    onSelect={handleSelectSkill}
                    onFileClick={handleFileClick}
                  />
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* Skill detail / editor */}
        <div className="flex flex-1 flex-col bg-workspace">
          {selectedSkill ? (
            <SkillEditor
              key={selectedSkill.id}
              skill={selectedSkill}
              onSaved={handleSaved}
              onDeleted={handleDeleted}
              viewingFile={viewingFile}
              onViewFile={setViewingFile}
            />
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center">
              <Wrench size={40} className="text-text-muted" />
              <div>
                <p className="text-sm font-medium text-text-primary">
                  {skills.length === 0 ? "No skills yet" : "Select a skill"}
                </p>
                <p className="mt-1 text-xs text-text-muted">
                  {skills.length === 0
                    ? "Create your first custom skill to get started."
                    : "Choose a skill from the list to view or edit it."}
                </p>
              </div>
              {skills.length === 0 && (
                <button
                  onClick={() => setShowCreate(true)}
                  className="mt-2 flex items-center gap-1.5 rounded-lg bg-accent-teal px-4 py-2 text-sm font-medium text-charcoal transition-colors hover:bg-accent-light"
                >
                  <Plus size={15} />
                  Create Skill
                </button>
              )}
            </div>
          )}
        </div>
      </div>

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
    </>
  );
}
