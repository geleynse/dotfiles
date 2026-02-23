# SpaceMolt Project Memory

## Project TODO
- **`TODO.md`** at repo root — master list of ideas, bugs, and feature work
- Numbered items (#1-#84), strikethrough + **DONE** when completed
- Check TODO.md at session start to see what's pending

## Claude Code Custom Commands & Skills
- Slash commands: `.claude/commands/` (no YAML frontmatter, filename = command name)
- Skills: `.claude/skills/` (YAML frontmatter with name/description)
- `.claude/*` with `!.claude/commands/` and `!.claude/skills/` in gitignore
- **`fleet-manage` skill** (was fleet-improve-loop): `/fleet-manage` with `improve N rounds` arg. Creates a worktree for isolation, runs `spacemolt-fleet improve`, dispatches Sonnet subagent analysis, fixes prompts, commits+syncs, loops up to N iterations. At end, presents merge/PR/discard/keep options. Single skill at `.claude/commands/fleet-manage.md`.
- **Worktree gotcha**: If other agents clean up worktrees mid-session, fleet-manage's worktree can disappear. The prompt changes will still be synced to LXC but the git branch/commits are lost. Consider committing to main directly for fleet-manage sessions, or protect the worktree.
- **Old bash script conflict**: The repo root `spacemolt-fleet` was the old 126k bash script. It shadowed the TS CLI (`npx spacemolt-fleet`) and didn't support worktrees — reading config from its own directory, not `git rev-parse --show-toplevel`. Deleted in iteration 8. If a similar issue recurs, check `which spacemolt-fleet` and `file $(which spacemolt-fleet)`.
- **`spacemolt-fleet improve <canary> [--duration N] [--health-threshold N]`**: Canary start → health monitoring → timed shutdown → analyze → JSON report. Exit: 0=success, 1=canary failed, 2=all stopped early.
- **Improve turn counting**: Uses `/tmp/improve-start-marker` on LXC + `find -newer`. If marker fails, caps at expected turns from duration (duration/interval + 2). Fixed 2026-02-22 — old code had `head -20` fallback that counted historical turns. **Per-agent counts** now passed to analyze (was passing maxTurns for all agents, inflating data for agents with fewer turns like drifter-gale).

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
- **Sell auto-listing (zero credits)**: FIXED (#69). Proxy gates multi_sell on prior analyze_market call via calledTools tracking in AgentCallTracker. Still happening at prompt level — sable-thorn had 3 zero-demand sells in iteration 7.
- **Verbosity**: SOLVED by switching to Sonnet. Haiku: 507 verbose texts, 465 forbidden words. Sonnet: 0 verbose, 1-13 forbidden. No further prompt pressure needed.
- **Sonnet throughput vs Haiku**: Haiku=~100 turns/10min, Sonnet=~13 turns/30min (~10x slower). Sonnet costs less per run ($8 vs $16) but earns less credits. User chose Sonnet for quality.
- **Sonnet zero economic activity**: Sonnet agents explore but don't mine/sell. Prompts updated to enforce economic cycle — needs further testing.
- **Re-contamination**: Agents rewrite contaminated docs even after wipes. Proxy now rejects contaminated writes to write_doc/write_diary, but watch for new contamination patterns.
- **Navigation loops**: Resolved — was inflated data from analyzing old turns. Per-agent turn counting fix deployed. Not a real issue.
- **25% empty sessions**: Server downtime ate 25/100 turns in iteration 7. lumen-shoal worst (8/20 empty).
- **Captain's log compliance poor**: 9-13 of 20 sessions missing captains_log_add per agent. May need proxy enforcement.
- **Forbidden word "sync" false positive**: rust-vane hits "sync" 34x because a system is literally named "sync". Consider exempting system names from forbidden word counting.
- When all agents share the same bug, check common-rules.txt first.

## YAML Tool Results (TODO #79)
- Per-agent `toolResultFormat: "yaml"` in fleet-config.json (default: JSON)
- `format-result.ts` has `formatForAgent()`, `reformatResponse()` in server.ts wraps with try/catch
- Applied at `withInjections()` in both v1 and v2 paths — final formatting before MCP transport
- `yaml` npm package (v2) uses YAML 1.2 schema — no coercion of "yes"/"no"/"null" strings
- **All agents enabled** (iteration 8+, was drifter-gale only for A/B). Proxy logs `[yaml]` with byte savings per response.
- Responses that bypass `withInjections()` (errors, doc tools) stay JSON — they're tiny.

## Proxy Code Structure Gotchas
- `createSapServer` (v1) and `createSapServerV2` (v2) are separate function scopes in server.ts. Helper functions defined inside one are NOT accessible from the other. Shared helpers must be at module level (before the exports). This caused a build failure with `throttledPersistGameState`.
- Both v1 and v2 need identical wiring for persistence, events, guardrails. When adding persistence calls, always grep for the v2 equivalent and add there too.

## Proxy Key Gotchas
- `PARAM_REMAPS` in schema.ts: jump→target_system, travel→target_poi, find_route→target_system, search_systems→query. `OUR_SCHEMA_PARAMS` in server.ts must stay in sync.
- `checkSchemaDrift()` runs at startup — compares our params vs server, logs mismatches.
- get_status is cached (WebSocket state_update), not a game server call. Structure: `{tick, player: {credits, current_system, ...}, ship: {fuel, hull, cargo, ...}}`
- Compound tools: batch_mine, travel_to, jump_route, multi_sell, scan_and_attack
- **scan_and_attack full combat loop**: DONE (#72/#73). Battle polling (MAX_BATTLE_TICKS=30), hull-based stance switching (defensive <30%, flee <20%), auto-loot wrecks after victory. Both v1 and v2 handlers. v2 stance reads `args.stance` first, falls back to `args.id`.
- **battleCache**: DONE (#56). `Map<string, BattleState | null>` in SharedState. Populated from combat_update events and scan_and_attack loop. Cleared after battle ends.
- **Respawn detection**: DONE (#56). `player_died` sets pendingDeathEnrichment flag; next state_update injects synthetic `respawn_state` critical event with post-respawn location/hull/credits.
- **Schema drift fixes**: DONE (#54). 9 tools fixed. Drift down to 2 (get_system/get_poi with intentional optional extras).
- **All agents on Sonnet** (iteration 8+). Was: drifter/rust/lumen on Haiku, sable/cinder on Sonnet.
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
- Tables: agent_diary, agent_docs, agent_signals, proxy_sessions, proxy_game_state, proxy_battle_state, proxy_call_trackers
- Docs injected at turn start: strategy (full), discoveries/market-intel (last 20 lines)
- MCP tools: write_diary, read_diary, write_doc, read_doc, write_report, search_memory
- **search_memory**: Searches agent's OWN diary+docs only (filtered by agent name). Cross-agent search is TODO #82.
- **Proxy cache persistence** (#81): statusCache/battleCache/callTrackers persisted to fleet-web SQLite via fire-and-forget HTTP. statusCache throttled to 30s per agent. Restored on proxy startup. battleCache also persisted during scan_and_attack loop.

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
- **Fixed (2026-02-22)**: v2 `jump_route` had before-system captured after jump, v2 passthrough had redundant tick wait before nav cache wait. Both now match v1 behavior.
- **Proxy caches persisted** (#81 DONE): statusCache, battleCache, callTrackers saved to fleet-web SQLite via `cache-persistence.ts`. eventBuffers still in-memory only (ephemeral by design).
- **Known issue**: `get_system`/`get_poi`/`get_map` param remaps may be wrong — verify against live server

## Fleet CLI Rewrite (#11)
- New TypeScript CLI at `fleet-cli/` (npm package name: `spacemolt-fleet`), workspace sibling to action-proxy/fleet-web
- Root `package.json` with npm workspaces, `tsconfig.base.json` shared config
- All 31 subcommands ported. Old bash script removed from repo root (was causing worktree config issues).
- JSONL parser (183 lines) + summary generator (429 lines) — faithful port with 3 bug fixes over Python original
- Bug fixes vs old: `??` instead of `or` for 0-credit handling, improve files excluded from prev_snap, pruning only counts real snapshots
- 78 tests (13 config + 17 parser + 19 summary + 12 health parsers + 17 output). `npx spacemolt-fleet help` works.
- Forbidden words list is 52 words (not 34 — MEMORY.md was outdated)
- **Worktree support**: `config.ts` uses `git rev-parse --show-toplevel` via `execFileSync` for all paths except SNAPSHOTS_DIR (always main repo). `spacemolt-fleet sync/deploy` from a worktree uses that worktree's files automatically.

## Competitor Clients
- Client comparison at `~/Dendron/vault.personal/projects.spacemolt.client-comparison.md` — 9 clients analyzed
- **botrunner** (humbrol2): Hybrid scripted bots + LLM. 10 deterministic routines at zero LLM cost. Coordinator meta-bot uses public `https://game.spacemolt.com/api/market` for fleet optimization. Local pathfinding via `GET /api/map`. High throughput threat.
- **SpaceMolt_User** (leopoko, v1.3.2): Full web GUI. Reveals PvP battle zones (outer/mid/inner/engaged), player-to-player trading, facilities with rent, action loops. Good reference for game mechanics.
- **sm-cli** (vcarl, 137 commits): Most active CLI. Battle, facility (14 subcmds), catalog with recipe trace, hierarchical commands.
- **commander** (official, v0.2.11): YAML-over-JSON for token savings. Dynamic OpenAPI schema. Single "game" meta-tool.

## Reference Files
- `action-proxy/CLAUDE.md`, `fleet-agents/CLAUDE.md`, `fleet-web/CLAUDE.md` — keep updated on arch changes
