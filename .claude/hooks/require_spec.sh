#!/usr/bin/env bash
set -uo pipefail

proj="${CLAUDE_PROJECT_DIR:-$(pwd)}"
input=$(cat)
raw=$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')
[ -z "$raw" ] && exit 0

case "$raw" in
  /*) path="$raw" ;;
  *)  path="$proj/$raw" ;;
esac

# Fixed exemption, checked BEFORE segment derivation: package __init__.py at any depth.
# (Dunder/package-init scaffolding is never a feature; NOT a segment. Kept regardless of mechanism.)
case "$path" in
  */__init__.py) exit 0 ;;
esac

# Scope: app/** only. tests/, docs/, scripts/ are NOT gated.
# Compute the path relative to the app/ root.
case "$path" in
  */app/*) rel="${path##*/app/}" ;;   # ".../app/services/extraction_service.py" -> "services/extraction_service.py"
  *)       exit 0 ;;                    # outside app/ -> no-op (tests/docs/scripts/anything else)
esac

# Derive the feature segment from the naming convention:
#   subdirectory file   -> first path component  (the DIRECTORY name, not stripped)
#   top-level app/ file -> filename STEM         (extension stripped)
case "$rel" in
  */*) segment="${rel%%/*}" ;;          # "services/..."   -> "services"
  *)   segment="${rel%.*}" ;;           # "domain.py"      -> "domain"
esac

# PASS condition (per feature, not per file):
#   1) a committed per-segment spec exists  -> docs/specs/<segment>.md   (simple test -f, no grep)
#   2) OR the pre-Phase-4 grandfather baseline enumerates this segment. The baseline's
#      machine-checked token list is a fenced block of one-token-per-line entries in the exact
#      form "- <token>". We match a WHOLE LINE with fixed strings: `grep -Fxq -- "- $segment"`.
#      -F = fixed string (segment is never a regex, so a stem containing "." can't act as a
#      wildcard), -x = whole-line anchor (zero substring/prose-collision surface), -q = quiet.
if [ -f "$proj/docs/specs/$segment.md" ]; then
  exit 0
fi
if grep -Fxq -- "- $segment" "$proj/docs/specs/pre-phase-4-baseline.md" 2>/dev/null; then
  exit 0
fi

# No per-segment spec and not grandfathered -> deny with an actionable reason (valid JSON via jq --arg)
jq -n --arg seg "$segment" --arg rel "$rel" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason:
      ("Feature segment \"\($seg)\" (from app/\($rel)) has no spec. Create docs/specs/\($seg).md describing this feature before editing its code (Phase-4 per-feature spec-before-code gate). Legacy Phases 1-3 segments are grandfathered in docs/specs/pre-phase-4-baseline.md; package __init__.py files are exempt.")
  }
}'
exit 0
