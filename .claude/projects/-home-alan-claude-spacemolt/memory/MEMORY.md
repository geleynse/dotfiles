# SpaceMolt Project Memory

## Claude Code Custom Commands
- Custom slash commands go in `.claude/commands/`, NOT `.claude/skills/`
- No YAML frontmatter — filename is the command name
- Use absolute paths in command files (other sessions may have different cwd)
- `.claude/*` with `!.claude/commands/` in gitignore to track commands but ignore other .claude files

## Fleet Script (`spacemolt-fleet` — at repo root, NOT scripts/)
- Large text data passed to `jq` via `--rawfile`/`--slurpfile` with temp files, NOT `--arg` (hits ARG_MAX)
- JSONL result lines use `total_cost_usd` not `cost_usd`
- Token data is in `modelUsage` object, not top-level
- Multi-model turns (Opus + Haiku) — select primary model by highest `costUSD`
- Remote exec: `pve_exec()` (root), `pve_exec_user()` (spacemolt user)
- Deploy: `spacemolt-fleet web deploy`, `spacemolt-fleet proxy deploy`
- Sync prompts: `spacemolt-fleet sync` (no restart needed, agents pick up on next turn)
- Decontaminate: `spacemolt-fleet decontaminate [agent...]` (auto-detects from latest snapshot, or specify agents)
- JSONL sync: `pct pull` runs on Proxmox HOST (not inside container). Tar to user home dir to avoid permission issues.

## Fleet Architecture
- 5 agents on LXC 200 (Proxmox container), prompts at `/home/spacemolt/fleet-agents/`
- Current config: all 5 agents on Haiku (all 90s turns).
- SOCKS proxy: sable-thorn→micro:1082, cinder-wake→general:1081, others→direct
- Always check `fleet-agents/fleet-config.json` for latest — models/proxies change frequently
- Proxy restart needed after fleet-config.json changes (routing changes): `spacemolt-fleet proxy restart`
- Action proxy at localhost:3100 on LXC
- Fleet-web at :3000 on LXC
- Snapshots at `fleet-snapshots/` (gitignored). `analyze` generates both `.json` (~288KB) and `-summary.txt` (~1.5KB)
- Summary has: config, agent table, economic table, NEW FEATURES section, delta vs previous, auto-detected issues

