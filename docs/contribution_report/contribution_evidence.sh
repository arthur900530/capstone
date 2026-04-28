#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

PRODUCT_PATHS=(
  .github/workflows
  frontend/src
  backend/routers
  backend/db
  backend/services
  backend/tests
  backend/alembic
  start.sh
  .env.template
  backend/.env.example
  backend/server.py
  backend/reflexion_agent
  backend/metrics.py
  backend/trajectory.py
  backend/trajectory_llm.py
  backend/config.py.example
)

EVIDENCE_REF="${EVIDENCE_REF:-origin/main}"
EVIDENCE_EXCLUDE_REGEX="${EVIDENCE_EXCLUDE_REGEX:-(__pycache__/|[.]pyc$|[.]pyo$|[.]json$|[.]md$|/docs/|(^|/)tests?(/|$)|(^|/)test[-_][^/]*[.](py|sh)$|/skill-eval-runs/)}"
ERIC_REASSIGNED_COMMIT="86d234a0b77848e98823ee0050f8f4b7de2ab947"

JOURNEY_PATHS=(
  frontend/src/pages/CreationWizard.jsx
  frontend/src/components/wizard
  frontend/src/components/skills
  frontend/src/components/dashboard
  frontend/src/pages/DashboardPage.jsx
  frontend/src/pages/EmployeePage.jsx
  frontend/src/services/employeeStore.js
  backend/routers/employees.py
  backend/db/models.py
  backend/alembic/versions/003_add_employees_table.py
  backend/alembic/versions/009_add_employee_description.py
)

DEMO_PATHS=(
  frontend/src/components/desktop
  frontend/src/services/mockStream.js
)

REFLEXION_PATHS=(
  backend/reflexion_agent
  backend/reflexion_memory.json
)

BACKEND_API_RUNTIME_PATHS=(
  backend/routers
  backend/db
  backend/services
  backend/alembic
  backend/server.py
  backend/metrics.py
  backend/trajectory.py
  backend/trajectory_llm.py
  backend/config.py.example
  backend/.env.example
  backend/requirements.txt
  backend/reflexion_agent/agent.py
)

AGENT_RUNTIME_PATHS=(
  backend/server.py
  backend/reflexion_agent/agent.py
  backend/config.py.example
  backend/.env.example
  frontend/src/components/BrowserLiveView.jsx
  frontend/src/components/InputBox.jsx
)

CHAT_INTERFACE_PATHS=(
  frontend/src/App.jsx
  frontend/src/components/ChatView.jsx
  frontend/src/components/ChatMessage.jsx
  frontend/src/components/InputBox.jsx
  frontend/src/components/Sidebar.jsx
  frontend/src/components/employee/EmployeeChat.jsx
  frontend/src/services/messageUtils.js
)

WORKSPACE_PROJECT_PATHS=(
  frontend/src/components/EditorCanvas.jsx
  frontend/src/components/FileEditBlock.jsx
  frontend/src/components/FileTreeNode.jsx
  frontend/src/components/BrowserLiveView.jsx
  frontend/src/components/employee/EmployeeProjectFilesTab.jsx
  frontend/src/services/api.js
  backend/routers/employees.py
  backend/server.py
)

REPORT_METRICS_PATHS=(
  backend/metrics.py
  backend/trajectory.py
  backend/trajectory_llm.py
  backend/prompts
  frontend/src/components/employee/EmployeeReportCard.jsx
  frontend/src/components/employee/TaskPerformanceSection.jsx
  frontend/src/components/employee/TaskTrajectoryDrawer.jsx
  frontend/src/components/employee/TrajectoryNodeCard.jsx
  frontend/src/components/MessageRating.jsx
  frontend/src/services/messageUtils.js
  backend/alembic/versions/005_add_task_runs.py
  backend/alembic/versions/006_add_task_run_raw_events.py
  backend/alembic/versions/007_add_task_run_annotations.py
  backend/alembic/versions/008_add_task_run_user_rating.py
)

SKILL_INGESTION_EVALUATION_PATHS=(
  backend/skills_ingestor
  backend/skillsbench/experiments/skill_evaluation_framework.py
  backend/server.py
  frontend/src/components/EvaluationView.jsx
  frontend/src/pages/EvaluationLabPage.jsx
  frontend/src/components/InputBox.jsx
)

