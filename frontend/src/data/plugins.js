/**
 * Static plugin definitions mapping friendly roles to skill IDs.
 * Each plugin bundles a set of skills into a coherent "role" that
 * non-technical users can understand without knowing the underlying tools.
 */

const PLUGINS = [
  {
    id: "research-analyst",
    name: "Research Analyst",
    description: "Searches SEC filings, financial news, and earnings reports",
    bestFor: "Equity research, market intelligence, earnings analysis",
    icon: "TrendingUp",
    skillIds: ["web-search", "edgar-search", "parse-html", "retrieve-info"],
    defaultModel: "openai/gpt-5.4",
  },
  {
    id: "data-engineer",
    name: "Data Engineer",
    description: "Transforms, validates, and pipelines structured data",
    bestFor: "CSV cleanup, schema validation, ETL pipelines",
    icon: "Database",
    skillIds: ["parse-html", "retrieve-info"],
    defaultModel: "openai/gpt-5.4",
  },
  {
    id: "compliance-reviewer",
    name: "Compliance Reviewer",
    description: "Reviews documents against regulatory frameworks and flags risks",
    bestFor: "Policy review, regulatory gap analysis, audit prep",
    icon: "ShieldCheck",
    skillIds: ["retrieve-info", "web-search"],
    defaultModel: "openai/gpt-5.4",
  },
  {
    id: "report-writer",
    name: "Report Writer",
    description: "Drafts structured reports, memos, and executive summaries",
    bestFor: "Earnings summaries, investment memos, status reports",
    icon: "FileText",
    skillIds: ["retrieve-info"],
    defaultModel: "openai/gpt-5.4",
  },
  {
    id: "general-assistant",
    name: "General Assistant",
    description: "Flexible helper for ad-hoc questions and tasks",
    bestFor: "Quick lookups, brainstorming, drafting emails",
    icon: "Sparkles",
    skillIds: [],
    defaultModel: "openai/gpt-5.4",
  },
];

export default PLUGINS;
