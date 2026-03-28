---
name: prompt-template-definition
description: >
  Define and manage structured multi-line prompt templates for AI agents, specifically for SWE-bench tasks and multimedia skill extraction.
license: MIT
metadata:
  version: "1.0"
triggers:
  - prompt template
  - SWE_BENCH_PROMPT_TEMPLATE
  - MMSkillTrainer_PROMPT_TEMPLATE
---

# Prompt Template Definition

This skill involves defining high-level instructions for AI agents using structured Python strings.

### SWE-bench Problem Solving Template
When creating a prompt for solving software engineering tasks, include:
1. A placeholder for the `{problem_description}`.
2. Specific instructions for outputting the solution (e.g., `/workspace/solution.md`).
3. Logic for skill extraction: identifying reusable components and saving them in a specific `SKILL.md` format under `/workspace/skills/<skill_name>/`.

### Multimedia Skill Extraction Template
When creating a prompt for summarizing multimedia into skills:
1. Instruct the assistant to analyze files and identify demonstrated skills.
2. Mandate the use of tools (`list_skills`, `read_skill`) to check for existing duplicates.
3. Enforce a specific XML-based output format (`<skill_name>` and `<skill_description>`) containing YAML frontmatter and Markdown content.

### Formatting Requirements
- Use triple quotes `"""` for multi-line strings.
- Ensure the YAML frontmatter includes: `name`, `description`, `license`, and `triggers`.
- Use snake_case or hyphen-separated names for variables and skill files.