EMPLOYEE_DETAIL_PATHS=(
  frontend/src/pages/EmployeePage.jsx
  frontend/src/components/employee
  frontend/src/services/api.js
)

PROJECT_FILES_TAB_PATHS=(
  frontend/src/components/employee/EmployeeProjectFilesTab.jsx
)

METRICS_CORE_PATHS=(
  backend/metrics.py
  backend/trajectory.py
  backend/trajectory_llm.py
  backend/prompts
)

BROWSER_LIVE_VIEW_PATHS=(
  frontend/src/components/BrowserLiveView.jsx
)

REPORT_UI_PATHS=(
  frontend/src/components/employee/EmployeeReportCard.jsx
  frontend/src/components/employee/TaskPerformanceSection.jsx
  frontend/src/components/employee/TaskTrajectoryDrawer.jsx
  frontend/src/components/employee/TrajectoryNodeCard.jsx
  frontend/src/components/MessageRating.jsx
)

print_title() {
  printf '\n== %s ==\n' "$1"
}

grouped_commit_counts() {
  print_title "Repository commit counts grouped by person with attribution corrections"
  git log "$EVIDENCE_REF" --format='%H	%aN	%aE' |
    awk '
      BEGIN { FS = "\t" }
      function normalize_author(author) {
        if (author == "Andrew Zhang" || author == "andrew-yifanzhang") return "Andrew Zhang"
        if (author == "Aditya Kumar") return "Aditya Kumar"
        if (author == "Arthur Chien") return "Arthur Chien"
        if (author == "Aspen Chen" || author == "AspenC") return "Aspen Chen"
        if (author == "Yuling") return "Yuling Wang"
        if (author == "Danni Qu") return "Danni Qu / Angela"
        if (author == "Hin Kit Eric Wong") return "Hin Kit Eric Wong"
        return author
      }
      function corrected_author(commit, author) {
        author = normalize_author(author)
        if (commit ~ /^86d234a/) return "Hin Kit Eric Wong"
        return author
      }
      {
        person = corrected_author($1, $2)
        commits[person]++
      }
      END {
        for (person in commits) {
          printf "%8d %s\n", commits[person], person
        }
      }
    ' | sort -k2,2
}

numstat_by_author() {
  local title="$1"
  shift
  print_title "$title"
  printf "%10s %10s %8s %s\n" "added" "deleted" "commits" "author"
  git log "$EVIDENCE_REF" --no-merges --numstat --format='@@@%H	%aN' -- "$@" |
    awk -v exclude="$EVIDENCE_EXCLUDE_REGEX" '
      BEGIN { FS = "\t" }
      function normalize_author(author) {
        if (author == "Andrew Zhang" || author == "andrew-yifanzhang") return "Andrew Zhang"
        if (author == "AspenC") return "Aspen Chen"
        if (author == "Danni Qu") return "Danni Qu / Angela"
        if (author == "Yuling") return "Yuling Wang"
        return author
      }
      function corrected_author(author, commit, path) {
        author = normalize_author(author)
        if (commit ~ /^86d234a/) return "Hin Kit Eric Wong"
        if ((path ~ /^backend\/reflexion_agent(\/|$)/ || path ~ /^backend\/reflexion_memory[.]json$/) && author == "Aspen Chen") return "Hin Kit Eric Wong"
        return author
      }
      function flush_commit() {
        for (touched_author in touched) {
          commits[touched_author]++
        }
        delete touched
      }
      /^@@@/ {
        flush_commit()
        split(substr($0, 4), header, "\t")
        commit = header[1]
        author = header[2]
        next
      }
      NF == 3 && $1 ~ /^[0-9]+$/ && $2 ~ /^[0-9]+$/ && $3 !~ exclude {
        adjusted_author = corrected_author(author, commit, $3)
        added[adjusted_author] += $1
        deleted[adjusted_author] += $2
        touched[adjusted_author] = 1
      }
      END {
        flush_commit()
        for (author in commits) {
          printf "%10d %10d %8d %s\n", added[author], deleted[author], commits[author], author
        }
      }
    ' | sort -k4,4
}

