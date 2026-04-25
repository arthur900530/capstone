# Technical Contribution Evidence

Basis: local git history through 2026-04-25 on branch `describe-to-system-prompt`. This treats Sylindril as the contributor recorded in git as `Aditya Kumar <adityakumar2001@outlook.com>`. Merge commits are not counted as implementation work; the evidence below is based on authored commits, path-specific history, numstat, and current-line blame.

## Summary

No overall rank is asserted here; the feature-level history below shows where the quantities came from. Contributor rows are alphabetical.

Repository-wide commit counts:

| Contributor | Commits | Notes |
|---|---:|---|
| Aditya Kumar / Sylindril | 170 | `Aditya Kumar <adityakumar2001@outlook.com>` |
| Arthur Chien | 39 | 37 plus 2 across two emails |
| Aspen Chen | 32 | 28 plus 4 across two author names |
| Danni Qu | 8 | `Danni Qu <angelaqu129@gmail.com>` |
| Hin Kit Eric Wong | 6 | 5 plus 1 across two machine-local emails |
| Yuling | 11 | `Yuling <yuling@YulingdeMacBook-Air-2.local>` |

Main product-path quantities:

| Contributor | Non-merge commits | Lines added | Lines deleted | Current blamed lines |
|---|---:|---:|---:|---:|
| Aditya Kumar / Sylindril | 163 | 15,622 | 6,403 | 10,774 |
| Arthur Chien | 26 | 8,316 | 1,183 | 5,947 |
| Aspen Chen | 21 | 7,719 | 388 | 7,249 |
| Danni Qu | 5 | 539 | 87 | 460 |
| Hin Kit Eric Wong | 5 | 503 | 59 | 356 |
| Yuling | 10 | 575 | 61 | 264 |

Focused subsystem quantities:

| Subsystem | Contributor | Non-merge commits | Lines added | Lines deleted | Current blamed lines |
|---|---|---:|---:|---:|---:|
| Demo simulator | Aditya Kumar / Sylindril | 17 | 1,694 | 214 | 1,434 |
| Journey / wizard / employee / skill UX | Aditya Kumar / Sylindril | 89 | 6,404 | 1,182 | 5,170 |
| Journey / wizard / employee / skill UX | Arthur Chien | 10 | 404 | 78 | 370 |
| Journey / wizard / employee / skill UX | Aspen Chen | 7 | 701 | 10 | 693 |
| Journey / wizard / employee / skill UX | Yuling | 3 | 235 | 10 | 8 |
| Reflexion agent | Arthur Chien | 4 | 1,494 | 4 | 1,251 |
| Reflexion agent | Aspen Chen | 8 | 529 | 39 | 517 |
| Reflexion agent | Hin Kit Eric Wong | 5 | 4,853 | 212 | 4,843 |
| Reflexion agent | Yuling | 3 | 155 | 12 | 142 |

## Contributor Evidence

**Aditya Kumar / Sylindril.** Sylindril/Aditya authored the core employee journey and shell: the router/context/dashboard setup (`c39a01c`, `835fd27`, `dc5a6f5`, `f37a719`), the creation wizard route and employee page (`46bebfb`, `692bccb`), the initial wizard steps (`8cf83d0`, `f032dd0`, `081115c`), local employee persistence (`664b3db`), backend employee model/schema/API (`510dfbc`, `23ea2cc`, `14bf60e`), and the later swap from localStorage to backend API (`0b234a8`).

The wizard's skill and description evolution is concentrated in Aditya commits: plugin arrays and multi-plugin UI (`e77adeb`, `5a237d3`), radial/list skill graph work (`a0f23d6`, `90ceb5d`, `4fa815f`), reusable skill browser and Learn Skills step (`69f7dc7`, `d11c78e`), model-picker hardening and description flow (`2467882`, `6fb25fc`, `f171847`, `c0247ef`, `6ae6472`, `7c239f9`, `19224fb`), and the System Prompt tab (`ccc0c82`, `fcb11a8`, `2914094`). Path-specific evidence for wizard/employee/skill UX shows 6,404 added / 1,182 deleted lines over 89 Aditya commits, with current blame of 5,170 Aditya lines versus 693 Aspen, 370 Arthur, and 8 Yuling.