## Fleet Config Features (fleet-config.json)
- `agentDeniedTools`: per-agent tool blocking with hint messages (e.g. drifter-gale can't call batch_mine)
- `callLimits`: per-tool session limits applied to all agents (e.g. get_location:3, scan:5, get_events:3)
- Both enforced at proxy level in `checkGuardrails()` — mechanical, not prompt-based

## Fleet Known Issues
- **Gas cloud mining yields zero ore**: lumen-shoal mined 11 times at sirius_gas_cloud, got nothing. Only asteroid belts (POIs with "belt"/"harvesters") produce ore.
- **multi_sell pending at scale**: Small quantities (<60) resolve as "sell completed", large quantities (120+) return "Action 'sell' pending". Agents calling multi_sell 7+ times per turn saturate the tick queue. Credits barely move despite heavy mining. Items are now safe (v0.103.8 returns failed sells to station storage), but credits still stall. Low priority — no item loss risk anymore.
- **Stale proxy processes on LXC**: Fixed — `spacemolt-fleet proxy stop` now runs `fuser -k 3100/tcp` to kill orphans automatically.
- **`spacemolt-fleet stop` vs `stop --force`**: `stop` sends shutdown signals but agents may take time to finish sessions. Use `stop --force` for immediate kill.
- Haiku agents still very verbose (23-104 long texts per 10 turns). Prompt pressure helps but doesn't solve it.
- When all agents share the same bug, check common-rules.txt first — it's probably a prompt-level issue.
- Re-contamination is persistent: agents rewrite contaminated files even after wipes. Use `spacemolt-fleet decontaminate`.
- v2_ tools: game server serves them but we block via DENIED_TOOLS. Agents hallucinate these tool names.
- cinder-wake session_id hallucination: passes `session_id: "already_authenticated"` — proxy strips it.
- Snapshot analysis: agents data is a list (not dict), access via `data['agents'][i]` not `.items()`.
- **OAuth token race**: 5 agents share one OAuth token. Concurrent refresh on expiry causes cascading 401s. Fixed with `ensure_fresh_token()` pre-start check.
- **Push event response corruption** (fixed): Game server push events (combat_update, chat, etc.) were consumed as command responses in FIFO queue, causing one-request-lag in results. Fixed with PUSH_EVENT_TYPES filter in game-client.ts.
- **Contamination feedback loop**: Agents write false claims ("navigation frozen") to diary/strategy docs → docs injected at next turn start → agent reads them and reinforces. Captain's log is auto-redacted by proxy, but docs are NOT. Fix: `spacemolt-fleet decontaminate` + add anti-contamination callouts to agent prompts.
- **Craft cache staleness**: Agents call craft() successfully, immediately check cargo (stale cache), conclude crafting is broken. Fixed by passthrough tick wait — craft is in STATE_CHANGING_TOOLS so cache refreshes before response returns.
- **Jump silent failure (FIXED)**: Root cause was param name mismatch — our proxy exposed `system_id` but game wants `target_system`. Game accepted wrong params as "pending" then silently failed via `action_error` push event (which we weren't handling). Fixed with: param remapping in passthrough handler (`PARAM_REMAPS` in schema.ts), added `action_result`/`action_error` + 11 other missing push event types. Proxy still has stuck-jump detection + warning injection as safety net.
- **Sell auto-listing (zero credits)**: v0.103.3 auto_list means sell() with no station demand creates exchange sell orders. multi_sell shows delta=0 in proxy logs. Agents earn nothing. Need agents to use analyze_market() to find stations with actual demand.

## Proxy Features (action-proxy/src/server.ts)
- Captain's log decontamination: `decontaminateLog()` redacts entries with `CONTAMINATION_WORDS` array
- **Doc decontamination gap**: Proxy only redacts captain's log, NOT agent docs (strategy/discoveries/diary). Contaminated docs persist and get injected into prompts. Must use `spacemolt-fleet decontaminate` to wipe them manually.
- Duplicate call blocker: tracks last call signature per agent
- Per-agent tool blocking: config-driven via `agentDeniedTools` in fleet-config.json
- Call limits: config-driven via `callLimits` + hardcoded `CALL_LIMITS` map
- Hallucinated param stripping: deletes `session_id` from game tool args
- **Parameter remapping**: `PARAM_REMAPS` in schema.ts defines agent→game param names (jump: system_id→target_system, travel: destination_id→target_poi, find_route: destination_system_id→target_system, search_systems: name→query). Applied in passthrough handler before game call. `OUR_SCHEMA_PARAMS` in server.ts mirrors TOOL_SCHEMAS keys for drift detection — keep in sync.
- **Schema drift detection**: `checkSchemaDrift()` in schema.ts runs at startup, compares our param names vs server inputSchema. Filters `session_id` (proxy-stripped). Logs warnings for real mismatches.
- get_status is cached (reads from WebSocket state_update), not a game server call
- **State_update structure**: `{tick, player: {credits, current_system, ...}, ship: {fuel, hull, cargo, ...}}`
- Compound tools: batch_mine, travel_to, jump_route, multi_sell
- **Tick sync (all paths)**: Both compound tools AND passthrough handler now always `waitForTick()` after successful state-changing actions. Navigation tools (jump/travel) get double waitForTick().
- **Auto-undock before jump**: Passthrough handler auto-undocks before jump() — game silently ignores jumps while docked.
- **Nav diagnostic logging**: jump/travel log before/after system/poi/tick to proxy logs for debugging.
- Response summarizers: 22 tools have summarizers in `summarizers.ts`
- **Prompt assembly**: personality-rules.txt references MCP tools (write_diary/write_doc), NOT filesystem paths. Keep in sync when changing note storage.
- Error hints: pattern-matched contextual hints in `error-hints.ts`
- Fleet order injection: `withInjections()` piggybacks orders + critical events onto tool responses
- Session handoff: stores agent state on logout to fleet-web, injects on next login
- DENIED_TOOLS in schema.ts: ~73 tools blocked (faction, cosmetic, auth, v2_, personal facilities, drones, forum delete)
- All proxy features documented in common-rules.txt PROXY FEATURES section — keep in sync

## Analyzer Features (spacemolt-fleet analyze)
- Credits fallback: uses proxy gamestate cache when agent logs show `?`
- Location/cargo fallback: same proxy cache for delta comparisons
- NEW FEATURES section: tracks v0.102+ tool adoption (battle, insurance, salvage, reload)
- Navigation loop detection: flags 3+ jumps to same system
- drifter-gale mining ban auto-detection
- Contamination detection in diary/report files
- Sell outcome tracking: S:OK/S:PEND/S:NOBU from tool results

## Deployment
- LXC 200 via `ssh root@192.168.1.2` then `pct exec 200`
- Fleet-web and action proxy both need build locally then deploy compiled JS
- Run from main repo root: `bash spacemolt-fleet web deploy`, `bash spacemolt-fleet proxy deploy`
- After deploy, restart: `bash spacemolt-fleet web restart`, `bash spacemolt-fleet proxy restart`

## CLAUDE.md Files
- `action-proxy/CLAUDE.md`, `fleet-agents/CLAUDE.md`, `fleet-web/CLAUDE.md` all exist
- Keep them updated when making architectural changes

## SQLite & Agent Docs
- All agent data now in SQLite: agent_diary, agent_docs, agent_signals, proxy_sessions tables
- Agent docs (strategy, discoveries, market-intel) injected into prompts at turn start
  - strategy: full content; discoveries/market-intel: last 20 lines (truncated)
  - Agents told notes are pre-loaded, can use read_doc() for older entries
- Old file dirs (.bak/) deleted from LXC (2026-02-19)
- MCP tools: write_diary, read_diary, write_doc, read_doc, write_report
- pve_exec_user wraps in single quotes — can't use SQL with single quotes. Use pve_exec (root) or upload scripts.

## Game Updates
- v0.102: Combat rework (zones/stances/battle tool), ammo system, insurance, salvage/wrecks
- v0.103: 105+ missions, epic story chains, station chains
- v0.103.3: Insurance claims (buy_insurance, claim_insurance), auto_list on buy/sell, deliver_to on buy, market_analysis mode='detailed'
- v0.103.4: Weapon crafting bootstrap fix (no action needed)
- v0.103.5: Server stability fix — async background ops (no action needed)
- v0.103.6: X-Session-Expires header on HTTP responses, notification polling extends session
- v0.103.8: Item safety — failed sell orders return items to station storage (not destroyed). Cargo space checks on all operations.
- v0.103.9: Travel with base_id fix, attack with POI_id fix (minor)
- v0.103.11: MCP auto-reconnect after server restarts (helps proxy WebSocket stability)
- v0.104.0: analyze_market redesigned — no params, returns skill-based trading insights. market_analysis skill retired. Terminology: "station exchange" + "station manager" (not "NPC market").
- v0.104.3: analyze_market no longer counts your own buy orders as demand signals. Order warnings capped at 3+summary. Master traders (8+) see full remote price ladders.
- v0.105.0: **Major response size reduction.** get_status no longer includes map/XP/log. Dock briefings capped (5 facilities, 20 fills/orders). get_map paginated (100/page). Player lists capped at 20.
- v0.106.0: **Fleet Overhaul.** 268 empire-specific ships across 5 tiers. Empire shipyards (shipyard_showroom, commission_ship, claim_commission). Ship exchange (list_ship_for_sale, browse_ships, buy_listed_ship). 20 new crafting components. Old generic ships retired. get_ships retired → use shipyard_showroom.
- v0.106.4: Playstyle guide references in skill.md (miner, trader, pirate hunter, explorer, base builder).
- v0.107.0: MCP Apps (V2 only) — visual UI widgets. Not relevant to our V1 MCP agents.
- v0.107.1: `get_guide()` — fetch progression guides (miner, trader, pirate-hunter, explorer, base-builder) via MCP.
- v0.108.0: `catalog` on V1 MCP (ships, items, skills, recipes with search/pagination). `get_recipes` and `get_ships` REMOVED. Recipe dependency analysis (full bill of materials).
- v0.109.0: `commission_quote` — preview ship commission costs. Ship help text improved.
- v0.109.6: Craft results show bonus items with `outputs` array. install_mod cargo fix.
- v0.113.0: MCP tool annotations (readOnlyHint, destructiveHint, idempotentHint). Protocol compliance fixes.
- v0.115.0: MCP App widget fixes (V2 only — session accumulation, auto-fetch, no session_id needed). No V1 impact.
- Tool names differ from patch notes — always verify via proxy test output

## OAuth Token Management
- Token stored at `~/.claude/.credentials.json` (local), synced to LXC via `spacemolt-fleet sync`
- All 5 agents share one OAuth token (claudeAiOauth). API keys won't use Claude Code quota — must use OAuth.
- SOCKS proxies (1081/general, 1082/micro) only route game WebSocket traffic, NOT Claude API calls
- `ensure_fresh_token()` in spacemolt-fleet checks expiry, refreshes locally, syncs to LXC before fleet start
- SSH tunnels managed by autossh on LXC (auto-reconnect with ServerAliveInterval=30)
