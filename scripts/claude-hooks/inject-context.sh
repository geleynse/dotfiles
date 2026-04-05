#!/usr/bin/env bash
# inject-context.sh — SessionStart hook for Claude Code
#
# Fires once when a session begins. Reads the last 2-3 days of session
# summaries from daily scratch files and injects them as context via
# hookSpecificOutput.additionalContext so the model has continuity.
#
# Output JSON shape for SessionStart:
#   {
#     "hookSpecificOutput": {
#       "hookEventName": "SessionStart",
#       "additionalContext": "... recent session context ..."
#     }
#   }

set -euo pipefail

WORKSPACE="${ROOK_WORKSPACE:-/home/alan/.openclaw/workspace}"
MEMORY_DIR="$WORKSPACE/memory"
TODAY=$(TZ="America/Los_Angeles" date +%Y-%m-%d)

# Read stdin (SessionStart provides session_id etc.)
cat >/dev/null 2>&1 || true

# Gather recent context: last 3 days of scratch files
CONTEXT=""
for OFFSET in 3 2 1 0; do
  DATE=$(TZ="America/Los_Angeles" date -d "-${OFFSET} days" +%Y-%m-%d 2>/dev/null) || continue
  FILE="$MEMORY_DIR/${DATE}.md"

  [ -f "$FILE" ] || continue

  if [ "$DATE" = "$TODAY" ]; then
    # Today: include everything
    CONTENT=$(cat "$FILE")
  else
    # Older days: extract structured sections, skip raw activity log
    CONTENT=$(awk '
      BEGIN { printing=0 }
      /^## Session Activity/ { printing=0; next }
      /^## / { printing=1 }
      /^# / { printing=1 }
      printing { print }
    ' "$FILE" 2>/dev/null)

    # Fallback: first 20 lines if no structured sections found
    if [ -z "$CONTENT" ]; then
      CONTENT=$(head -20 "$FILE")
    fi
  fi

  if [ -n "$CONTENT" ]; then
    CONTEXT="${CONTEXT}

### ${DATE}
${CONTENT}"
  fi
done

# If we have context, output it for the hook system
if [ -n "$CONTEXT" ]; then
  MESSAGE="## Recent Session Context (auto-injected)

The following is automatically captured context from recent sessions. Use it to maintain continuity.
${CONTEXT}"

  # Use jq to properly JSON-escape the multiline string
  echo "$MESSAGE" | jq -Rs '{
    "hookSpecificOutput": {
      "hookEventName": "SessionStart",
      "additionalContext": .
    }
  }'
else
  echo '{}'
fi

exit 0
