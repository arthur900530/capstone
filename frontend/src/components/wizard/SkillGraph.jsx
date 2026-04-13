import { useState, useEffect, useMemo } from "react";
import { Plus, Check, Loader2 } from "lucide-react";
import * as Icons from "lucide-react";
import { browseMarketplaceSkills } from "../../services/api";
import PLUGINS from "../../data/plugins";

/**
 * Radial graph showing the current plugin at center with active skills
 * in an inner ring and suggested cloud skills in an outer ring.
 * Click a suggestion to add it.
 */
export default function SkillGraph({
  pluginId,
  skillIds,
  onToggleSkill,
}) {
  const [cloudSkills, setCloudSkills] = useState([]);
  const [loading, setLoading] = useState(true);
  const [hoveredNode, setHoveredNode] = useState(null);

  const plugin = PLUGINS.find((p) => p.id === pluginId);
  const PluginIcon = Icons[plugin?.icon] || Icons.Bot;

  useEffect(() => {
    setLoading(true);
    browseMarketplaceSkills({ status: "published" })
      .then((res) => {
        const skills = res.skills || res || [];
        setCloudSkills(
          skills.filter((s) => !skillIds.includes(s.id || s.slug)),
        );
      })
      .catch(() => setCloudSkills([]))
      .finally(() => setLoading(false));
  }, [pluginId]);

  // Layout: center node + inner ring (active skills) + outer ring (suggestions)
  const graphSize = 480;
  const cx = graphSize / 2;
  const cy = graphSize / 2;
  const innerRadius = 110;
  const outerRadius = 195;

  const activeNodes = useMemo(
    () =>
      skillIds.map((sid, i) => {
        const angle = (2 * Math.PI * i) / Math.max(skillIds.length, 1) - Math.PI / 2;
        return {
          id: sid,
          label: sid,
          x: cx + innerRadius * Math.cos(angle),
          y: cy + innerRadius * Math.sin(angle),
          active: true,
        };
      }),
    [skillIds, cx, cy],
  );

  const suggestedNodes = useMemo(() => {
    const suggestions = cloudSkills.slice(0, 10);
    return suggestions.map((s, i) => {
      const angle = (2 * Math.PI * i) / Math.max(suggestions.length, 1) - Math.PI / 2;
      const id = s.id || s.slug || s.name;
      return {
        id,
        label: s.name || id,
        description: s.description,
        x: cx + outerRadius * Math.cos(angle),
        y: cy + outerRadius * Math.sin(angle),
        active: false,
      };
    });
  }, [cloudSkills, cx, cy]);

  const allNodes = [...activeNodes, ...suggestedNodes];

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 size={20} className="animate-spin text-accent-teal" />
        <span className="ml-2 text-sm text-text-muted">Loading cloud skills...</span>
      </div>
    );
  }

  return (
    <div className="mt-3 rounded-xl border border-border/40 bg-surface p-4">
      <p className="mb-2 text-xs text-text-muted">
        Suggested skills from the cloud. Click to add.
      </p>

      <div className="relative mx-auto" style={{ width: graphSize, height: graphSize }}>
        <svg
          width={graphSize}
          height={graphSize}
          className="absolute inset-0"
        >
          {/* Lines from center to active skills */}
          {activeNodes.map((node) => (
            <line
              key={`line-active-${node.id}`}
              x1={cx}
              y1={cy}
              x2={node.x}
              y2={node.y}
              stroke="rgb(45,155,173)"
              strokeOpacity={0.3}
              strokeWidth={1.5}
            />
          ))}
          {/* Dashed lines from center to suggestions */}
          {suggestedNodes.map((node) => (
            <line
              key={`line-sug-${node.id}`}
              x1={cx}
              y1={cy}
              x2={node.x}
              y2={node.y}
              stroke="rgb(45,155,173)"
              strokeOpacity={hoveredNode === node.id ? 0.4 : 0.1}
              strokeWidth={1}
              strokeDasharray="4 3"
              className="transition-all duration-200"
            />
          ))}
        </svg>

        {/* Center node (plugin) */}
        <div
          className="absolute flex flex-col items-center justify-center rounded-full border-2 border-accent-teal bg-accent-teal/10"
          style={{
            width: 72,
            height: 72,
            left: cx - 36,
            top: cy - 36,
          }}
        >
          <PluginIcon size={22} className="text-accent-teal" />
          <span className="mt-0.5 text-[9px] font-semibold text-accent-teal leading-tight text-center px-1 truncate max-w-[64px]">
            {plugin?.name?.split(" ")[0]}
          </span>
        </div>

        {/* Active skill nodes (inner ring) */}
        {activeNodes.map((node) => (
          <button
            key={node.id}
            onClick={() => onToggleSkill(node.id)}
            onMouseEnter={() => setHoveredNode(node.id)}
            onMouseLeave={() => setHoveredNode(null)}
            className="group absolute flex items-center justify-center rounded-full border border-accent-teal bg-accent-teal/15 transition-all hover:bg-accent-teal/25 hover:scale-110"
            style={{
              width: 56,
              height: 56,
              left: node.x - 28,
              top: node.y - 28,
            }}
            title={`${node.label} (click to remove)`}
          >
            <div className="flex flex-col items-center">
              <Check size={12} className="text-accent-teal" />
              <span className="text-[8px] font-medium text-accent-teal leading-tight text-center max-w-[48px] truncate">
                {node.label}
              </span>
            </div>
          </button>
        ))}

        {/* Suggested skill nodes (outer ring) */}
        {suggestedNodes.map((node) => (
          <button
            key={node.id}
            onClick={() => onToggleSkill(node.id)}
            onMouseEnter={() => setHoveredNode(node.id)}
            onMouseLeave={() => setHoveredNode(null)}
            className="group absolute flex items-center justify-center rounded-full border border-border/40 bg-workspace transition-all hover:border-accent-teal/60 hover:bg-accent-teal/10 hover:scale-110"
            style={{
              width: 52,
              height: 52,
              left: node.x - 26,
              top: node.y - 26,
            }}
            title={node.description || node.label}
          >
            <div className="flex flex-col items-center">
              <Plus size={11} className="text-text-muted group-hover:text-accent-teal" />
              <span className="text-[8px] font-medium text-text-muted leading-tight text-center max-w-[44px] truncate group-hover:text-accent-teal">
                {node.label}
              </span>
            </div>
          </button>
        ))}

        {/* Tooltip for hovered node */}
        {hoveredNode && (() => {
          const node = allNodes.find((n) => n.id === hoveredNode);
          if (!node?.description) return null;
          return (
            <div
              className="absolute z-10 max-w-48 rounded-lg border border-border/40 bg-charcoal px-3 py-2 text-[11px] text-text-secondary shadow-xl pointer-events-none"
              style={{ left: node.x + 30, top: node.y - 16 }}
            >
              <p className="font-medium text-text-primary">{node.label}</p>
              <p className="mt-0.5 line-clamp-2">{node.description}</p>
            </div>
          );
        })()}
      </div>

      {cloudSkills.length === 0 && (
        <p className="mt-2 text-center text-xs text-text-muted/60">
          No cloud skills available. Start the backend to see suggestions.
        </p>
      )}
    </div>
  );
}