Sylindril/Aditya authored the full demo simulator design/implementation: CSS animation foundation (`5679c5b`), event processor (`9cc7044`), macOS-style window and taskbar (`b33dbec`, `754d2a6`), root simulator (`9812c78`), browser/terminal/editor/notepad scenes (`09315fb`, `05f655f`, `dad57fa`, `5eb3272`), thinking/confidence/report overlays (`b6af9e7`), mock stream and chat forwarding (`41a8d74`, `c580ad2`), and real-data wiring across scenes (`2775bd3`, `f31fec9`, `3aee402`, `a9123ee`, `7707d29`, `47bcec8`, `7740d4c`). For these paths, history and current blame show only Aditya: 1,694 added / 214 deleted lines and 1,434 current lines.

Aditya also delivered major marketplace, infrastructure, and safety work: DB-backed marketplace/schema/services (`08661bc`, `e916393`, `25c1b39`, `22c89b3`, `293db7b`), submission/review/install workflows (`b85f7a7`, `8c66776`, `0235dbd`, `accdc8b`), runtime fallbacks (`ba25b4b`, `a9f973e`, `850109b`, `86a356b`), start/config improvements (`56ab9d8`, `062359b`, `2a7e999`, `ab597d8`, `4c524d3`, `0f7974e`), and security fixes for path traversal and storage handling (`27ca84f`, `cd146b0`, `20e1627`).

**Arthur Chien.** Arthur contributed the initial repo/chat/skill-selection baseline, workspace sidebar/canvas edit visualization, real-time editor PDF/Markdown support, quick-chat relocation to employee pages, SSE filtering, the Project Files subtab, and UI/layout polish (`8dcdc85`, `2a3a0af`, `3e521ab`, `225a2a9`, `d3a6ed2`, `8d507e5`, `a177a10`, `fed2175`, `9730872`).

**Aspen Chen.** Aspen contributed OpenHands and Docker workspace integration, browser live view/path selection, persona injection and persistent memory, and the report-card/metrics/trajectory system including LLM induction and user ratings (`a11af01`, `fb34ff4`, `6472d94`, `7a06bc6`, `e3d89b8`, `0356dd7`, `6678b89`, `365979c`, `98d6a3b`, `488e008`).

**Danni Qu.** Danni contributed the skill evaluation pipeline/run UI, agent skill mapper/evaluation workflow, and OpenAI base URL config (`db6cf63`, `df87bcf`, `0f97e06`, `83a81a6`).

**Hin Kit Eric Wong.** Hin Kit Eric Wong has a substantial reflexion-specific history across `backend/reflexion_agent` and `backend/reflexion_memory.json`: 4,853 added / 212 deleted lines over 5 non-merge commits, with 4,843 current blamed lines in those paths. The commits are `f9103c5` for reflexion agent/evaluator/reflector bug and logic fixes, `d4941b4` for unit pytest coverage, `7d94742` for reflexion docs plus a Layer 3 test artifact, `640b681` for debug logging, live-testing documentation, and run artifacts, and `fb31357` for step-ceiling and evaluator prompt tuning. Separately, `d0cde9f` filters irrelevant agent runtime metadata artifacts from the mounted workspace through server, workspace panel, and API changes.

**Yuling.** Yuling contributed stream termination/final-answer fixes, OpenAI model config, first-run environment fixes, wizard back-button and skill-card bugfixes, auto skill selection, and selected-skill agent context (`7310ee6`, `88d03f4`, `abe60bb`, `499a796`, `5066069`, `1c31b49`, `30039ed`, `78ff9cc`).

## Reproduction

Run `bash scripts/contribution_evidence.sh` from the repository root to regenerate the headline tables. The script uses `--all`, so it includes local and remote refs such as `origin/fix/reflexion-agent-bugs` and `origin/fix/workspace-filebrowser-runtime-noise`. Raw path-specific commit lists are omitted by default because the tables and cited commit tags are easier to read; run `INCLUDE_COMMIT_HISTORY=1 bash scripts/contribution_evidence.sh` if a full audit trail is needed. The core commands are:

```bash
git shortlog -sne --all | sort -k2,2 -k3,3
git log --all --no-merges --numstat --format='@@@%aN' -- frontend/src backend/routers backend/db backend/services backend/alembic start.sh .env.template backend/server.py backend/reflexion_agent/agent.py backend/metrics.py backend/trajectory.py backend/trajectory_llm.py backend/config.py.example
git ls-files frontend/src backend/routers backend/db backend/services backend/alembic backend/server.py backend/reflexion_agent/agent.py backend/metrics.py backend/trajectory.py backend/trajectory_llm.py backend/config.py.example start.sh .env.template | xargs -I{} git blame --line-porcelain -- {}
```
