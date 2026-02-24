---
paths:
  - ~/claude/spacemolt
  - ~/claude/spacemolt/.claude/skills/fleet-improve-loop/skill.md
description: SpaceMolt fleet operations — only run when Alan is present and explicitly asks
---

# SpaceMolt Fleet Rules

## Mode: Manual-Only (No Auto-Runs)

**Golden Rule:** Fleet operations (improve, monitor, analysis) only run when Alan is **explicitly present and has asked**.

### Why
- Long-running processes (15-18 min improvement cycles)
- Meaningful decisions require human judgment (prompt fixes, design direction)
- Better to batch work than fragment Alan's attention throughout the day

### How to Invoke

Only trigger fleet operations via explicit commands:
- `/fleet-improve` — Start improvement loop (canary-based)
- `/fleet-status` — Quick health check (no long-running processes)
- `/fleet-manage` — Detailed analysis + recommendations (interactive)

Never auto-start fleet operations in heartbeats or background tasks.

## Fleet Improvement Loop

When invoked, follow `~/.claude/skills/fleet-improve-loop/skill.md` exactly:

1. **Verify fleet state** — `spacemolt-fleet status`, offer to stop if running
2. **Pick canary** — Ask Alan which agent to use as test case
3. **Run iterations** (max 5):
   - Start improvement cycle (~18 min)
   - Analyze results
   - Fix prompts (targeted, one rule per issue)
   - Commit + sync
4. **Log findings** — proxy-todos.md for code-level fixes, git commits for prompt fixes
5. **Report final state** — Summary of iterations, fixes applied, remaining work

## Fleet Health Metrics (Manual Only)

When Alan asks for status, check:

### Economic Cycle
- Is mining happening? (check captain logs)
- Is selling happening? (multi_sell vs sell difference matters)
- Is refueling happening? (complete cycle?)
- Are credits accumulating?

### Verbosity
- Are agents over-narrating? (target: <50 verbose texts per 90s cycle)
- Haiku agents inherently more verbose than Sonnet

### Tool Usage
- Are agents using correct tools? (sell ≠ multi_sell)
- Are action proxy errors occurring?
- Are rate-limit issues visible?

### Output
Don't dump full logs. Instead:
```
✅ Fleet Status (as of HH:MM):
  • drifter-gale: Last turn 2min ago, economic cycle active
  • sable-thorn: Last turn 5min ago, mining (no recent sells)
  • rust-vane: Last turn 1min ago, normal
  • lumen-shoal: Last turn 8min ago, stalled (investigate)
  • cinder-wake: Last turn 3min ago, refueling

⚠️ Alerts: Lumen-shoal hasn't acted in 8+ min
📊 Economic: Fleet credits up 2.3k this cycle
📝 Issues: Check proxy-todos.md for pending code fixes
```

## Current Fleet Config

**Agents:** 5 (drifter-gale, sable-thorn, rust-vane, lumen-shoal, cinder-wake)
**Backend:** All Claude (Haiku/Sonnet)
**Deployment:** Proxmox LXC 200 (spacemolt user, tmux sessions)
**Web UI:** fleet-web dashboard at localhost:3000
**Logs:** Real-time via captain-log, snapshots in fleet-snapshots/

## Decision Log

When improving prompts:
- Add rule → commit message explains why
- Remove verbosity check → explain target level
- Change tool blocking → note which agents affected
- Update economic callouts → include current cycle metrics

Example:
```
commit: fleet-improve: iter N — reduce haiku verbosity (target 40/cycle)

- common-rules.txt: Added "Keep internal monologue under 40 lines"
- sable-thorn.txt: Updated verbosity baseline (was 91, now targeting 40)
- Reason: Haiku agents naturally verbose; prompt pressure helps without model change
```

## Design Docs (Reference)

Current completed designs (not implemented yet):
- `#86`: Discord integration (agentlogs + webhook)
- `#59`: Forum posting (with guardrails)

If Alan asks to start either, follow their design docs in workspace.

## Open Code TODOs

See `~/claude/spacemolt/docs/proxy-todos.md` for items that need server code changes (not prompt fixes).
