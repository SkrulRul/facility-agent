#!/usr/bin/env bash
set -uo pipefail

proj="${CLAUDE_PROJECT_DIR:-$(pwd)}"
input=$(cat)
session_id=$(printf '%s' "$input" | jq -r '.session_id // empty')
state_file="$proj/.claude/hooks/.runtime/last_check.json"

# Nothing recorded yet (no app/ write happened, or quality_gate.sh never ran) -> allow.
[ -f "$state_file" ] || exit 0

# Read defensively: a missing/corrupt field or unreadable file must never hard-block --
# fail open (allow) rather than wedge the session on a broken state file.
status=$(jq -r '.status // empty' "$state_file" 2>/dev/null || true)
recorded_session=$(jq -r '.session_id // empty' "$state_file" 2>/dev/null || true)

# Only honor a failure recorded by THIS session. A different/older session_id means the
# marker is stale (e.g. a prior session was interrupted mid-failure) -- ignore it rather
# than wrongly blocking an unrelated future session that hasn't touched app/ yet.
[ "$status" = "fail" ] || exit 0
[ "$recorded_session" = "$session_id" ] || exit 0

reason=$(jq -r '.reason // "uv run poe check is failing; see the last quality_gate.sh block for details."' "$state_file" 2>/dev/null)
jq -n --arg reason "$reason" '{decision:"block", reason:$reason}'
exit 0
