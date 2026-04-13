/**
 * Pre-built employee templates for the "Hire from Pool" gallery.
 * Each template pre-fills the creation wizard with sensible defaults.
 */

const EMPLOYEE_TEMPLATES = [
  {
    id: "equity-analyst-template",
    name: "Equity Research Analyst",
    description: "Pre-configured for deep equity research with SEC filing access",
    pluginId: "research-analyst",
    suggestedName: "Sarah",
    avatar: "TrendingUp",
  },
  {
    id: "data-pipeline-template",
    name: "Data Pipeline Engineer",
    description: "Cleans and transforms structured data for downstream analysis",
    pluginId: "data-engineer",
    suggestedName: "Marcus",
    avatar: "Database",
  },
  {
    id: "compliance-analyst-template",
    name: "Compliance Analyst",
    description: "Reviews documents and flags regulatory risks automatically",
    pluginId: "compliance-reviewer",
    suggestedName: "Alex",
    avatar: "ShieldCheck",
  },
  {
    id: "report-drafter-template",
    name: "Report Drafter",
    description: "Writes structured memos, summaries, and executive briefs",
    pluginId: "report-writer",
    suggestedName: "Jordan",
    avatar: "FileText",
  },
];

export default EMPLOYEE_TEMPLATES;
