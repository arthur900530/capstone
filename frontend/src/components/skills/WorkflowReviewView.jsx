import { useEffect, useMemo, useRef, useState } from "react";
import { Sparkles } from "lucide-react";
import WorkflowTree from "../workflow/WorkflowTree";

// Renders the post-train review: source video on the left, extracted
// workflow tree on the right, kept in sync by `timeupdate` events.
//
// Props:
// - workflows : { [slug]: workflow_dict } from POST /api/skills/train
// - files     : [{ name, url }] of session-scoped media (typically one)
// - skills    : [{ id, name, ... }] new skills returned alongside workflows
// (used to label the picker chips)

// Normalize a filename for tolerant matching against an uploaded basename.
// Mirrors backend ``MMSkillTrainer._normalize_basename`` so older
// workflow.json files (with model-emitted noise like "foo.mp400:00") still
// pair with the correct source file on the review screen.
const MEDIA_EXT_RE = /\.(mp4|mov|webm|m4v|avi|mp3|wav|m4a|txt|md|py|sh|json|yaml|yml|csv)/i;
function normalizeBasename(value) {
  if (!value) return "";
  const base = String(value).split(/[\\/]/).pop().trim().toLowerCase();
  const match = base.match(MEDIA_EXT_RE);
  return match ? base.slice(0, match.index + match[0].length) : base;
}

export default function WorkflowReviewView({ workflows, files = [], skills = [] }) {
  const slugs = useMemo(() => Object.keys(workflows || {}), [workflows]);
  const [selectedSlug, setSelectedSlug] = useState(slugs[0] || null);

  useEffect(() => {
    if (!selectedSlug || !workflows?.[selectedSlug]) {
      setSelectedSlug(slugs[0] || null);
    }
  }, [slugs, selectedSlug, workflows]);

  const workflow = selectedSlug ? workflows[selectedSlug] : null;

  // Pick the file the workflow references. Match `source_file` exactly
  // first, then a normalized form (case-insensitive, extension-trimmed) to
  // tolerate model garbling. As a last resort, fall back to assigning the
  // Nth slug to the Nth video so multi-video uploads don't all collapse
  // onto the first file.
  const selectedFile = useMemo(() => {
    if (!files || files.length === 0) return null;

    const sourceFile = workflow?.source_file;
    if (sourceFile) {
      const exact = files.find((f) => f.name === sourceFile);
      if (exact) return exact;
      const norm = normalizeBasename(sourceFile);
      if (norm) {
        const fuzzy = files.find((f) => normalizeBasename(f.name) === norm);
        if (fuzzy) return fuzzy;
      }
    }

    const videos = files.filter((f) =>
      /\.(mp4|mov|webm|m4v|avi)$/i.test(f.name)
    );
    if (videos.length > 0) {
      const idx = Math.max(0, slugs.indexOf(selectedSlug));
      return videos[idx % videos.length];
    }
    return files[0];
  }, [files, workflow?.source_file, slugs, selectedSlug]);

  const videoRef = useRef(null);
  const [currentTime, setCurrentTime] = useState(0);

  useEffect(() => {
    setCurrentTime(0);
  }, [selectedFile?.url]);

  const handleTimeUpdate = () => {
    const t = videoRef.current?.currentTime;
    if (typeof t === "number") setCurrentTime(t);
  };

  const handleSeek = (seconds) => {
    if (!videoRef.current) return;
    videoRef.current.currentTime = Math.max(0, seconds);
    videoRef.current
      .play()
      .catch(() => {
        // Some browsers block autoplay until the user interacts; ignore.
      });
  };

  if (!workflow) {
    return (
      <div className="rounded-lg border border-border/40 bg-charcoal/40 px-4 py-6 text-center text-sm text-text-muted">
        Training finished but no structured workflow was recorded for the
        extracted skills.
      </div>
    );
  }

  const skillById = Object.fromEntries((skills || []).map((s) => [s.id, s]));

  return (
    <div className="space-y-3">
      {slugs.length > 1 ? (
        <div className="flex flex-wrap items-center gap-1.5">
          {slugs.map((slug) => {
            const skill = skillById[slug];
            const label = skill?.name || workflows[slug]?.title || slug;
            const active = slug === selectedSlug;
            return (
              <button
                key={slug}
                onClick={() => setSelectedSlug(slug)}
                className={
                  "inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium transition-colors " +
                  (active
                    ? "bg-accent-teal/20 text-accent-teal"
                    : "bg-charcoal/60 text-text-secondary hover:bg-charcoal/80 hover:text-text-primary")
                }
              >
                <Sparkles size={11} />
                {label}
              </button>
            );
          })}
        </div>
      ) : null}

      <div className="grid gap-3 lg:grid-cols-[1fr_1fr]">
        <div className="space-y-2">
          {selectedFile ? (
            <video
              key={selectedFile.url}
              ref={videoRef}
              src={selectedFile.url}
              controls
              onTimeUpdate={handleTimeUpdate}
              className="aspect-video w-full rounded-lg border border-border/40 bg-black object-contain"
            />
          ) : (
            <div className="flex aspect-video items-center justify-center rounded-lg border border-dashed border-border/40 bg-charcoal/30 text-xs text-text-muted">
              No source media available for review.
            </div>
          )}
          {selectedFile ? (
            <p className="truncate text-[11px] text-text-muted">
              Source: {selectedFile.name}
            </p>
          ) : null}
        </div>

        <div className="space-y-2">
          {workflow.title ? (
            <h4 className="text-sm font-semibold text-text-primary">
              {workflow.title}
            </h4>
          ) : null}
          {workflow.summary ? (
            <p className="text-xs text-text-muted">{workflow.summary}</p>
          ) : null}
          <div className="max-h-[60vh] overflow-y-auto pr-1">
            <WorkflowTree
              nodes={workflow.root_steps || []}
              mode="workflow"
              currentTime={currentTime}
              onSeek={handleSeek}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
