import { useState, useEffect } from "react";
import {
  Wrench, Plus, Loader2, AlertCircle, Search, Sparkles,
  LayoutGrid, List, Store, Download, Upload as UploadIcon, ClipboardCheck,
} from "lucide-react";
import { fetchSkills, installSkill, uninstallSkill, deleteSkill } from "../../services/api";
import SkillCard from "./SkillCard";
import SkillEditor from "./SkillEditor";
import SkillDetailPanel from "./SkillDetailPanel";
import CreateSkillModal from "./CreateSkillModal";
import TrainSkillModal from "./TrainSkillModal";
import SubmitSkillModal from "./SubmitSkillModal";
import ReviewQueue from "./ReviewQueue";

const TABS = [
  { id: "browse", label: "Browse", icon: Store },
  { id: "installed", label: "Installed", icon: Download },
  { id: "create", label: "Create", icon: UploadIcon },
  { id: "review", label: "Review", icon: ClipboardCheck },
];

export default function SkillsView({ onSkillsChanged }) {
  const [skills, setSkills] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [viewingFile, setViewingFile] = useState(null);
  const [search, setSearch] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [showTrain, setShowTrain] = useState(false);
  const [showSubmit, setShowSubmit] = useState(false);
  const [subTab, setSubTab] = useState("browse");
  const [viewMode, setViewMode] = useState("grid");
  const [typeFilter, setTypeFilter] = useState("all");

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

  // Filter by search
  // Search + type filter
  const searched = skills.filter((s) => {
    const matchesSearch = !search ||
      s.name.toLowerCase().includes(search.toLowerCase()) ||
      s.id.toLowerCase().includes(search.toLowerCase());
    const matchesType = typeFilter === "all" ||
      (typeFilter === "builtin" && (s.is_builtin || s.type === "builtin")) ||
      (typeFilter === "user" && (!s.is_builtin && s.type !== "builtin"));
    return matchesSearch && matchesType;
  });

  // Further filter by tab
  const filtered = subTab === "installed"
    ? searched.filter((s) => !s.is_cloud_only)
    : subTab === "review"
      ? searched.filter((s) => s.status === "pending_review")
      : searched;

  const selectedSkill = skills.find((s) => s.id === selectedId);

  const installedCount = skills.filter((s) => !s.is_cloud_only).length;
  const reviewCount = skills.filter((s) => s.status === "pending_review").length;

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
    setSubTab("browse");
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
      <div className="flex flex-1 flex-col overflow-hidden pt-12 lg:pt-0">
        <div className="border-b border-border/40 bg-charcoal/30 px-4 py-3">
          <div className="h-5 w-40 animate-pulse rounded bg-surface" />
          <div className="mt-3 flex gap-2">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-7 w-20 animate-pulse rounded-lg bg-surface" />
            ))}
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div key={i} className="rounded-xl border border-border/40 bg-surface p-4">
                <div className="flex items-center gap-2.5">
                  <div className="h-9 w-9 animate-pulse rounded-lg bg-surface-hover" />
                  <div className="flex-1 space-y-1.5">
                    <div className="h-4 w-32 animate-pulse rounded bg-surface-hover" />
                    <div className="h-3 w-20 animate-pulse rounded bg-surface-hover" />
                  </div>
                </div>
                <div className="mt-3 space-y-1.5">
                  <div className="h-3 w-full animate-pulse rounded bg-surface-hover" />
                  <div className="h-3 w-2/3 animate-pulse rounded bg-surface-hover" />
                </div>
                <div className="mt-3 flex gap-2">
                  <div className="h-5 w-14 animate-pulse rounded-full bg-surface-hover" />
                  <div className="h-5 w-10 animate-pulse rounded-full bg-surface-hover" />
                </div>
              </div>
            ))}
          </div>
        </div>
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
      <div className="flex flex-1 flex-col overflow-hidden pt-12 lg:pt-0">
        {/* Top toolbar */}
        <div className="border-b border-border/40 bg-charcoal/30 px-4 py-3">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <Store size={16} className="text-accent-teal" />
              <h2 className="text-sm font-semibold text-text-primary">Skill Marketplace</h2>
              <span className="rounded-full bg-surface px-1.5 py-0.5 text-[10px] text-text-muted">
                {skills.length}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowTrain(true)}
                className="flex items-center gap-1 rounded-lg bg-purple-500/10 px-2.5 py-1.5 text-xs font-medium text-purple-400 transition-colors hover:bg-purple-500/20"
              >
                <Sparkles size={13} />
                Train
              </button>
              <button
                onClick={() => setShowCreate(true)}
                className="flex items-center gap-1 rounded-lg bg-accent-teal/10 px-2.5 py-1.5 text-xs font-medium text-accent-teal transition-colors hover:bg-accent-teal/20"
              >
                <Plus size={13} />
                New Skill
              </button>
            </div>
          </div>

          {/* Sub-tabs row */}
          <div className="mt-3 flex items-center gap-1">
            {TABS.map(({ id, label, icon: TabIcon }) => {
              const count = id === "installed" ? installedCount
                : id === "review" ? reviewCount
                : null;
              return (
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
                  {count != null && count > 0 && (
                    <span className="rounded-full bg-accent-teal/10 px-1.5 py-0.5 text-[10px] text-accent-teal">
                      {count}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* Controls row — always visible */}
          {(subTab === "browse" || subTab === "installed") && (
            <div className="mt-2 flex items-center gap-2">
              <div className="relative flex-1">
                <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted" />
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search skills…"
                  className="w-full rounded-lg border border-border/40 bg-charcoal py-1.5 pl-8 pr-3 text-xs text-text-primary placeholder:text-text-muted outline-none transition-colors focus:border-accent-teal"
                />
              </div>

              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                className="shrink-0 rounded-lg border border-border/40 bg-charcoal px-2.5 py-1.5 text-xs text-text-primary outline-none transition-colors focus:border-accent-teal"
              >
                <option value="all">All Types</option>
                <option value="builtin">Builtin</option>
                <option value="user">User</option>
              </select>

              <div className="flex shrink-0 items-center rounded-lg border border-border/40 bg-charcoal">
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
          )}
        </div>

        {/* Content area */}
        <div className="flex flex-1 overflow-hidden">
          {subTab === "browse" || subTab === "installed" ? (
            <>
              {/* Card grid / list */}
              <div className="min-w-0 flex-1 overflow-y-auto overflow-x-hidden p-4">
                {filtered.length === 0 ? (
                  <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
                    <Wrench size={32} className="text-text-muted" />
                    <p className="text-sm text-text-muted">
                      {search ? "No matching skills" : subTab === "installed" ? "No installed skills" : "No skills yet"}
                    </p>
                    {!search && skills.length === 0 && (
                      <button
                        onClick={() => setShowCreate(true)}
                        className="mt-1 flex items-center gap-1.5 rounded-lg bg-accent-teal px-4 py-2 text-sm font-medium text-charcoal transition-colors hover:bg-accent-light"
                      >
                        <Plus size={15} />
                        Create Skill
                      </button>
                    )}
                  </div>
                ) : viewMode === "grid" ? (
                  <div className="animate-fade-in grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
                    {filtered.map((skill) => (
                      <SkillCard
                        key={skill.id}
                        skill={skill}
                        isSelected={skill.id === selectedId}
                        onClick={() => handleSelectSkill(skill.id)}
                        viewMode="grid"
                      />
                    ))}
                  </div>
                ) : (
                  <div className="space-y-1">
                    {filtered.map((skill) => (
                      <SkillCard
                        key={skill.id}
                        skill={skill}
                        isSelected={skill.id === selectedId}
                        onClick={() => handleSelectSkill(skill.id)}
                        viewMode="list"
                      />
                    ))}
                  </div>
                )}
              </div>

              {/* Detail panel — hidden on small screens, side panel on lg+ */}
              {selectedSkill && (
                <div className="hidden w-[480px] shrink-0 animate-slide-in-right border-l border-border/40 bg-workspace lg:block xl:w-[560px]">
                  {subTab === "installed" ? (
                    <SkillEditor
                      key={selectedSkill.id}
                      skill={selectedSkill}
                      onSaved={handleSaved}
                      onDeleted={handleDeleted}
                      viewingFile={viewingFile}
                      onViewFile={setViewingFile}
                      onSubmit={() => setShowSubmit(true)}
                    />
                  ) : (
                    <SkillDetailPanel
                      key={selectedSkill.id}
                      skill={selectedSkill}
                      onClose={() => setSelectedId(null)}
                      onSaved={(updated) => {
                        setSkills((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
                      }}
                      onInstall={async (id) => {
                        await installSkill(id);
                        const refreshed = await fetchSkills();
                        setSkills(refreshed);
                      }}
                      onUninstall={async (id) => {
                        await uninstallSkill(id);
                        const refreshed = await fetchSkills();
                        setSkills(refreshed);
                      }}
                      onDelete={async (id) => {
                        setSelectedId(null);
                        setSkills((prev) => prev.filter((s) => s.id !== id));
                        await deleteSkill(id);
                        const refreshed = await fetchSkills();
                        setSkills(refreshed);
                        onSkillsChanged?.();
                      }}
                    />
                  )}
                </div>
              )}
            </>
          ) : subTab === "create" ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8">
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
          ) : subTab === "review" ? (
            <ReviewQueue />
          ) : null}
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
      <SubmitSkillModal
        open={showSubmit}
        onClose={() => setShowSubmit(false)}
        skill={selectedSkill}
        onSubmitted={() => {}}
      />
    </>
  );
}
