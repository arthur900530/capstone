import { useState, useEffect, useMemo } from "react";
import { Plus, Check, Loader2, CloudDownload } from "lucide-react";
import * as Icons from "lucide-react";
import { fetchSkills, browseMarketplaceSkills, installSkill } from "../../services/api";
import PLUGINS from "../../data/plugins";

export default function SkillGraph({ pluginIds, skillIds, onToggleSkill }) {
  const [skillLoad, setSkillLoad] = useState({
    key: null,
    skills: [],
  });
  const [hoveredNode, setHoveredNode] = useState(null);
  const [installing, setInstalling] = useState(null);
  const pluginKey = pluginIds.join(",");
  const loading = skillLoad.key !== pluginKey;
  const cloudSkills = useMemo(
    () => (loading ? [] : skillLoad.skills),
    [loading, skillLoad.skills],
  );

  const selectedPlugins = PLUGINS.filter((p) => pluginIds.includes(p.id));
  const primaryPlugin = selectedPlugins[0];
  const PrimaryIcon = Icons[primaryPlugin?.icon] || Icons.Bot;

  useEffect(() => {
    let cancelled = false;
    browseMarketplaceSkills({ status: "published" })
      .then((res) => res.items || res.skills || res || [])
      .catch(() => fetchSkills().catch(() => []))
      .then((skills) => {
        if (cancelled) return;
        const list = Array.isArray(skills) ? skills : [];
        setSkillLoad({
          key: pluginKey,
          skills: list.filter((s) => !skillIds.includes(s.id || s.slug)),
        });
      })
      .catch(() => {
        if (!cancelled) setSkillLoad({ key: pluginKey, skills: [] });
      });
    return () => {
      cancelled = true;
    };
  }, [pluginKey, skillIds]);

  const handleAddSkill = async (node) => {
    onToggleSkill(node.id);
    // Try to install from marketplace
    if (node.slug) {
      setInstalling(node.id);
      try {
        await installSkill(node.slug);
      } catch {
        /* still added locally */
      }
      setInstalling(null);
    }
    // Remove from suggestions
    setSkillLoad((prev) => ({
      ...prev,
      skills: prev.skills.filter((s) => (s.id || s.slug) !== node.id),
    }));
  };

  const graphSize = 520;
  const cx = graphSize / 2;
  const cy = graphSize / 2;
  const innerRadius = 130;
  const outerRadius = 215;

  const activeNodes = useMemo(() => {
    const count = Math.max(skillIds.length, 1);
    return skillIds.map((sid, i) => {
      const angle = (2 * Math.PI * i) / count - Math.PI / 2;
      return { id: sid, label: sid, x: cx + innerRadius * Math.cos(angle), y: cy + innerRadius * Math.sin(angle), active: true };
    });
  }, [skillIds, cx, cy]);

  const suggestedNodes = useMemo(() => {
    const suggestions = cloudSkills.slice(0, 8);
    const count = Math.max(suggestions.length, 1);
    return suggestions.map((s, i) => {
      const angle = (2 * Math.PI * i) / count - Math.PI / 2;
      const id = s.id || s.slug || s.name;
      return {
        id,
        slug: s.slug,
        label: s.name || id,
        description: s.description,
        x: cx + outerRadius * Math.cos(angle),
        y: cy + outerRadius * Math.sin(angle),
        active: false,
      };
    });
  }, [cloudSkills, cx, cy]);

  if (loading) {
    return (
      <div className="mt-3 flex items-center justify-center rounded-xl border border-border/40 bg-surface py-16">
        <Loader2 size={20} className="animate-spin text-accent-teal" />
        <span className="ml-2 text-sm text-text-muted">Loading cloud skills...</span>
      </div>
    );
  }

  return (
    <div className="mt-3 rounded-xl border border-border/40 bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-xs text-text-muted">
          <span className="text-accent-teal">Inner ring</span> = active skills &middot;
          <span className="text-text-secondary ml-1">Outer ring</span> = cloud suggestions (click to add &amp; install)
        </p>
      </div>

      <div className="relative mx-auto overflow-hidden" style={{ width: graphSize, height: graphSize }}>
        {/* Background rings */}
        <svg width={graphSize} height={graphSize} className="absolute inset-0">
          <circle cx={cx} cy={cy} r={innerRadius} fill="none" stroke="rgb(45,155,173)" strokeOpacity={0.08} strokeWidth={1} strokeDasharray="4 4" />
          <circle cx={cx} cy={cy} r={outerRadius} fill="none" stroke="rgb(100,100,120)" strokeOpacity={0.08} strokeWidth={1} strokeDasharray="4 4" />

          {/* Lines to active skills */}
          {activeNodes.map((node) => (
            <line key={`la-${node.id}`} x1={cx} y1={cy} x2={node.x} y2={node.y}
              stroke="rgb(45,155,173)" strokeOpacity={0.25} strokeWidth={1.5} />
          ))}
          {/* Dashed lines to suggestions */}
          {suggestedNodes.map((node) => (
            <line key={`ls-${node.id}`} x1={cx} y1={cy} x2={node.x} y2={node.y}
              stroke="rgb(100,100,120)" strokeOpacity={hoveredNode === node.id ? 0.3 : 0.08} strokeWidth={1}
              strokeDasharray="3 4" className="transition-all duration-200" />
          ))}
        </svg>

        {/* Center node */}
        <div
          className="absolute flex flex-col items-center justify-center rounded-full border-2 border-accent-teal bg-accent-teal/10"
          style={{ width: 80, height: 80, left: cx - 40, top: cy - 40 }}
        >
          <PrimaryIcon size={24} className="text-accent-teal" />
          <span className="mt-0.5 max-w-[70px] truncate text-center text-[9px] font-bold text-accent-teal leading-tight">
            {selectedPlugins.length > 1
              ? `${selectedPlugins.length} plugins`
              : primaryPlugin?.name?.split(" ")[0] || "Plugin"}
          </span>
        </div>

        {/* Active skill nodes */}
        {activeNodes.map((node) => (
          <button
            key={node.id}
            onClick={() => onToggleSkill(node.id)}
            onMouseEnter={() => setHoveredNode(node.id)}
            onMouseLeave={() => setHoveredNode(null)}
            className="group absolute flex items-center justify-center rounded-full border border-accent-teal/60 bg-accent-teal/15 transition-all hover:scale-110 hover:bg-accent-teal/25"
            style={{ width: 64, height: 64, left: node.x - 32, top: node.y - 32 }}
            title={`${node.label} (click to remove)`}
          >
            <div className="flex flex-col items-center px-1">
              <Check size={13} className="text-accent-teal" />
              <span className="mt-0.5 max-w-[56px] truncate text-center text-[9px] font-semibold text-accent-teal leading-tight">
                {node.label}
              </span>
            </div>
          </button>
        ))}

        {/* Suggested skill nodes */}
        {suggestedNodes.map((node) => (
          <button
            key={node.id}
            onClick={() => handleAddSkill(node)}
            onMouseEnter={() => setHoveredNode(node.id)}
            onMouseLeave={() => setHoveredNode(null)}
            className="group absolute flex items-center justify-center rounded-full border border-border/30 bg-workspace/80 transition-all hover:scale-110 hover:border-accent-teal/50 hover:bg-accent-teal/10"
            style={{ width: 60, height: 60, left: node.x - 30, top: node.y - 30 }}
            title={node.description || node.label}
          >
            <div className="flex flex-col items-center px-1">
              {installing === node.id ? (
                <Loader2 size={12} className="animate-spin text-accent-teal" />
              ) : (
                <CloudDownload size={12} className="text-text-muted/60 group-hover:text-accent-teal" />
              )}
              <span className="mt-0.5 max-w-[52px] truncate text-center text-[9px] font-medium text-text-muted/80 leading-tight group-hover:text-accent-teal">
                {node.label}
              </span>
            </div>
          </button>
        ))}

        {/* Tooltip */}
        {hoveredNode && (() => {
          const node = [...activeNodes, ...suggestedNodes].find((n) => n.id === hoveredNode);
          if (!node) return null;
          const left = Math.min(node.x + 36, graphSize - 200);
          const top = Math.max(node.y - 20, 8);
          return (
            <div
              className="absolute z-10 max-w-52 rounded-lg border border-border/40 bg-charcoal px-3 py-2 shadow-xl pointer-events-none"
              style={{ left, top }}
            >
              <p className="text-[11px] font-semibold text-text-primary">{node.label}</p>
              {node.description && (
                <p className="mt-0.5 text-[10px] text-text-muted line-clamp-2">{node.description}</p>
              )}
              <p className="mt-1 text-[10px] text-accent-teal">
                {node.active ? "Click to remove" : "Click to add & install"}
              </p>
            </div>
          );
        })()}
      </div>

      {cloudSkills.length === 0 && suggestedNodes.length === 0 && (
        <p className="mt-2 text-center text-xs text-text-muted/60">
          No cloud skills available. Start the backend to see suggestions.
        </p>
      )}
    </div>
  );
}
