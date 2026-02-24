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

exec python3 - "$CLAUDE_CREDS" "$OPENCLAW_AUTH" << 'PYEOF'
import json, sys, subprocess, shutil

claude_path, oc_path = sys.argv[1], sys.argv[2]

creds = json.load(open(claude_path))
token = creds.get("claudeAiOauth", {}).get("accessToken")
if not token:
    print("No token in Claude creds", file=sys.stderr)
    sys.exit(1)

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
