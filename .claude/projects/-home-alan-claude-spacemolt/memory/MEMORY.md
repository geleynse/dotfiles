# SpaceMolt Project Memory

## Project TODO
- **`TODO.md`** at repo root — active items only (~10 remaining). **`TODO-ARCHIVE.md`** has ~102 completed items.
- Numbered items (#1-#127), strikethrough + **DONE** when completed
- Check TODO.md at session start to see what's pending

## Claude Code Custom Commands & Skills
- Slash commands: `.claude/commands/` (no YAML frontmatter, filename = command name)
- Skills: `.claude/skills/` (YAML frontmatter with name/description)
- `.claude/*` with `!.claude/commands/` and `!.claude/skills/` in gitignore
- **`fleet-manage` skill** (was fleet-improve-loop): `/fleet-manage` with `improve N rounds` arg. Creates a worktree for isolation, runs `spacemolt-fleet improve`, dispatches Sonnet subagent analysis, fixes prompts, commits+syncs, loops up to N iterations. At end, presents merge/PR/discard/keep options. Single skill at `.claude/commands/fleet-manage.md`.
- **Worktree gotcha**: If other agents clean up worktrees mid-session, fleet-manage's worktree can disappear. The prompt changes will still be synced to LXC but the git branch/commits are lost. Consider committing to main directly for fleet-manage sessions, or protect the worktree.
- **Old bash script conflict**: The repo root `spacemolt-fleet` was the old 126k bash script. It shadowed the TS CLI (`npx spacemolt-fleet`) and didn't support worktrees — reading config from its own directory, not `git rev-parse --show-toplevel`. Deleted in iteration 8. If a similar issue recurs, check `which spacemolt-fleet` and `file $(which spacemolt-fleet)`.
- **CLI invocation**: Fleet CLI is built with `--target bun`. Run with `bun fleet-cli/dist/cli.js <command>`. Do NOT use `node` (fails with `__require is not a function`). `npx spacemolt-fleet` may also fail — `bun fleet-cli/dist/cli.js` is the reliable invocation.
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
- **Unified server**: `spacemolt-server/` — single Express process on :3100 (merged proxy + web, #12 DONE 2026-02-24)
- Old `action-proxy/` deleted from repo (2026-02-23). `fleet-web/` also gone — all code lives in `spacemolt-server/`.
- **Runtime: Bun** (#96 DONE 2026-02-23). Both fleet-cli and spacemolt-server use Bun for runtime, test runner, and bundling. SQLite via `bun:sqlite` (replaced better-sqlite3). Tests via `bun:test` (replaced vitest). ~1143 tests total (1065 server + 78 CLI).
- Deploy: `spacemolt-fleet server deploy` (or `deploy-all`). Old `web deploy`/`proxy deploy` show deprecation warnings.
- Snapshots at `fleet-snapshots/` (gitignored): `.json` (~288KB) + `-summary.txt` (~1.5KB)
- `agentDeniedTools` + `callLimits` in fleet-config.json, enforced by proxy `checkGuardrails()`

## Active Issues
- **Gas cloud mining yields zero ore**: Only asteroid belts (POIs with "belt"/"harvesters") produce ore.
- **multi_sell pending at scale**: 120+ qty saturates tick queue. Items safe (returned to storage), but credits stall.
- **~~buy() storage hint~~**: FIXED (#100). Proxy injects hint after buy() telling agent items are in STATION STORAGE. Agent must call withdraw_items + install_mod. Game returns `{command: "buy"}` wrapper — buy hint checks `toolName === "buy"` not response content.
- **~~commission_status empty~~**: FIXED (#101). Game returns `{command: "commission_status"}` (not empty `{}`). Summarizer now checks emptiness AFTER `pick()` strips non-relevant fields.
- **Sell auto-listing (zero credits)**: FIXED (#69). Proxy gates multi_sell on prior analyze_market call via calledTools tracking in AgentCallTracker. Still happening at prompt level — sable-thorn had 3 zero-demand sells in iteration 7.
- **Verbosity**: SOLVED by Sonnet. Verbosity rules scaled back (2026-02-23): removed "OUTPUT RULES" + iteration stats from all agent prompts, simplified Rule 14 in common-rules, fleet-manage skill no longer flags verbosity. Forbidden words kept (hallucination indicators only).
- **Sonnet throughput vs Haiku**: Haiku=~100 turns/10min, Sonnet=~13 turns/30min (~10x slower). Sonnet costs less per run ($8 vs $16) but earns less credits. User chose Sonnet for quality.
- **Sonnet zero economic activity**: PARTIALLY FIXED (2026-02-24). Summary generator was reporting MINE=0/SELL=0 due to v2 tool counting bug (checked tool.name not input.action). Real data: agents ARE mining/selling but earning little due to zero-demand sells and mining at wrong POIs.
- **Summary generator v2 fix**: `getEffectiveToolName()` in summary-generator.ts extracts action from input field for v2 consolidated tools. Without this, MINE/SELL/CRAFT/MISSION columns all show 0.
- **NPC buy() doesn't work**: buy() only fills PLAYER sell orders. NPC market items (is_npc:true in get_poi) are reference prices, NOT purchasable. create_buy_order is NOT auto-filled by NPC inventory. Sable prompt rewritten to use commissions/player ships/buy orders.
- **~~SOCKS5 relay broken under Bun~~**: FIXED (#114). Root cause: Bun sends `Host: 127.0.0.1:<port>` — game server rejects mismatched Host. Fix: `localSocket.once('data')` rewrites Host header before piping. Sable re-enabled on micro proxy (1082).
- **Instability metrics false positives**: game-client.ts was recording ALL game errors (not_docked, item_not_available) and action_pending as server instability. One error in 5 requests = 20% error rate → "unstable" → blocks all non-safe tools for 10 min window. FIXED: only count connection_failed/timeout/5xx. action_pending has its own retry logic.
- **~~Circuit breaker is global~~**: FIXED (#115). Each GameClient has its own CircuitBreaker. `BreakerRegistry` in circuit-breaker.ts tracks all with `getAggregateStatus()` for health endpoint. `gameServerBreaker` kept as deprecated compat alias.
- **Snapshot filename sort bug**: Old snapshots use YYYYMMDD format, new use YYYY-MM-DD. Alphabetical sort picks old files as "latest". Fixed with mtime sort in improve.ts.
- **~~travel_to wrong POI resolution~~**: FIXED (2026-02-24). `poi-resolver.ts` caches POI data from get_system responses. All 4 travel paths (v1/v2 travel_to + passthrough) resolve names to IDs. get_system summarizer now includes POI `id` field.
- **Re-contamination**: Agents rewrite contaminated docs even after wipes. Proxy now rejects contaminated writes to write_doc/write_diary, but watch for new contamination patterns.
- **Captain's log compliance poor**: May need proxy enforcement.
- **Forbidden word "sync" false positive**: system literally named "sync". Consider exempting system names.
- When all agents share the same bug, check common-rules.txt first.

## YAML Tool Results (TODO #79)
- Per-agent `toolResultFormat: "yaml"` in fleet-config.json (default: JSON)
- `format-result.ts` has `formatForAgent()`, `reformatResponse()` in server.ts wraps with try/catch
- Applied at `withInjections()` in both v1 and v2 paths — final formatting before MCP transport
- `yaml` npm package (v2) uses YAML 1.2 schema — no coercion of "yes"/"no"/"null" strings
- **All agents enabled** (iteration 8+, was drifter-gale only for A/B). Proxy logs `[yaml]` with byte savings per response.
- Responses that bypass `withInjections()` (errors, doc tools) stay JSON — they're tiny.

## Proxy Code Structure (post-Gantry Phase 3 2026-02-24)
- **Naming**: SAP → Gantry. Types: `GantryConfig` (alias `SapConfig` deprecated). Factories: `createGantryServer`/`createGantryServerV2`. Log prefix: `[Gantry]`. MCP server name: `"gantry"`.
- **server.ts reduced from 4,491 → 317 lines** via three extraction phases:
  - Phase 1: `pipeline.ts` (59 tests), `compound-tools-impl.ts` (53 tests), `auth-handlers.ts` (19 tests)
  - Phase 2: `tool-registry.ts` (23 tests), `doc-tools.ts` (14 tests), `cached-queries.ts` (8 tests), `public-tools.ts` (7 tests), `mcp-factory.ts` (12 tests), `serverSchemaToZod` moved to `schema.ts` (7 tests)
  - Phase 3: `gantry-v2.ts` (17 tests), `passthrough-handler.ts` (15 tests), `proxy-constants.ts` (shared constants extracted to break circular imports). Shared handler exports added to cached-queries/doc-tools/public-tools/tool-registry.
- **DI pattern**: Each module defines a `*Deps` interface, `textResult` duplicated locally, pure functions imported directly, shared state via deps.
- **v1/v2 deduplication**: Handler logic shared between v1 and v2 (~530 lines deduplicated). Each Phase 2 module exports pure handler functions. v1 `registerXxxTools()` and v2 action dispatch both call shared handlers. Only difference: param naming (v1 named, v2 generic id/text/count).
- **mcp-factory.ts**: Top-level `createMcpServer()` — schema fetch, shared state init, health poller, Express router, v1/v2 endpoints. Re-exported from server.ts for app.ts compat.
- **gantry-v2.ts** (~479 lines): `createGantryServerV2` factory, `V2_ACTION_TO_V1_NAME` mapping, `BATTLE_SUB_ACTIONS`, v2→v1 param remapping, dispatches to shared handlers.
- **passthrough-handler.ts** (~272 lines): `handlePassthrough()` — nav capture, auto-undock, execute, tick wait, error hints, summarize, enrich, buy hint. Used by both v1 and v2.
- **proxy-constants.ts** (~106 lines): `STATE_CHANGING_TOOLS`, `CONTAMINATION_WORDS`, `stripPendingFields()`, `throttledPersistGameState()`, `reformatResponse()`. Created to break circular import between server.ts ↔ gantry-v2.ts.
- **tool-registry.ts**: Exports `TOOL_SCHEMAS`, `NO_PARAM_DESCRIPTIONS`, `PROXY_HANDLED_TOOLS`, `registerPassthroughTools()`, `registerCompoundTools()`, `buildCompoundActions()`, `handleGetEvents()`, `handleGetSessionInfo()`.
- **Config cleaned**: No more hardcoded IPs (PROXY_MAP/DIRECT_HOST removed), no DEFAULT_AGENTS fallback. Zod validation on load. Config file chain: `gantry.$GANTRY_ENV.json` → `gantry.json` → `fleet-config.json`. 23 config tests.
- **Game response wrappers**: Many game tools return `{command: "tool_name", ...data}`. Summarizers receive the full response — `Object.keys()` count includes `command`. Check emptiness AFTER `pick()`, not before, when detecting "no data" responses.

## Proxy Key Gotchas
- `PARAM_REMAPS` in schema.ts: jump→target_system, travel→target_poi, find_route→target_system, search_systems→query.
- `checkSchemaDrift()` runs at startup — compares our params vs server, logs mismatches.
- get_status is cached (populated by `refreshStatus()` polling after each tool call, NOT WebSocket push). Structure: `{tick, player: {credits, current_system, ...}, ship: {fuel, hull, cargo, ...}}`
- **Schema caching** (#107 DONE): `data/schema-cache.json` caches v1+v2 schemas. `invalidateSchemaCache()` on game version change. Tests must call `invalidateSchemaCache()` in setup/teardown to prevent cross-test pollution.
- Compound tools: batch_mine, travel_to, jump_route, multi_sell, scan_and_attack, loot_wrecks
- **scan_and_attack full combat loop**: DONE (#72/#73). Battle polling (MAX_BATTLE_TICKS=30), hull-based stance switching (defensive <30%, flee <20%), auto-loot wrecks after victory. Both v1 and v2 handlers. v2 stance reads `args.stance` first, falls back to `args.id`.
- **battleCache**: DONE (#56). `Map<string, BattleState | null>` in SharedState. Populated from combat_update events and scan_and_attack loop. Cleared after battle ends.
- **Respawn detection**: DONE (#56). `player_died` sets pendingDeathEnrichment flag; next state_update injects synthetic `respawn_state` critical event with post-respawn location/hull/credits.
- **Schema drift fixes**: DONE (#54). 9 tools fixed. Drift down to 2 (get_system/get_poi with intentional optional extras).
- **All agents on Sonnet** except cinder-wake on **Codex** (gpt-5.3-codex, re-enabled 2026-02-24). Codex does NOT support YAML tool results (rmcp can't parse YAML as JSON-RPC) — cinder has no `toolResultFormat` in config. ~68K tokens/turn, ~87K for longer sessions. If Codex underperforms, switch back to Sonnet with `toolResultFormat: "yaml"`.
- **deploy-all now deploys loop scripts** (fixed 2026-02-24). Previously only `fleet start` and `improve` called `deployLoopScripts()`. Stale loop scripts on LXC caused Codex smoke test failure.
- All state-changing tools get `waitForTick()`. Nav tools: arrival_tick-aware cache wait (up to 8 ticks for jump, 1 for travel). Auto-undock before jump.
- **Jump arrival_tick protocol**: Game server sends `{pending:true}` immediately, then deferred `ok` with `{arrival_tick: N}` ~3 ticks later. `refreshStatus()` poll shows new position at tick N. GameClient captures `lastArrivalTick`; `waitForNavCacheUpdate` waits until cache tick >= arrival_tick. Both passthrough jump and jump_route clear `lastArrivalTick` before each jump.
- **Bun + npm `ws` incompatibility**: Bundled npm `ws` causes "Expected 101 status code" under Bun. Fix: mark `ws` and `socks` as external in esbuild. SOCKS relay still broken (see Active Issues).
- **Legacy node→bun in deploy scripts**: cmdProxyStart and fleet-web start commands used `node dist/index.js`. Fixed 2026-02-24 to use `bun`. improve.ts now calls cmdServerStart (uses `spacemolt-server` tmux session) instead of cmdProxyStart (`action-proxy` session).
- **test-nav.ts**: Diagnostic script connecting directly to game WebSocket to test jump protocol. Used to discover the arrival_tick mechanism.
- **Jump param**: Agents use `system_id` (proxy remaps to `target_system`). Do NOT tell agents to use `target_system` — Zod validation rejects it before remap runs.
- **Nav timing logs**: travel_to, jump_route, and passthrough jump/travel all log elapsed ms per step. Check proxy logs to diagnose cache lag vs actual nav delays.
- **travel_to returns `docked_at_base`**: `location_after.docked_at_base` is null if POI has no base. Proxy emits a warning. Agents must check before calling get_missions().
- personality-rules.txt references MCP tools (write_diary/write_doc), NOT filesystem paths.
- DENIED_TOOLS in schema.ts: ~69 tools blocked (facility tools removed in #93). All proxy features documented in common-rules.txt PROXY FEATURES — keep in sync.
- **Facility tools** (#93 DONE): `facility`/`personal_build`/`personal_decorate`/`personal_visit` unblocked. Faction actions (build/upgrade/toggle/transfer/faction_build) blocked for non-Gale agents via `agentDeniedTools` with `tool:action` keys. All agents get personal facilities + read-only queries. Rule 29 in common-rules, Gale prompt has facility management strategy.
- Snapshot analysis: agents data is a list (not dict), access via `data['agents'][i]`.

## Deployment
- LXC 200 via `ssh root@192.168.1.2` then `pct exec 200`
- Build locally, deploy compiled JS: `spacemolt-fleet server deploy`
- **`spacemolt-fleet deploy-all`**: server deploy + sync prompts + server restart. Self-rebuilds fleet-cli first (non-fatal).
- **deploy-all gotcha**: If you add a new CLI command, the *current* process still runs stale code — the self-rebuild only helps the *next* run. After adding commands, do `bun run build` in fleet-cli/ manually or run deploy-all twice.
- **Bun on LXC 200**: Required for deploy after #96 migration. Deploy pipeline uses `bun install --production` and `bun dist/index.js`. Install Bun on LXC before first post-migration deploy.
- **Stale process gotcha**: `server stop` now kills legacy `action-proxy` tmux session + `pkill -f 'bun dist/index.js'`. Before this fix (2026-02-23), stale processes could hold port 3100, causing new deploys to serve 404 on all routes while health endpoint still worked (MCP router on old process).
- **Debugging deploy 404s**: If all routes return 404 but `/health` works, check `ps aux | grep "bun dist"` for multiple bun processes. Kill all and restart.
- Sync prompts only: `spacemolt-fleet sync` (no restart needed)
- Server restart needed after fleet-config.json routing/tool changes

## SQLite & Agent Docs
- Tables: agent_diary, agent_docs, agent_signals, proxy_sessions, proxy_game_state, proxy_battle_state, proxy_call_trackers, proxy_tool_calls
- Docs injected at turn start: strategy (full), discoveries/market-intel (last 20 lines)
- MCP tools: write_diary, read_diary, write_doc, read_doc, write_report, search_memory
- **search_memory**: Supports own, cross-agent, and fleet-wide search (#82 DONE). Optional `agent` param (v1) / `id` param (v2). Fleet-web `GET /api/notes/fleet/search` endpoint.
- **Proxy cache persistence** (#81): statusCache/battleCache/callTrackers persisted directly to SQLite (was HTTP, now direct after merge #12). statusCache throttled to 30s per agent. Restored on proxy startup.
- **Real-time tool call logging** (#89 DONE): Direct SQLite writes + in-memory ring buffer (200). SSE stream at `/api/tool-calls/stream` uses subscriber pattern (push, not polling). 7-day retention, 6h auto-prune.

## OAuth
- **Claude Code v2.1.52+**: `~/.claude/.credentials.json` no longer exists. Use `claude setup-token` for long-lived API keys. Token written directly to LXC credentials file.
- Old: Token at `~/.claude/.credentials.json`, synced to LXC via `spacemolt-fleet sync` (broken in v2.1.52+)
- All 5 agents share one OAuth token. `ensure_fresh_token()` checks expiry before fleet start.
- **OAuth mid-run refresh**: `spacemolt-fleet improve` health loop checks token expiry every 5 min, refreshes if ≤30 min remaining. Prevents agents losing turns to expired tokens.
- SOCKS proxies (1081/1082) only route game WebSocket, NOT Claude API calls

## Game Version Notes
- Current: v0.144.0. Key changes through v0.140 handled in proxy/prompts.
- v0.142.5-v0.144.0 (2026-02-24): 5 stability patches in one day. action_pending stuck state affected all agents. v0.144.0 "Server stability instrumentation" — partially cleared stuck state but it returned.
- v0.143.0: "Economic management tools" — details unknown.
- v0.140.0: Removed `state_update`, `poi_arrival`, `poi_departure` WebSocket push messages. Proxy adapted with active `get_status` polling (#106). v0.137.1 rate-limits MCP spec to 1 req/min/IP — schema caching added (#107).
- v0.125: Budget ships (Datum, Foundation), commission_status has required_materials. Summarizer added.
- v0.126: Crafting expansion (new recipes, Nova Terra ion hub), craft param is `count` (not `quantity`).
- v0.130: Finite resource deposits (regenerate over time), storage cap 100k/item/station, rare ore in dozens of systems, one-time delivery missions.
- v0.131: agentlogs API for Discord (TODO #86), login no longer includes captain's log (no proxy impact).
- v0.132.0: supply_commission tool, commission pricing changes (credits-only uses live sell orders).
- v0.132.1: Ship build materials fixed (comp_life_support_unit). v0.132.2: All resources now finite with regeneration.
- v0.133.0: jump/find_route accept display names (not just IDs). Numeric params accept strings. faction deposit_credits/withdraw_credits removed (already blocked). Forum IDs fixed. get_skills shows XP progress. Jump returns result immediately (no more "pending" for jumps). No proxy changes needed — all server-side fixes.
- v0.129: Multi-stop delivery missions (deposit at each destination), pirate wrecks drop ship parts, commission persistence fixes.
- v0.124: session_id in tool calls (proxy strips it). **v2 Zod schema bug**: `serverSchemaToZod()` must skip `session_id` or agents get -32602 validation errors. Fixed 2026-02-23.
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
- **Proxy caches persisted** (#81 DONE): statusCache, battleCache, callTrackers saved directly to SQLite via `cache-persistence.ts` (direct after merge #12). eventBuffers still in-memory only (ephemeral by design).
- **Known issue**: `get_system`/`get_poi`/`get_map` param remaps may be wrong — verify against live server

## Fleet CLI Rewrite (#11)
- New TypeScript CLI at `fleet-cli/` (npm package name: `spacemolt-fleet`), workspace sibling to spacemolt-server
- Root `package.json` with npm workspaces, `tsconfig.base.json` shared config
- All 31 subcommands ported. Old bash script removed from repo root (was causing worktree config issues).
- JSONL parser (183 lines) + summary generator (429 lines) — faithful port with 3 bug fixes over Python original
- Bug fixes vs old: `??` instead of `or` for 0-credit handling, improve files excluded from prev_snap, pruning only counts real snapshots
- 78 tests (13 config + 17 parser + 19 summary + 12 health parsers + 17 output). `npx spacemolt-fleet help` works.
- Forbidden words list is 52 words (not 34 — MEMORY.md was outdated)
- **Worktree support**: `config.ts` uses `git rev-parse --show-toplevel` via `execFileSync` for all paths except SNAPSHOTS_DIR (always main repo). `spacemolt-fleet sync/deploy` from a worktree uses that worktree's files automatically.

## Competitor Clients
- Full comparison at `~/Dendron/vault.personal/projects.spacemolt.client-comparison.md`

## Fleet-Web Visual Overhaul (DONE 2026-02-23)
- Design: `docs/plans/2026-02-23-fleet-web-overhaul-design.md`
- Plan: `docs/plans/2026-02-23-fleet-web-overhaul-plan.md` (18 tasks, 6 phases)
- Stack: React 19 + Next.js 15 (static export) + Tailwind CSS 4 + SMUI theme (Nord palette)
- Galaxy map: react-force-graph-2d, 505 systems, 5 faction colors (solarian/crimson/nebula/outerrim/voidborn)
- Next.js `output: 'export'` to `dist/public/`, served by Express static
- Build: `bun run build` = `build:server` (esbuild) + `build:client` (next build)
- Separate tsconfigs: `tsconfig.json` (server/esbuild), `tsconfig.next.json` (React/Next.js)
- `deploy-all` now self-rebuilds fleet-cli at start (non-fatal)

## Ship Images
- SVG silhouettes as primary display (`ShipImageFallback.tsx`), 13 category-specific shapes
- CDN image (`spacemolt.com/images/ships/catalog/{class_id}.webp`) overlays SVG if available
- Only 5 ships have CDN images: outerrim_prayer, outerrim_loose_change, outerrim_rubble, nebula_floor_price, nebula_motherlode — all others use SVG
- Deleted overengineered caching layer (shipImageCache.ts, useShipImagePrefetch.ts, ShipImagePlaceholder.tsx) — browser handles caching natively
- Ship `class_id` from game state maps to `ship.class` in frontend via `game-state.ts` flatten()

## Fleet-Web UI Gotchas
- **Diary API fields**: Returns `{ id, entry, created_at }` not `{ timestamp, content }`. diary-viewer.tsx and notes/page.tsx must use correct field names.
- **DB timestamps lack timezone**: SQLite timestamps like `"2026-02-24 01:19:17"` need `T` + `Z` appended for correct UTC parsing. FIXED (#120): shared `src/lib/time.ts` with `parseDbTimestamp()` handles this. All frontend timestamp display now uses these shared utils.
- **Contrast stacking**: Never combine `text-muted-foreground` with `opacity-*` — the compound effect makes text invisible on dark backgrounds. Current `muted-foreground: #b0bbd0` gives ~7:1 on card bg (#242933).
- **Map hit areas must scale with zoom**: `nodePointerAreaPaint` needs `minScreenPx / globalScale` same as visual dots, otherwise hit area shrinks below dot size when zoomed out.
- **Game factions**: 5 factions in map data: solarian, crimson, nebula, outerrim, voidborn (+ empty string for neutral). Must all be in EMPIRE_COLORS.
- **Static export routing**: Next.js `output: 'export'` generates `comms.html` etc. Express needs `extensions: ['html']` in `express.static()` or routes fall through to SPA fallback (serves index.html/dashboard for all routes).
- **API↔frontend shape mismatch**: `game-state.ts` `flatten()` must return structure matching frontend `AgentGameState` interface (nested `ship: {...}`, field names `current_system`/`current_poi`/`docked_at_base`). Previous flat structure (`ship_name`, `system`, `poi`) caused ship data to never display.
- **SSE event consistency**: Tool call SSE must send arrays (wrap single records in `[record]`). Backfill must use same event name as live events (`tool_call`, not `backfill`). Frontend guards with `Array.isArray()`.
- **Comms timeline delivery enrichment**: `getCommsLog()` uses LEFT JOIN to `fleet_orders` to replace "Order #N delivered" with actual order message content.
- **Hook types must match server types**: `use-fleet-status.ts` defines its own interfaces — these MUST mirror `shared/types.ts` exactly. Key fields: `state` (not `status`), `healthScore` (not `health`), `actionProxy.healthy` (not `proxyHealthy`), `source` (not `note_type`). When adding API fields, update both the server type AND the hook type.

## Bun Testing Gotchas
- **`mock.module()` is process-global**: Unlike vitest/jest, Bun's `mock.module()` replaces modules in a shared process-wide cache. Mocking `database.js` in one test file poisons ALL other test files in the same run. Never use `mock.module()` for commonly-imported modules — use real `createDatabase(':memory:')` instead.
- **`mock.module()` doesn't work for Node built-ins**: `mock.module('node:child_process')` fails silently — the real module is still used. Use `spyOn` on namespace imports instead.
- **`spyOn` requires namespace imports**: `spyOn(module, 'fn')` only works if the source uses `import * as mod` (namespace import). Named imports (`import { fn }`) capture a direct reference that spyOn can't intercept.
- **`promisify` custom symbol**: Node's `promisify(execFile)` uses a custom symbol to return `{ stdout, stderr }`. Mock/spy functions don't have this symbol, so `promisify(spy)` returns only the first callback arg. Fix: use manual Promise wrapper.
- **`global.fetch` not restored by `mock.restore()`**: Direct assignment to `global.fetch` must be manually saved/restored in beforeAll/afterEach.
- **`bun:sqlite` `db.exec()` supports multi-statement SQL** — works fine for schema creation.
- **Bun spawn pipe EPIPE**: `tar.stdout.pipe(ssh.stdin)` between two `spawn()` processes causes EPIPE + "Unexpected EOF in archive". Fix: use shell pipe via `exec()` instead (delegates piping to OS). Affected `pveTarSync` in fleet-cli deploy.

## External Access & Auth (#116 DONE 2026-02-25)
- **Public**: `gantry.ra726.net` (viewer, read-only). **Admin**: `sm.ra726.net` (CF Access, full control).
- Both hostnames on existing HA CF tunnel, pointing to LXC 200 (`192.168.1.105:3100`).
- Auth config in `fleet-config.json` under `"auth"` key. Three built-in adapters: `none`/`token`/`cloudflare-access`.
- `src/web/auth/` — types, middleware, 3 adapters, factory. 39 tests in `auth.test.ts`.
- **Gotcha**: `/api/auth/me` must be auth-optional (not public) — it needs to run `adapter.authenticate()` to populate `req.auth`, but never block access. Initially was in PUBLIC_ROUTES which skipped auth entirely → always returned viewer.
- **Route classification**: GET=viewer, POST/PUT/DELETE+MCP=admin. MCP localhost bypass (`127.0.0.1`/`::1`/`::ffff:127.0.0.1`).
- **Frontend**: `AuthProvider` wraps app in layout.tsx. `useAuth()` hook returns `{role, identity, isAdmin}`. Admin controls gated: comms SendOrderForm, notes edit button, agent start/stop/restart/inject/shutdown, fleet Start All/Stop All.
- **HealthBar `invert` prop**: Cargo bars use `invert` for green=empty, red=full.
- **CF Access team domain**: `ra726.cloudflareaccess.com`. AUD tag in fleet-config.json.
- **cloudflared installed on LXC 200** (2026-02-25) but not used — tunnel runs through HA.
