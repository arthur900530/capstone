import SkillsView from "../components/skills/SkillsView";
import { useApp } from "../context/AppContext";

export default function PluginsPage() {
  const { refreshSkills } = useApp();
  return <SkillsView onSkillsChanged={refreshSkills} />;
}
