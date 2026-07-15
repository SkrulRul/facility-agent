#!/usr/bin/env bash
set -uo pipefail   # NOT -e: a failing `poe check` inside $() must be captured, not abort the script

proj="${CLAUDE_PROJECT_DIR:-$(pwd)}"
input=$(cat)
raw=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')
[ -z "$raw" ] && exit 0                    # non-file tool / empty path -> no-op

# Normalize to absolute (real sessions send absolute; be defensive about relative)
case "$raw" in
  /*) path="$raw" ;;
  *)  path="$proj/$raw" ;;
esac

# Trip on app/ writes only; carve out __init__.py and Skill-generated extraction targets.
# NOTE: the extraction_targets carve-out here is a RUNTIME concern (do not interrupt the
# Skill mid-generation with a poe check), NOT a spec-coverage concern -- that is why Hook 1
# keeps it while Hook 2 (require_spec.sh) drops it.
case "$path" in
  */app/extraction_targets/*) exit 0 ;;    # Skill output -- do not interrupt mid-generation
  */__init__.py)              exit 0 ;;    # empty packaging scaffolding
  */app/*)                    ;;           # fall through -> run the check
  *)                          exit 0 ;;    # anything outside app/ -> no-op
esac

# Full check anchored to the project dir; disable color at source
out=$(cd "$proj" && NO_COLOR=1 uv run poe check 2>&1)
status=$?
[ "$status" -eq 0 ] && exit 0

# Strip residual ANSI (BSD sed can't \b -- use python3, which is confirmed available),
# bound the size, and build VALID JSON with jq --arg (never string-interpolate raw output)
clean=$(printf '%s' "$out" \
  | python3 -c 'import sys,re; sys.stdout.write(re.sub(r"\x1b\[[0-9;]*[A-Za-z]","",sys.stdin.read()))' \
  | tail -c 4000)
jq -n --arg reason "$clean" '{decision:"block", reason:$reason}'
exit 0