blame_by_author() {
  local title="$1"
  shift
  print_title "$title"
  printf "%10s %s\n" "lines" "author"
  git ls-tree -r --name-only "$EVIDENCE_REF" -- "$@" |
    awk -v exclude="$EVIDENCE_EXCLUDE_REGEX" '$0 !~ exclude' |
    while IFS= read -r file; do
      printf '@@@FILE\t%s\n' "$file"
      git blame --line-porcelain "$EVIDENCE_REF" -- "$file"
    done |
    awk '
      function normalize_author(author) {
        if (author == "Andrew Zhang" || author == "andrew-yifanzhang") return "Andrew Zhang"
        if (author == "AspenC") return "Aspen Chen"
        if (author == "Danni Qu") return "Danni Qu / Angela"
        if (author == "Yuling") return "Yuling Wang"
        return author
      }
      function corrected_author(author, commit, path) {
        author = normalize_author(author)
        if (commit ~ /^86d234a/) return "Hin Kit Eric Wong"
        if ((path ~ /^backend\/reflexion_agent(\/|$)/ || path ~ /^backend\/reflexion_memory[.]json$/) && author == "Aspen Chen") return "Hin Kit Eric Wong"
        return author
      }
      /^@@@FILE\t/ {
        file = substr($0, 9)
        next
      }
      /^[0-9a-f]{40} / {
        commit = $1
        next
      }
      /^author / {
        author = corrected_author(substr($0, 8), commit, file)
        lines[author]++
      }
      END {
        for (author in lines) {
          printf "%10d %s\n", lines[author], author
        }
      }
    ' | sort -k2,2
}

subsystem_quantities() {
  local title="$1"
  shift

  numstat_by_author "$title: non-merge numstat by author" "$@"
  blame_by_author "$title: current-line blame by author" "$@"
}

timeline_by_author() {
  local latest_date
  local recent_start

  latest_date="$(git log -1 "$EVIDENCE_REF" --no-merges --date=short --format='%ad')"
  recent_start="$(date -d "$latest_date -1 day" +%Y-%m-%d)"

  print_title "Merged non-merge commit timeline by week"
  printf 'Last two-day window: %s through %s\n' "$recent_start" "$latest_date"
  git log "$EVIDENCE_REF" --no-merges --date=short --format='%ad%x09%H%x09%aN' |
    while IFS=$'\t' read -r commit_date commit author; do
      local day_of_week
      local week_start

      day_of_week="$(date -d "$commit_date" +%u)"
      week_start="$(date -d "$commit_date -$((day_of_week - 1)) days" +%Y-%m-%d)"
      printf '%s\t%s\t%s\t%s\n' "$commit_date" "$week_start" "$commit" "$author"
    done |
    awk -v recent_start="$recent_start" '
      BEGIN { FS = "\t" }
      function normalize_author(author) {
        if (author == "Andrew Zhang" || author == "andrew-yifanzhang") return "Andrew Zhang"
        if (author == "AspenC") return "Aspen Chen"
        if (author == "Danni Qu") return "Danni Qu / Angela"
        if (author == "Yuling") return "Yuling Wang"
        return author
      }
      function corrected_author(commit, author) {
        author = normalize_author(author)
        if (commit ~ /^86d234a/) return "Hin Kit Eric Wong"
        return author
      }
      {
        date = $1
        week = $2
        commit = $3
        author = corrected_author(commit, $4)
        counts[author, week]++
        totals[author]++
        if (date >= recent_start) recent[author]++
        if (first[author] == "" || date < first[author]) first[author] = date
        if (date > last[author]) last[author] = date
        weeks[week] = 1
        authors[author] = 1
      }
      END {
        for (week in weeks) week_list[++week_count] = week
        for (i = 1; i <= week_count; i++) {
          for (j = i + 1; j <= week_count; j++) {
            if (week_list[i] > week_list[j]) {
              temp = week_list[i]
              week_list[i] = week_list[j]
              week_list[j] = temp
            }
          }
        }

        for (author in authors) author_list[++author_count] = author
        for (i = 1; i <= author_count; i++) {
          for (j = i + 1; j <= author_count; j++) {
            if (author_list[i] > author_list[j]) {
              temp = author_list[i]
              author_list[i] = author_list[j]
              author_list[j] = temp
            }
          }
        }

        printf "%-22s %6s %10s %10s", "author", "total", "first", "last"
        for (i = 1; i <= week_count; i++) printf " %8s", substr(week_list[i], 6)
        printf " %8s", "last2d"
        printf "\n"
        for (i = 1; i <= author_count; i++) {
          author = author_list[i]
          printf "%-22s %6d %10s %10s", author, totals[author], first[author], last[author]
          for (j = 1; j <= week_count; j++) printf " %8d", counts[author, week_list[j]] + 0
          printf " %8d", recent[author] + 0
          printf "\n"
        }
      }
    '
}

