#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

PRODUCT_PATHS=(
  frontend/src
  backend/routers
  backend/db
  backend/services
  backend/alembic
  start.sh
  .env.template
  backend/server.py
  backend/reflexion_agent/agent.py
  backend/metrics.py
  backend/trajectory.py
  backend/trajectory_llm.py
  backend/config.py.example
)

ANDREW_BUGFIX_BASE="${ANDREW_BUGFIX_BASE:-origin/main}"
ANDREW_BUGFIX_HEAD="${ANDREW_BUGFIX_HEAD:-origin/andrew}"

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

print_title() {
  printf '\n== %s ==\n' "$1"
}

grouped_commit_counts() {
  print_title "Repository commit counts grouped by person"
  git log --all --format='%aN	%aE' |
    awk '
      BEGIN { FS = "\t" }
      {
        person = $1 " <" $2 ">"
        if ($1 == "Andrew Zhang" || $1 == "andrew-yifanzhang") person = "Andrew Zhang"
        else if ($1 == "Aditya Kumar") person = "Aditya Kumar"
        else if ($1 == "Arthur Chien") person = "Arthur Chien"
        else if ($1 == "Aspen Chen" || $1 == "AspenC") person = "Aspen Chen"
        else if ($1 == "Yuling") person = "Yuling"
        else if ($1 == "Danni Qu") person = "Danni Qu"
        else if ($1 == "Hin Kit Eric Wong") person = "Hin Kit Eric Wong"
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
  git log --all --no-merges --numstat --format='@@@%aN' -- "$@" |
    awk '
      BEGIN { FS = "\t" }
      /^@@@/ {
        author = substr($0, 4)
        if (author == "Andrew Zhang" || author == "andrew-yifanzhang") author = "Andrew Zhang"
        commits[author]++
        next
      }
      NF == 3 && $1 ~ /^[0-9]+$/ { added[author] += $1; deleted[author] += $2 }
      END {
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
  git ls-files -- "$@" |
    while IFS= read -r file; do
      git blame --line-porcelain -- "$file"
    done |
    awk '
      /^author / {
        author = substr($0, 8)
        if (author == "Andrew Zhang" || author == "andrew-yifanzhang") author = "Andrew Zhang"
        lines[author]++
      }
      END {
        for (author in lines) {
          printf "%10d %s\n", lines[author], author
        }
      }
    ' | sort -k2,2
}

andrew_bugfix_summary() {
  if ! git rev-parse --verify --quiet "$ANDREW_BUGFIX_HEAD" >/dev/null; then
    return
  fi

  print_title "Andrew Zhang open PR #17 bugfix summary"
  printf 'Base: %s\n' "$ANDREW_BUGFIX_BASE"
  printf 'Head: %s\n' "$ANDREW_BUGFIX_HEAD"
  git diff --shortstat "$ANDREW_BUGFIX_BASE...$ANDREW_BUGFIX_HEAD"
  printf '\n%10s %10s %s\n' "added" "deleted" "path"
  git diff --numstat "$ANDREW_BUGFIX_BASE...$ANDREW_BUGFIX_HEAD"
  if [[ "${INCLUDE_COMMIT_HISTORY:-0}" == "1" ]]; then
    printf '\n'
    git log --no-merges --format='%h %ad %an %s' --date=short "$ANDREW_BUGFIX_BASE..$ANDREW_BUGFIX_HEAD"
  fi
}

commit_list() {
  if [[ "${INCLUDE_COMMIT_HISTORY:-0}" != "1" ]]; then
    return
  fi

  local title="$1"
  shift
  print_title "$title"
  git log --all --no-merges --format='%h %ad %an %s' --date=short -- "$@"
}

print_title "Repository commit counts"
git shortlog -sne --all | sort -k2,2 -k3,3
grouped_commit_counts

if [[ "${INCLUDE_COMMIT_HISTORY:-0}" != "1" ]]; then
  print_title "Commit history output"
  printf 'Raw path-specific commit lists are omitted by default. Set INCLUDE_COMMIT_HISTORY=1 to include them.\n'
fi

numstat_by_author "Main product paths: non-merge numstat by author" "${PRODUCT_PATHS[@]}"
blame_by_author "Main product paths: current-line blame by author" "${PRODUCT_PATHS[@]}"
andrew_bugfix_summary

numstat_by_author "Journey, wizard, employee, and skill UX paths: non-merge numstat by author" "${JOURNEY_PATHS[@]}"
blame_by_author "Journey, wizard, employee, and skill UX paths: current-line blame by author" "${JOURNEY_PATHS[@]}"
commit_list "Journey, wizard, employee, and skill UX path commit history" "${JOURNEY_PATHS[@]}"

numstat_by_author "Demo simulator paths: non-merge numstat by author" "${DEMO_PATHS[@]}"
blame_by_author "Demo simulator paths: current-line blame by author" "${DEMO_PATHS[@]}"
commit_list "Demo simulator path commit history" "${DEMO_PATHS[@]}"

numstat_by_author "Reflexion agent paths: non-merge numstat by author" "${REFLEXION_PATHS[@]}"
blame_by_author "Reflexion agent paths: current-line blame by author" "${REFLEXION_PATHS[@]}"
commit_list "Reflexion agent path commit history" "${REFLEXION_PATHS[@]}"
