#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CASES_DIR="$ROOT_DIR/harness/evals/cases"

required_fields=(
  "id"
  "title"
  "task"
  "fixture"
  "allowed_scope"
  "forbidden_changes"
  "expected_commands"
  "deterministic_assertions"
  "hard_failure_conditions"
)

valid_assertions=(
  "architecture_boundary_enforced"
  "behavior_verification_present"
  "forbidden_paths_unchanged"
  "regression_test_or_rationale"
  "tests_not_suppressed"
  "test_file_added_or_updated"
)

status=0

log() {
  echo "$*"
}

fail() {
  echo "ERROR: $*" >&2
  status=1
}

field_value() {
  local field="$1"
  local file="$2"
  awk -F ': ' -v field="$field" '
    $1 == field {
      sub("^[^:]*:[[:space:]]*", "")
      print
      exit
    }
  ' "$file"
}

contains_valid_assertion() {
  local assertion="$1"
  local valid
  for valid in "${valid_assertions[@]}"; do
    [[ "$assertion" == "$valid" ]] && return 0
  done
  return 1
}

validate_command() {
  local command="$1"
  local case_path="$2"

  [[ "$command" == "none" ]] && return 0

  local executable="${command%% *}"
  if [[ "$executable" == ./* ]]; then
    [[ -x "$ROOT_DIR/${executable#./}" ]] || {
      fail "$case_path references non-executable command: $command"
      return
    }
    return 0
  fi

  fail "$case_path references unsupported expected command: $command"
}

validate_fixture() {
  local fixture="$1"
  local case_path="$2"

  case "$fixture" in
    "current repository")
      return 0
      ;;
    "")
      fail "$case_path has an empty fixture"
      return
      ;;
  esac

  fail "$case_path references unsupported fixture: $fixture"
}

echo "Agent eval validation"
echo

seen_ids_file="$(mktemp "${TMPDIR:-/tmp}/copia-eval-ids.XXXXXX")"
cleanup() {
  rm -f "$seen_ids_file"
}
trap cleanup EXIT

shopt -s nullglob
case_files=("$CASES_DIR"/*.md)
shopt -u nullglob

if [[ "${#case_files[@]}" -eq 0 ]]; then
  fail "no eval cases found in ${CASES_DIR#$ROOT_DIR/}"
fi

for case_file in "${case_files[@]}"; do
  case_path="${case_file#$ROOT_DIR/}"
  log "==> Validating $case_path"

  if [[ "$(sed -n '1p' "$case_file")" != "---" ]]; then
    fail "$case_path must start with front matter delimiter ---"
  fi

  if [[ "$(sed -n '2,$p' "$case_file" | grep -n '^---$' | head -n 1 || true)" == "" ]]; then
    fail "$case_path must close front matter with ---"
  fi

  for field in "${required_fields[@]}"; do
    value="$(field_value "$field" "$case_file")"
    if [[ -z "$value" ]]; then
      fail "$case_path missing or empty field: $field"
    fi
  done

  id="$(field_value "id" "$case_file")"
  if [[ -n "$id" ]]; then
    if [[ ! "$id" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
      fail "$case_path has invalid id: $id"
    elif grep -q "^$id|" "$seen_ids_file"; then
      first_case="$(grep "^$id|" "$seen_ids_file" | head -n 1 | cut -d '|' -f 2-)"
      fail "$case_path duplicates id from $first_case: $id"
    else
      printf '%s|%s\n' "$id" "$case_path" >> "$seen_ids_file"
    fi
  fi

  fixture="$(field_value "fixture" "$case_file")"
  validate_fixture "$fixture" "$case_path"

  IFS=';' read -r -a commands <<< "$(field_value "expected_commands" "$case_file")"
  for command in "${commands[@]}"; do
    command="$(echo "$command" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [[ -n "$command" ]] || {
      fail "$case_path has an empty expected command entry"
      continue
    }
    validate_command "$command" "$case_path"
  done

  IFS=';' read -r -a assertions <<< "$(field_value "deterministic_assertions" "$case_file")"
  for assertion in "${assertions[@]}"; do
    assertion="$(echo "$assertion" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [[ -n "$assertion" ]] || {
      fail "$case_path has an empty deterministic assertion entry"
      continue
    }
    contains_valid_assertion "$assertion" || fail "$case_path has unknown deterministic assertion: $assertion"
  done
done

if [[ "$status" -eq 0 ]]; then
  log "Eval validation passed."
else
  log "Eval validation failed."
fi

exit "$status"