commit_list() {
  if [[ "${INCLUDE_COMMIT_HISTORY:-0}" != "1" ]]; then
    return
  fi

  local title="$1"
  shift
  print_title "$title"
  git log "$EVIDENCE_REF" --no-merges --format='%h %ad %an %s' --date=short -- "$@"
}

print_title "Repository commit counts"
printf 'Generated at: %s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z (%z)')"
printf 'Evidence ref: %s\n' "$EVIDENCE_REF"
printf 'Attribution corrections: %s is counted for Hin Kit Eric Wong; Aspen-attributed lines under backend/reflexion_agent are counted for Hin Kit Eric Wong.\n' "${ERIC_REASSIGNED_COMMIT:0:7}"
printf 'Primary quantity exclusions: cache artifacts, tracked JSON, docs/markdown, tests, and test/run fixtures.\n'
printf 'Raw email/local-identifier output is suppressed; normalized contributor counts follow.\n'
grouped_commit_counts
timeline_by_author

if [[ "${INCLUDE_COMMIT_HISTORY:-0}" != "1" ]]; then
  print_title "Commit history output"
  printf 'Raw path-specific commit lists are omitted by default. Set INCLUDE_COMMIT_HISTORY=1 to include them.\n'
fi

numstat_by_author "Main product paths: non-merge numstat by author" "${PRODUCT_PATHS[@]}"
blame_by_author "Main product paths: current-line blame by author" "${PRODUCT_PATHS[@]}"

numstat_by_author "Journey, wizard, employee, and skill UX paths: non-merge numstat by author" "${JOURNEY_PATHS[@]}"
blame_by_author "Journey, wizard, employee, and skill UX paths: current-line blame by author" "${JOURNEY_PATHS[@]}"
commit_list "Journey, wizard, employee, and skill UX path commit history" "${JOURNEY_PATHS[@]}"

numstat_by_author "Demo simulator paths: non-merge numstat by author" "${DEMO_PATHS[@]}"
blame_by_author "Demo simulator paths: current-line blame by author" "${DEMO_PATHS[@]}"
commit_list "Demo simulator path commit history" "${DEMO_PATHS[@]}"

numstat_by_author "Reflexion agent paths: non-merge numstat by author" "${REFLEXION_PATHS[@]}"
blame_by_author "Reflexion agent paths: current-line blame by author" "${REFLEXION_PATHS[@]}"
commit_list "Reflexion agent path commit history" "${REFLEXION_PATHS[@]}"

subsystem_quantities "Backend API and runtime paths" "${BACKEND_API_RUNTIME_PATHS[@]}"
subsystem_quantities "Agent runtime and OpenHands paths" "${AGENT_RUNTIME_PATHS[@]}"
subsystem_quantities "Chat interface paths" "${CHAT_INTERFACE_PATHS[@]}"
subsystem_quantities "Workspace, editor, and project-file paths" "${WORKSPACE_PROJECT_PATHS[@]}"
subsystem_quantities "Report, metrics, and trajectory paths" "${REPORT_METRICS_PATHS[@]}"
subsystem_quantities "Skill ingestion and evaluation paths" "${SKILL_INGESTION_EVALUATION_PATHS[@]}"
subsystem_quantities "Employee detail tab paths" "${EMPLOYEE_DETAIL_PATHS[@]}"

blame_by_author "Project Files tab component: current-line blame by author" "${PROJECT_FILES_TAB_PATHS[@]}"
blame_by_author "Metrics and trajectory backend core: current-line blame by author" "${METRICS_CORE_PATHS[@]}"
blame_by_author "Browser live view component: current-line blame by author" "${BROWSER_LIVE_VIEW_PATHS[@]}"
blame_by_author "Report UI components: current-line blame by author" "${REPORT_UI_PATHS[@]}"
