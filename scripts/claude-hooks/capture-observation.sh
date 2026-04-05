#!/usr/bin/env bash
# capture-observation.sh — PostToolUse hook for Claude Code
#
# Called after every tool use. Reads JSON from stdin describing the tool call.
# Captures significant observations (file writes, bash commands, key decisions)
# to the daily scratch file in a machine-parseable format.
#
# stdin JSON shape (from Claude Code hooks):
#   { "session_id": "...", "tool_name": "...", "tool_input": {...}, "tool_response": {...} }
#
# We keep this FAST — no AI calls, just pattern-matched logging.
# Output: JSON with suppressOutput:true so this doesn't pollute the transcript.

set -euo pipefail

WORKSPACE="${ROOK_WORKSPACE:-/home/alan/.openclaw/workspace}"
MEMORY_DIR="$WORKSPACE/memory"
TODAY=$(TZ="America/Los_Angeles" date +%Y-%m-%d)
SCRATCH="$MEMORY_DIR/${TODAY}.md"
TIMESTAMP=$(TZ="America/Los_Angeles" date +%H:%M)

# Ensure memory dir exists
mkdir -p "$MEMORY_DIR"

# Read hook input from stdin
INPUT=$(cat)

# Extract fields with jq (fail silently if jq missing or parse error)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null) || exit 0
TOOL_INPUT=$(echo "$INPUT" | jq -c '.tool_input // {}' 2>/dev/null) || exit 0

# Skip noisy/uninteresting read-only tools
case "$TOOL_NAME" in
  Read|Glob|Grep|ToolSearch|Skill)
    echo '{"suppressOutput": true}'
    exit 0
    ;;
esac

# Extract useful details based on tool type
ENTRY=""

case "$TOOL_NAME" in
  Bash)
    CMD=$(echo "$TOOL_INPUT" | jq -r '.command // empty' 2>/dev/null) || true
    DESC=$(echo "$TOOL_INPUT" | jq -r '.description // empty' 2>/dev/null) || true
    # Skip very short or trivial commands
    if [ ${#CMD} -lt 5 ]; then
      echo '{"suppressOutput": true}'
      exit 0
    fi
    # Skip common read-only patterns
    if echo "$CMD" | grep -qP '^(ls |cat |head |tail |wc |file |which |type |echo |printf )'; then
      echo '{"suppressOutput": true}'
      exit 0
    fi
    if [ -n "$DESC" ]; then
      ENTRY="- [$TIMESTAMP] \`Bash\`: $DESC"
    else
      # Truncate long commands
      SHORT_CMD="${CMD:0:120}"
      [ ${#CMD} -gt 120 ] && SHORT_CMD="${SHORT_CMD}..."
      ENTRY="- [$TIMESTAMP] \`Bash\`: \`$SHORT_CMD\`"
    fi
    ;;

  Edit)
    FILE=$(echo "$TOOL_INPUT" | jq -r '.file_path // empty' 2>/dev/null) || true
    if [ -n "$FILE" ]; then
      SHORT_FILE="${FILE/#\/home\/rook/~}"
      ENTRY="- [$TIMESTAMP] \`Edit\`: $SHORT_FILE"
    fi
    ;;

  Write)
    FILE=$(echo "$TOOL_INPUT" | jq -r '.file_path // empty' 2>/dev/null) || true
    if [ -n "$FILE" ]; then
      SHORT_FILE="${FILE/#\/home\/rook/~}"
      ENTRY="- [$TIMESTAMP] \`Write\`: $SHORT_FILE"
    fi
    ;;

  WebFetch|WebSearch)
    URL=$(echo "$TOOL_INPUT" | jq -r '.url // .query // empty' 2>/dev/null) || true
    if [ -n "$URL" ]; then
      ENTRY="- [$TIMESTAMP] \`$TOOL_NAME\`: $URL"
    fi
    ;;

  mcp__*)
    # MCP tool calls — extract the tool name suffix for readability
    SHORT_TOOL="${TOOL_NAME#mcp__}"
    SHORT_TOOL=$(echo "$SHORT_TOOL" | sed 's/__/\//g')
    ENTRY="- [$TIMESTAMP] \`MCP\`: $SHORT_TOOL"
    ;;

  *)
    # Any other tool — log it generically
    ENTRY="- [$TIMESTAMP] \`$TOOL_NAME\`"
    ;;
esac

# If we have something to log, append it
if [ -n "$ENTRY" ]; then
  # Create scratch file with header if it doesn't exist
  if [ ! -f "$SCRATCH" ]; then
    printf "# %s Daily Scratch\n\n" "$TODAY" > "$SCRATCH"
  fi

  # Ensure the auto-capture section exists
  if ! grep -q "^## Session Activity (laptop)" "$SCRATCH" 2>/dev/null; then
    printf "\n## Session Activity (laptop)\n" >> "$SCRATCH"
  fi

  # Append the observation (use flock to prevent concurrent write corruption)
  (
    flock -w 2 200 2>/dev/null || true
    echo "$ENTRY" >> "$SCRATCH"
  ) 200>>"$SCRATCH.lock"
fi

# Suppress our stdout from the transcript — this is background bookkeeping
echo '{"suppressOutput": true}'
exit 0
