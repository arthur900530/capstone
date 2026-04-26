import { useState, useCallback, useEffect, useRef } from "react";

const MAX_VERSIONS = 20;
const KEY_PREFIX = "skill_versions_";

function loadVersions(skillId) {
  try {
    const raw = localStorage.getItem(KEY_PREFIX + skillId);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveVersions(skillId, versions) {
  localStorage.setItem(KEY_PREFIX + skillId, JSON.stringify(versions));
}

export default function useVersionHistory(skillId, currentSkillData) {
  const initializedRef = useRef(null);

  const [versions, setVersions] = useState(() => {
    const stored = loadVersions(skillId);
    if (stored && stored.length > 0) return stored;
    if (!currentSkillData) return [];
    return [{
      version: 1,
      name: currentSkillData.name,
      description: currentSkillData.description,
      definition: currentSkillData.definition,
      savedAt: currentSkillData.updated_at || new Date().toISOString(),
      submitted: false,
    }];
  });

  const [activeVersion, setActiveVersion] = useState(() => {
    const stored = loadVersions(skillId);
    if (stored && stored.length > 0) return stored[stored.length - 1].version;
    return 1;
  });

  // Re-initialize when skill ID changes
  useEffect(() => {
    if (initializedRef.current === skillId) return;
    initializedRef.current = skillId;

    const resetTimer = window.setTimeout(() => {
      const stored = loadVersions(skillId);
      if (stored && stored.length > 0) {
        setVersions(stored);
        setActiveVersion(stored[stored.length - 1].version);
      } else if (currentSkillData) {
        const v1 = [{
          version: 1,
          name: currentSkillData.name,
          description: currentSkillData.description,
          definition: currentSkillData.definition,
          savedAt: currentSkillData.updated_at || new Date().toISOString(),
          submitted: false,
        }];
        setVersions(v1);
        setActiveVersion(1);
        saveVersions(skillId, v1);
      }
    }, 0);

    return () => window.clearTimeout(resetTimer);
  }, [skillId, currentSkillData]);

  // Persist on change
  useEffect(() => {
    if (versions.length > 0) {
      saveVersions(skillId, versions);
    }
  }, [skillId, versions]);

  const addVersion = useCallback((data) => {
    let nextNum;
    setVersions((prev) => {
      nextNum = prev.length > 0
        ? prev[prev.length - 1].version + 1
        : 1;
      const entry = {
        version: nextNum,
        name: data.name,
        description: data.description,
        definition: data.definition,
        savedAt: new Date().toISOString(),
        submitted: false,
      };
      return [...prev, entry].slice(-MAX_VERSIONS);
    });
    // setActiveVersion runs after the state update is queued
    setActiveVersion(nextNum);
    return nextNum;
  }, []);

  const markSubmitted = useCallback((versionNum) => {
    setVersions((prev) =>
      prev.map((v) =>
        v.version === versionNum ? { ...v, submitted: true } : v
      )
    );
  }, []);

  const getVersion = useCallback((versionNum) => {
    return versions.find((v) => v.version === versionNum) || null;
  }, [versions]);

  const latestVersion = versions.length > 0
    ? versions[versions.length - 1].version
    : 1;

  return {
    versions,
    activeVersion,
    setActiveVersion,
    addVersion,
    markSubmitted,
    getVersion,
    latestVersion,
  };
}
