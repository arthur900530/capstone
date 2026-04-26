# Technical Contribution Evidence

Basis: local git history through 2026-04-26 after fetching `origin/main` and `origin/andrew`. This treats Sylindril as the contributor recorded in git as `Aditya Kumar <adityakumar2001@outlook.com>`. Merge commits are not counted as implementation work; the evidence below is based on authored commits, path-specific history, numstat, and current-line blame.

## Summary

No overall rank is asserted here; the feature-level history below shows where the quantities came from. Contributor rows are alphabetical.

Repository-wide commit counts:

| Contributor | Commits | Notes |
|---|---:|---|
| Andrew Zhang | 3 | 2 bugfix commits on `origin/andrew`, plus PR #15 merge commit |
| Aditya Kumar / Sylindril | 173 | `Aditya Kumar <adityakumar2001@outlook.com>` |
| Arthur Chien | 39 | 37 plus 2 across two emails |
| Aspen Chen | 32 | 28 plus 4 across two author names |
| Danni Qu | 8 | `Danni Qu <angelaqu129@gmail.com>` |
| Hin Kit Eric Wong | 6 | 5 plus 1 across two machine-local emails |
| Yuling | 11 | `Yuling <yuling@YulingdeMacBook-Air-2.local>` |

Main product-path quantities:

| Contributor | Non-merge commits | Lines added | Lines deleted | Current blamed lines |
|---|---:|---:|---:|---:|
| Andrew Zhang | 2 | 168 | 140 | N/A; PR #17 is open |
| Aditya Kumar / Sylindril | 163 | 15,622 | 6,403 | 10,766 |
| Arthur Chien | 26 | 8,316 | 1,183 | 5,945 |
| Aspen Chen | 21 | 7,719 | 388 | 7,244 |
| Danni Qu | 5 | 539 | 87 | 460 |
| Hin Kit Eric Wong | 5 | 503 | 59 | 356 |
| Yuling | 10 | 575 | 61 | 555 |

Focused subsystem quantities:

| Subsystem | Contributor | Non-merge commits | Lines added | Lines deleted | Current blamed lines |
|---|---|---:|---:|---:|---:|
| Demo simulator | Aditya Kumar / Sylindril | 17 | 1,694 | 214 | 1,434 |
| Demo simulator | Andrew Zhang | 1 | 16 | 28 | N/A; PR #17 is open |
| Journey / wizard / employee / skill UX | Andrew Zhang | 1 | 28 | 8 | N/A; PR #17 is open |
| Journey / wizard / employee / skill UX | Aditya Kumar / Sylindril | 89 | 6,404 | 1,182 | 5,167 |
| Journey / wizard / employee / skill UX | Arthur Chien | 10 | 404 | 78 | 369 |
| Journey / wizard / employee / skill UX | Aspen Chen | 7 | 701 | 10 | 693 |
| Journey / wizard / employee / skill UX | Yuling | 3 | 235 | 10 | 235 |
| Reflexion agent | Arthur Chien | 4 | 1,494 | 4 | 1,251 |
| Reflexion agent | Aspen Chen | 8 | 529 | 39 | 516 |
| Reflexion agent | Hin Kit Eric Wong | 5 | 4,853 | 212 | 4,843 |
| Reflexion agent | Yuling | 3 | 155 | 12 | 154 |

Open PR quantities:

| PR / Branch | Contributor | Commits | Files changed | Lines added | Lines deleted | Status |
|---|---|---:|---:|---:|---:|---|
| PR #17 / `origin/andrew` | Andrew Zhang | 2 | 8 | 192 | 140 | Open against `main` |

## Contributor Evidence

**Andrew Zhang.** Andrew's latest open PR #17 contributes bugfixes for frontend lint and hook-ordering issues: `8a7632f` fixes `FileEditBlock` hook-ordering lint errors, and `25766f6` fixes React Compiler lint issues in editor, browser-scene, wizard, and version-history flows. The PR changes 8 files with 192 insertions and 140 deletions, including extracting editor canvas helper logic into `frontend/src/components/editorCanvasUtils.js`. Andrew also authored merge commit `2370930` for PR #15; consistent with the basis above, that merge commit is listed in commit totals but not treated as implementation work.

**Aditya Kumar / Sylindril.** Sylindril/Aditya authored the core employee journey and shell: the router/context/dashboard setup (`c39a01c`, `835fd27`, `dc5a6f5`, `f37a719`), the creation wizard route and employee page (`46bebfb`, `692bccb`), the initial wizard steps (`8cf83d0`, `f032dd0`, `081115c`), local employee persistence (`664b3db`), backend employee model/schema/API (`510dfbc`, `23ea2cc`, `14bf60e`), and the later swap from localStorage to backend API (`0b234a8`).

The wizard's skill and description evolution is concentrated in Aditya commits: plugin arrays and multi-plugin UI (`e77adeb`, `5a237d3`), radial/list skill graph work (`a0f23d6`, `90ceb5d`, `4fa815f`), reusable skill browser and Learn Skills step (`69f7dc7`, `d11c78e`), model-picker hardening and description flow (`2467882`, `6fb25fc`, `f171847`, `c0247ef`, `6ae6472`, `7c239f9`, `19224fb`), and the System Prompt tab (`ccc0c82`, `fcb11a8`, `2914094`). Path-specific evidence for wizard/employee/skill UX shows 6,404 added / 1,182 deleted lines over 89 Aditya commits, with current blame of 5,170 Aditya lines versus 693 Aspen, 370 Arthur, and 8 Yuling.

