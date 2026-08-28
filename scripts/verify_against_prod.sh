#!/usr/bin/env bash
#
# Verify this repo matches the code actually deployed to AWS.
#
# Downloads each live Lambda package and compares every first-party file
# against functions/<function-name>/. Exits non-zero on any difference, so it
# can run in CI or as a pre-deploy gate.
#
# Dependency versions are reported as a warning rather than a failure: they
# live in .dist-info metadata inside the package and drift whenever anything
# is rebuilt, which is not the same as source drift.
#
# Usage:
#   scripts/verify_against_prod.sh                 # all functions
#   scripts/verify_against_prod.sh qb-avsight-sync # one function
#
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

if [[ $# -gt 0 ]]; then
  FUNCTIONS=("$@")
else
  mapfile -t FUNCTIONS < <(ls functions/ | grep -v '^_shared$')
fi

# Resolve the source file for a given package filename: the function's own copy
# wins, then functions/_shared/. Mirrors what build_and_deploy.sh assembles.
resolve_src() {
  local fn_dir="$1" name="$2"
  if [[ -f "$fn_dir/$name" ]]; then echo "$fn_dir/$name"
  elif [[ -f "functions/_shared/$name" ]]; then echo "functions/_shared/$name"
  fi
}

OVERALL=0

for FUNCTION_NAME in "${FUNCTIONS[@]}"; do
  SRC_DIR="functions/$FUNCTION_NAME"
  if [[ ! -d "$SRC_DIR" ]]; then
    echo "!! no such function in repo: $FUNCTION_NAME"
    OVERALL=1
    continue
  fi

  echo "=== $FUNCTION_NAME"

  URL="$(aws lambda get-function --function-name "$FUNCTION_NAME" \
        --query 'Code.Location' --output text 2>/dev/null)"
  if [[ -z "$URL" || "$URL" == "None" ]]; then
    echo "  !! could not read deployed package (auth? wrong region?)"
    OVERALL=1
    continue
  fi

  EXTRACT="$WORK_DIR/$FUNCTION_NAME"
  mkdir -p "$EXTRACT"
  curl -s -o "$WORK_DIR/$FUNCTION_NAME.zip" "$URL"
  unzip -o -q "$WORK_DIR/$FUNCTION_NAME.zip" -d "$EXTRACT"

  # Compare every first-party file this function's package is built from:
  # its own files plus the shared modules.
  DIFFS=0
  mapfile -t NAMES < <(
    { find "$SRC_DIR" -maxdepth 1 -type f ! -name requirements.txt -printf '%f\n'
      find functions/_shared -maxdepth 1 -type f -printf '%f\n'; } | sort -u
  )
  for f in "${NAMES[@]}"; do
    src="$(resolve_src "$SRC_DIR" "$f")"
    label="$f"
    [[ "$src" == functions/_shared/* ]] && label="$f  (shared)"
    if [[ ! -f "$EXTRACT/$f" ]]; then
      echo "  MISSING in deployed package: $label"
      DIFFS=1
      continue
    fi
    if cmp -s "$src" "$EXTRACT/$f"; then
      echo "  ok    $label"
    else
      echo "  DIFF  $label"
      DIFFS=1
    fi
  done

  # Flag first-party files present in prod but absent from the repo. Skips
  # vendored dependencies, which are installed at build time, not tracked.
  while IFS= read -r f; do
    [[ -n "$(resolve_src "$SRC_DIR" "$f")" ]] && continue
    [[ "$f" == "typing_extensions.py" ]] && continue   # pip-installed module
    echo "  UNTRACKED in repo: $f"
    DIFFS=1
  done < <(find "$EXTRACT" -maxdepth 1 -type f -name '*.py' -printf '%f\n' \
           | while read -r c; do
               # only report files that are not part of an installed dist
               [[ -d "$EXTRACT/${c%.py}" ]] && continue
               echo "$c"
             done)

  # Dependency versions: warn only.
  if [[ -f "$SRC_DIR/requirements.txt" ]]; then
    DEPLOYED_DEPS="$(ls "$EXTRACT" | grep dist-info | sed 's/\.dist-info//' \
                     | sed 's/-\([0-9][^-]*\)$/==\1/' | sed 's/_/-/g' | sort)"
    REPO_DEPS="$(grep -v '^\s*#' "$SRC_DIR/requirements.txt" | grep -v '^\s*$' | sort)"
    if [[ "$DEPLOYED_DEPS" != "$REPO_DEPS" ]]; then
      echo "  warn  dependency versions differ from the deployed package:"
      diff <(echo "$REPO_DEPS") <(echo "$DEPLOYED_DEPS") \
        | grep '^[<>]' | sed 's/^/          /'
    fi
  fi

  if [[ "$DIFFS" -eq 0 ]]; then
    echo "  -> source matches production"
  else
    echo "  -> SOURCE DRIFT DETECTED"
    OVERALL=1
  fi
done

echo
if [[ "$OVERALL" -eq 0 ]]; then
  echo "All checked functions match production."
else
  echo "Drift detected. Reconcile before deploying."
fi
exit "$OVERALL"
