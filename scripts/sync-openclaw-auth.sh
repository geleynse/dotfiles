#!/bin/bash
# Sync Claude Code OAuth token to openclaw auth-profiles.json

CLAUDE_CREDS="$HOME/.claude/.credentials.json"
OPENCLAW_AUTH="$HOME/.openclaw/agents/main/agent/auth-profiles.json"

# Credentials file can briefly disappear during token refresh — wait and retry
for i in 1 2 3; do
    [[ -f "$CLAUDE_CREDS" ]] && break
    sleep 5
done
[[ -f "$CLAUDE_CREDS" ]] || { echo "No Claude Code credentials (after 3 retries)" >&2; exit 1; }
[[ -f "$OPENCLAW_AUTH" ]] || { echo "No openclaw auth-profiles.json" >&2; exit 1; }

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

exec python3 - "$CLAUDE_CREDS" "$OPENCLAW_AUTH" << 'PYEOF'
import json, sys, subprocess, shutil

claude_path, oc_path = sys.argv[1], sys.argv[2]

import time, datetime

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
        print(f"WARNING: Token expired {abs(days_left):.1f} days ago — run 'claude setup-token' to refresh", file=sys.stderr)
    elif days_left < 0.5:  # less than 12 hours
        hours_left = days_left * 24
        print(f"NOTE: Token expires in {hours_left:.1f}h — will auto-refresh via sync when < 2h remain")

# Sync to openclaw auth-profiles.json
auth = json.load(open(oc_path))
if auth["profiles"]["anthropic:default"].get("token") != token:
    auth["profiles"]["anthropic:default"]["token"] = token
    with open(oc_path, "w") as f:
        json.dump(auth, f, indent=2)
        f.write("\n")
    print("Synced Claude Code token to openclaw")

# Sync credentials to LXC 200 (spacemolt-agents)
if shutil.which("ssh"):
    try:
        r = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
             "spacemolt-agents", "cat > /root/.claude/.credentials.json"],
            input=json.dumps(creds).encode(),
            capture_output=True, timeout=15
        )
        if r.returncode == 0:
            print("Synced credentials to spacemolt-agents LXC")
        else:
            print(f"LXC sync failed: {r.stderr.decode().strip()}", file=sys.stderr)
    except Exception as e:
        print(f"LXC sync error: {e}", file=sys.stderr)
PYEOF