Sylindril/Aditya authored the full demo simulator design/implementation: CSS animation foundation (`5679c5b`), event processor (`9cc7044`), macOS-style window and taskbar (`b33dbec`, `754d2a6`), root simulator (`9812c78`), browser/terminal/editor/notepad scenes (`09315fb`, `05f655f`, `dad57fa`, `5eb3272`), thinking/confidence/report overlays (`b6af9e7`), mock stream and chat forwarding (`41a8d74`, `c580ad2`), and real-data wiring across scenes (`2775bd3`, `f31fec9`, `3aee402`, `a9123ee`, `7707d29`, `47bcec8`, `7740d4c`). For these paths, history and current blame show only Aditya: 1,694 added / 214 deleted lines and 1,434 current lines.

Aditya also delivered major marketplace, infrastructure, and safety work: DB-backed marketplace/schema/services (`08661bc`, `e916393`, `25c1b39`, `22c89b3`, `293db7b`), submission/review/install workflows (`b85f7a7`, `8c66776`, `0235dbd`, `accdc8b`), runtime fallbacks (`ba25b4b`, `a9f973e`, `850109b`, `86a356b`), start/config improvements (`56ab9d8`, `062359b`, `2a7e999`, `ab597d8`, `4c524d3`, `0f7974e`), and security fixes for path traversal and storage handling (`27ca84f`, `cd146b0`, `20e1627`).

**Arthur Chien.** Arthur contributed the initial repo/chat baseline, early skill-selection UI, Skill Ingestor integration, agent refactoring, workspace sidebar/canvas edit visualization, real-time editor PDF/Markdown support, quick-chat relocation to employee pages, SSE filtering, the Project Files subtab, and UI/layout polish (`8dcdc85`, `2a3a0af`, `91f05f6`, `15e93b9`, `86d234a`, `f9099b5`, `ddb1382`, `3e521ab`, `225a2a9`, `d3a6ed2`, `8d507e5`, `a177a10`, `fed2175`, `9730872`).

**Aspen Chen.** Aspen contributed multimodal skill-ingestion integration, OpenHands integration, backend-connected skill selection with a reflexion toggle, Docker workspace integration, browser live view/path selection, persona injection and persistent memory, and the report-card/metrics/trajectory system including LLM induction and user ratings (`0a3e53c`, `a11af01`, `6dc8185`, `fb34ff4`, `6472d94`, `7a06bc6`, `e3d89b8`, `0356dd7`, `6678b89`, `365979c`, `98d6a3b`, `488e008`).

**Danni Qu / Angela.** Danni/Angela contributed the skill evaluation pipeline, run button, auto-refresh UI, agent skill mapper/evaluation workflow, and OpenAI base URL config (`db6cf63`, `45ab6d1`, `df87bcf`, `0f97e06`, `83a81a6`).

**Hin Kit Eric Wong.** Hin Kit Eric Wong has a substantial reflexion-specific history across `backend/reflexion_agent` and `backend/reflexion_memory.json`: 4,853 added / 212 deleted lines over 5 non-merge commits, with 4,843 current blamed lines in those paths. The commits are `f9103c5` for reflexion agent/evaluator/reflector bug and logic fixes, `d4941b4` for unit pytest coverage, `7d94742` for reflexion docs plus a Layer 3 test artifact, `640b681` for debug logging, live-testing documentation, and run artifacts, and `fb31357` for step-ceiling and evaluator prompt tuning. Separately, `d0cde9f` filters irrelevant agent runtime metadata artifacts from the mounted workspace through server, workspace panel, and API changes.

**Yuling.** Yuling contributed stream termination/final-answer fixes, OpenAI model config, first-run environment fixes, wizard back-button and skill-card bugfixes, an LLM similarity check in the skill evaluation framework, auto skill selection, and selected-skill agent context (`7310ee6`, `88d03f4`, `abe60bb`, `499a796`, `5066069`, `1c31b49`, `65f74d8`, `30039ed`, `78ff9cc`).

## Reproduction

Run `bash scripts/contribution_evidence.sh` from the repository root to regenerate the headline tables. The script uses `--all`, so it includes local and remote refs such as `origin/andrew`. Raw path-specific commit lists are omitted by default because the tables and cited commit tags are easier to read; run `INCLUDE_COMMIT_HISTORY=1 bash scripts/contribution_evidence.sh` if a full audit trail is needed. The core commands are:

```bash
git shortlog -sne --all | sort -k2,2 -k3,3
git log --all --no-merges --numstat --format='@@@%aN' -- frontend/src backend/routers backend/db backend/services backend/alembic start.sh .env.template backend/server.py backend/reflexion_agent/agent.py backend/metrics.py backend/trajectory.py backend/trajectory_llm.py backend/config.py.example
git ls-files frontend/src backend/routers backend/db backend/services backend/alembic backend/server.py backend/reflexion_agent/agent.py backend/metrics.py backend/trajectory.py backend/trajectory_llm.py backend/config.py.example start.sh .env.template | xargs -I{} git blame --line-porcelain -- {}
```
