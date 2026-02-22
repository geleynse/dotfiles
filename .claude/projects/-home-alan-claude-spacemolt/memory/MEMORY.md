# SpaceMolt Project Memory

## Project TODO
- **`TODO.md`** at repo root — master list of ideas, bugs, and feature work
- Numbered items (#1-#69+), strikethrough + **DONE** when completed
- Check TODO.md at session start to see what's pending

## Claude Code Custom Commands & Skills
- Slash commands: `.claude/commands/` (no YAML frontmatter, filename = command name)
- Skills: `.claude/skills/` (YAML frontmatter with name/description)
- `.claude/*` with `!.claude/commands/` and `!.claude/skills/` in gitignore
- **`fleet-manage` skill** (was fleet-improve-loop): `/fleet-manage` with `improve N rounds` arg. Runs `spacemolt-fleet improve`, dispatches Sonnet subagent analysis, fixes prompts, commits+syncs, loops up to N iterations. Single skill at `.claude/commands/fleet-manage.md`.
- **`spacemolt-fleet improve <canary> [--duration N] [--health-threshold N]`**: Canary start → health monitoring → timed shutdown → analyze → JSON report. Exit: 0=success, 1=canary failed, 2=all stopped early.

## Fleet Script Gotchas
- Large text to `jq` via `--rawfile`/`--slurpfile` with temp files, NOT `--arg` (ARG_MAX)
- JSONL: `total_cost_usd` (not `cost_usd`), token data in `modelUsage`, primary model by highest `costUSD`
- Remote exec: `pve_exec()` (root), `pve_exec_user()` (spacemolt user)
- `pve_exec_user` wraps in single quotes — can't use SQL with single quotes. Use `pve_exec` or upload scripts.
- JSONL sync: `pct pull` runs on Proxmox HOST (not inside container). Tar to user home dir.

## Fleet Architecture
- 5 agents on LXC 200 (Proxmox), prompts at `/home/spacemolt/fleet-agents/`
- Always check `fleet-agents/fleet-config.json` for latest — models/proxies change frequently
- Action proxy :3100, fleet-web :3000 on LXC
- Snapshots at `fleet-snapshots/` (gitignored): `.json` (~288KB) + `-summary.txt` (~1.5KB)
- `agentDeniedTools` + `callLimits` in fleet-config.json, enforced by proxy `checkGuardrails()`

## Active Issues
- **Gas cloud mining yields zero ore**: Only asteroid belts (POIs with "belt"/"harvesters") produce ore.
- **multi_sell pending at scale**: 120+ qty saturates tick queue. Items safe (returned to storage), but credits stall.
- **Sell auto-listing (zero credits)**: sell() with no demand creates exchange orders, delta=0. Agents must use analyze_market() first.
- **Haiku verbosity**: 23-149 long texts per 10 turns. Not a major cost driver — deprioritize vs economic cycle fixes. Forbidden words list is 52 words (hallucination keywords).
- **Re-contamination**: Agents rewrite contaminated docs even after wipes. Proxy now rejects contaminated writes to write_doc/write_diary, but watch for new contamination patterns.
- When all agents share the same bug, check common-rules.txt first.

## Proxy Key Gotchas
- `PARAM_REMAPS` in schema.ts: jump→target_system, travel→target_poi, find_route→target_system, search_systems→query. `OUR_SCHEMA_PARAMS` in server.ts must stay in sync.
- `checkSchemaDrift()` runs at startup — compares our params vs server, logs mismatches.
- get_status is cached (WebSocket state_update), not a game server call. Structure: `{tick, player: {credits, current_system, ...}, ship: {fuel, hull, cargo, ...}}`
- Compound tools: batch_mine, travel_to, jump_route, multi_sell, scan_and_attack
- All state-changing tools get `waitForTick()`. Nav tools: arrival_tick-aware cache wait (up to 8 ticks for jump, 1 for travel). Auto-undock before jump.
- **Jump arrival_tick protocol**: Game server sends `{pending:true}` immediately, then deferred `ok` with `{arrival_tick: N}` ~3 ticks later. `state_update` shows new position at tick N. GameClient captures `lastArrivalTick`; `waitForNavCacheUpdate` waits until cache tick >= arrival_tick. Both passthrough jump and jump_route clear `lastArrivalTick` before each jump.
- **test-nav.ts**: Diagnostic script connecting directly to game WebSocket to test jump protocol. Used to discover the arrival_tick mechanism.
- **Jump param**: Agents use `system_id` (proxy remaps to `target_system`). Do NOT tell agents to use `target_system` — Zod validation rejects it before remap runs.
- **Nav timing logs**: travel_to, jump_route, and passthrough jump/travel all log elapsed ms per step. Check proxy logs to diagnose cache lag vs actual nav delays.
- **travel_to returns `docked_at_base`**: `location_after.docked_at_base` is null if POI has no base. Proxy emits a warning. Agents must check before calling get_missions().
- personality-rules.txt references MCP tools (write_diary/write_doc), NOT filesystem paths.
- DENIED_TOOLS in schema.ts: ~73 tools blocked. All proxy features documented in common-rules.txt PROXY FEATURES — keep in sync.
- Snapshot analysis: agents data is a list (not dict), access via `data['agents'][i]`.

## Deployment
- LXC 200 via `ssh root@192.168.1.2` then `pct exec 200`
- Build locally, deploy compiled JS: `spacemolt-fleet web deploy`, `spacemolt-fleet proxy deploy`
- Sync prompts only: `spacemolt-fleet sync` (no restart needed)
- Proxy restart needed after fleet-config.json routing/tool changes

## SQLite & Agent Docs
- Tables: agent_diary, agent_docs, agent_signals, proxy_sessions
- Docs injected at turn start: strategy (full), discoveries/market-intel (last 20 lines)
- MCP tools: write_diary, read_diary, write_doc, read_doc, write_report

## OAuth
- Token at `~/.claude/.credentials.json`, synced to LXC via `spacemolt-fleet sync`
- All 5 agents share one OAuth token. `ensure_fresh_token()` checks expiry before fleet start.
- **OAuth mid-run refresh**: `spacemolt-fleet improve` health loop checks token expiry every 5 min, refreshes if ≤30 min remaining. Prevents agents losing turns to expired tokens.
- SOCKS proxies (1081/1082) only route game WebSocket, NOT Claude API calls

## Game Version Notes
- Current: v0.128+. Key changes through v0.128 handled in proxy/prompts.
- v0.125: Budget ships (Datum, Foundation), commission_status has required_materials. Summarizer added.
- v0.126: Crafting expansion (new recipes, Nova Terra ion hub), craft param is `count` (not `quantity`).
- v0.124: session_id in tool calls (proxy strips it).
- `catalog` replaced `get_recipes`/`get_ships` (v0.108). Ship tools: shipyard_showroom, commission_ship/quote, browse_ships, buy_listed_ship.
- analyze_market: no params, skill-based insights (v0.104). Terminology: "station exchange" + "station manager".
- Tool names differ from patch notes — always verify via proxy test output.

## MCP v2 (All Agents)
- All 5 agents on v2/standard. Single `common-rules.txt` (v2 syntax), single `mcp.json` pointing to `/mcp/v2`.
- Old `common-rules-v2.txt` and `mcp-v2.json` deleted. Bash script no longer branches on mcpVersion.
- `/mcp/v2` endpoint serves 6-15 consolidated tools (action-dispatch model) alongside `/mcp` (v1, ~79 tools)
- v2→v1 translation at MCP boundary only. WebSocket only speaks v1. Compound tools/summarizers unchanged.
- `V2_TO_V1_PARAM_MAP` in schema.ts maps generic `id`/`text`/`count` to v1-specific params per action
- `spacemolt_catalog` uses `type` (not `action`) as dispatch key — v1 command is always "catalog" with type param
- **Known issue**: v2 `waitForNavCacheUpdate` lacks arrival_tick optimization (simpler than v1)
- **Known issue**: `get_system`/`get_poi`/`get_map` param remaps may be wrong — verify against live server

## Fleet CLI Rewrite (#11)
- New TypeScript CLI at `fleet-cli/` (npm package name: `spacemolt-fleet`), workspace sibling to action-proxy/fleet-web
- Root `package.json` with npm workspaces, `tsconfig.base.json` shared config
- All 31 subcommands ported across 9 steps. Original bash script at `scripts/spacemolt-fleet` preserved.
- JSONL parser (183 lines) + summary generator (429 lines) — faithful port with 3 bug fixes over Python original
- Bug fixes vs old: `??` instead of `or` for 0-credit handling, improve files excluded from prev_snap, pruning only counts real snapshots
- 49 tests (13 config + 17 parser + 19 summary). `npx spacemolt-fleet help` works.
- Forbidden words list is 52 words (not 34 — MEMORY.md was outdated)

## Reference Files
- `action-proxy/CLAUDE.md`, `fleet-agents/CLAUDE.md`, `fleet-web/CLAUDE.md` — keep updated on arch changes
