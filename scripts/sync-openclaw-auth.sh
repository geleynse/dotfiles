#!/bin/bash
# Sync Claude Code OAuth token to rook-bridge (LXC 109) and fleet agents
set -o pipefail

CLAUDE_CREDS="$HOME/.claude/.credentials.json"
LXC_HOST="root@192.168.1.18"
LXC_CREDS="/home/rook/.claude/.credentials.json"

# Credentials file can briefly disappear during token refresh — wait and retry
for i in 1 2 3; do
    [[ -f "$CLAUDE_CREDS" ]] && break
    sleep 5
done
[[ -f "$CLAUDE_CREDS" ]] || { echo "No Claude Code credentials (after 3 retries)" >&2; exit 1; }

# Auto-refresh if token expires in less than 2 hours
# Claude Code will use the refresh_token to get a new 8-hour access token
# when an API call is made near expiry
HOURS_LEFT=$(python3 -c "
import json, time
creds = json.load(open('$CLAUDE_CREDS'))
exp = creds.get('claudeAiOauth', {}).get('expiresAt', 0) / 1000
hours = (exp - time.time()) / 3600
print(f'{hours:.1f}')
" 2>/dev/null)

if python3 -c "exit(0 if float('${HOURS_LEFT:-99}') > 2 else 1)" 2>/dev/null; then
    true  # Token is fresh enough
else
    echo "Token expires in ${HOURS_LEFT}h — triggering refresh via claude API call..."
    unset CLAUDECODE  # Ensure we're not nested in another Claude Code session
    /home/alan/.local/bin/claude -p "." --output-format text > /dev/null 2>&1 && echo "Token refreshed" || echo "WARNING: Token refresh failed" >&2
fi

# Sync tasks CLI and skills to LXC 109
TASKS_SCRIPT="$HOME/scripts/tasks"
SKILLS_DIR="$HOME/.claude/skills"
if [[ -f "$TASKS_SCRIPT" ]]; then
    scp -q -o ConnectTimeout=5 -o BatchMode=yes "$TASKS_SCRIPT" "$LXC_HOST:/home/rook/scripts/tasks" 2>/dev/null && \
        ssh -o ConnectTimeout=5 -o BatchMode=yes "$LXC_HOST" "chmod +x /home/rook/scripts/tasks" 2>/dev/null && \
        echo "Synced tasks CLI to LXC 109" || echo "Tasks CLI sync failed" >&2
fi
for skill in tasks tasks-daily; do
    if [[ -f "$SKILLS_DIR/$skill/SKILL.md" ]]; then
        ssh -o ConnectTimeout=5 -o BatchMode=yes "$LXC_HOST" "mkdir -p /home/rook/.claude/skills/$skill" 2>/dev/null
        scp -q -o ConnectTimeout=5 -o BatchMode=yes "$SKILLS_DIR/$skill/SKILL.md" "$LXC_HOST:/home/rook/.claude/skills/$skill/SKILL.md" 2>/dev/null && \
            echo "Synced $skill skill to LXC 109" || echo "$skill skill sync failed" >&2
    fi
done

timeout 90 python3 - "$CLAUDE_CREDS" "$LXC_HOST" "$LXC_CREDS" << 'PYEOF'
import json, sys, subprocess, time, os

claude_path, lxc_host, lxc_creds_path = sys.argv[1:4]

creds = json.load(open(claude_path))
oauth = creds.get("claudeAiOauth", {})
token = oauth.get("accessToken")
if not token:
    print("No token in Claude creds", file=sys.stderr)
    sys.exit(1)

# Warn if token is expired or expiring soon
expires_at_ms = oauth.get("expiresAt", 0)
if expires_at_ms:
    expires_at = expires_at_ms / 1000
    now = time.time()
    days_left = (expires_at - now) / 86400
    if days_left < 0:
        print(f"WARNING: Token expired {abs(days_left):.1f} days ago", file=sys.stderr)
    elif days_left < 0.5:
        print(f"NOTE: Token expires in {days_left * 24:.1f}h")

ssh_opts = ["-o", "ConnectTimeout=5", "-o", "BatchMode=yes"]

# Sync credentials file to LXC 109 (openclaw)
try:
    r = subprocess.run(
        ["ssh"] + ssh_opts + [lxc_host, f"cat > {lxc_creds_path}"],
        input=json.dumps(creds).encode(),
        capture_output=True, timeout=15
    )
    if r.returncode == 0:
        print("Synced credentials to LXC 109")
    else:
        print(f"LXC 109 creds sync failed: {r.stderr.decode().strip()}", file=sys.stderr)
except Exception as e:
    print(f"LXC 109 creds sync error: {e}", file=sys.stderr)

# Restart rook-bridge on LXC 109 so it picks up the new token
try:
    r = subprocess.run(
        ["ssh"] + ssh_opts + [lxc_host, "systemctl restart rook-bridge"],
        capture_output=True, timeout=15
    )
    if r.returncode == 0:
        print("Restarted rook-bridge on LXC 109")
    else:
        print(f"rook-bridge restart failed: {r.stderr.decode().strip()}", file=sys.stderr)
except Exception as e:
    print(f"rook-bridge restart error: {e}", file=sys.stderr)

# Sync credentials to LXC 200 (spacemolt-agents)
try:
    r = subprocess.run(
        ["ssh"] + ssh_opts + ["spacemolt-agents",
         "cat > /home/spacemolt/.claude/.credentials.json && "
         "chmod 600 /home/spacemolt/.claude/.credentials.json && "
         "chown spacemolt:spacemolt /home/spacemolt/.claude/.credentials.json"],
        input=json.dumps(creds).encode(),
        capture_output=True, timeout=15
    )
    if r.returncode == 0:
        print("Synced credentials to spacemolt-agents LXC")
    else:
        print(f"LXC 200 sync failed: {r.stderr.decode().strip()}", file=sys.stderr)
except Exception as e:
    print(f"LXC 200 sync error: {e}", file=sys.stderr)

# Sync credentials to CT 201 (spacemolt-staging)
try:
    r = subprocess.run(
        ["ssh"] + ssh_opts + ["root@192.168.1.17",
         "cat > /home/spacemolt/.claude/.credentials.json && "
         "chmod 600 /home/spacemolt/.claude/.credentials.json && "
         "chown spacemolt:spacemolt /home/spacemolt/.claude/.credentials.json"],
        input=json.dumps(creds).encode(),
        capture_output=True, timeout=15
    )
    if r.returncode == 0:
        print("Synced credentials to spacemolt-staging CT 201")
    else:
        print(f"CT 201 sync failed: {r.stderr.decode().strip()}", file=sys.stderr)
except Exception as e:
    print(f"CT 201 sync error: {e}", file=sys.stderr)
PYEOF
echo "sync-openclaw-auth completed successfully at $(date)"
