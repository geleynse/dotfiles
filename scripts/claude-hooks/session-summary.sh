#!/usr/bin/env bash
# session-summary.sh — Stop hook for Claude Code
#
# Called when Claude Code finishes a response (Stop event).
# Generates a brief summary line of what was accomplished in this turn
# by reading the assistant's final message from stdin.
#
# stdin JSON shape (Stop event):
#   { "session_id": "...", "stop_reason": "end_turn"|"tool_use"|..., "message": "..." }
#
# We extract the first ~sentence of the response as a lightweight summary.
# Full AI-powered summarization happens via memory-distill nightly.
#
# Output: JSON with suppressOutput:true to keep this invisible.

set -euo pipefail

WORKSPACE="${ROOK_WORKSPACE:-/home/alan/.openclaw/workspace}"
MEMORY_DIR="$WORKSPACE/memory"
TODAY=$(TZ="America/Los_Angeles" date +%Y-%m-%d)
SCRATCH="$MEMORY_DIR/${TODAY}.md"
TIMESTAMP=$(TZ="America/Los_Angeles" date +%H:%M)

mkdir -p "$MEMORY_DIR"

# Read hook input
INPUT=$(cat)

STOP_REASON=$(echo "$INPUT" | jq -r '.stop_reason // empty' 2>/dev/null) || { echo '{"suppressOutput": true}'; exit 0; }

# Only summarize on end_turn (normal completion), not on tool_use mid-turn stops
if [ "$STOP_REASON" != "end_turn" ] && [ "$STOP_REASON" != "stop_sequence" ]; then
  echo '{"suppressOutput": true}'
  exit 0
fi

# Extract the assistant message text
MESSAGE=$(echo "$INPUT" | jq -r '.message // empty' 2>/dev/null) || { echo '{"suppressOutput": true}'; exit 0; }

# Skip if empty or very short
if [ ${#MESSAGE} -lt 20 ]; then
  echo '{"suppressOutput": true}'
  exit 0
fi

# Extract a one-line summary: first sentence or first 200 chars
# Strip markdown formatting for cleaner log
SUMMARY=$(echo "$MESSAGE" | head -5 | tr '\n' ' ' | sed 's/[#*`]//g' | sed 's/  */ /g')
SUMMARY="${SUMMARY:0:200}"
# Try to cut at sentence boundary (require period followed by space or end-of-string,
# not mid-path periods like ~/.claude)
if echo "$SUMMARY" | grep -qP '[.!?](\s|$)'; then
  CUT=$(echo "$SUMMARY" | grep -oP '^.+?[.!?](?=\s|$)' | head -1)
  [ -n "$CUT" ] && SUMMARY="$CUT"
fi

# Don't log if it's just a greeting or very generic
if echo "$SUMMARY" | grep -qiP '^(hello|hi |hey |good morning|good evening|no_reply|heartbeat_ok)'; then
  echo '{"suppressOutput": true}'
  exit 0
fi

if [ -n "$SUMMARY" ]; then
  if [ ! -f "$SCRATCH" ]; then
    printf "# %s Daily Scratch\n\n" "$TODAY" > "$SCRATCH"
  fi

  if ! grep -q "^## Session Summaries (laptop)" "$SCRATCH" 2>/dev/null; then
    printf "\n## Session Summaries (laptop)\n" >> "$SCRATCH"
  fi

  (
    flock -w 2 200 2>/dev/null || true
    echo "- [$TIMESTAMP] $SUMMARY" >> "$SCRATCH"
  ) 200>>"$SCRATCH.lock"
fi

echo '{"suppressOutput": true}'
exit 0
