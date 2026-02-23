---
name: cache-audit
description: Use when auditing Claude Code prompt caching setup, checking cache efficiency, or when session costs seem high. Triggers on "audit caching", "check cache", "am I breaking the cache", or /cache-audit.
---

# Prompt Cache Audit

Reads your live Claude Code configuration and checks it against 6 prompt caching rules from Anthropic's engineering team. Returns a scored report with actionable fixes.

**Reference:** Thariq Shihipar's "Lessons from Building Claude Code: Prompt Caching Is Everything"

## When Invoked

Run all checks automatically. No confirmation needed. Read files and produce the full report in one pass.

## The 6 Checks

### Check 1 — Prompt Ordering (Static Before Dynamic)

**Read:** `~/.claude/settings.json`, all active `CLAUDE.md` files

**Look for:**
- Static content first, dynamic content last
- Correct order: System prompt -> Tools -> CLAUDE.md -> Session context -> Messages
- Flag: Dynamic content (timestamps, git status, dates) in system prompt itself
- Flag: CLAUDE.md files with session-specific or time-sensitive data
- Pass: CLAUDE.md files that are purely static instructions

**Scoring:**
- PASS: System prompt fully static, dynamic data injected via messages
- WARNING: Some dynamic data in system prompt but low-frequency change
- FAIL: High-churn dynamic content in system prompt

### Check 2 — Dynamic Updates via Messages (not System Prompt Edits)

**Read:** All hook files in `~/.claude/plugins/` and `~/.claude/hooks/`

**Look for:**
- Hooks should output dynamic data as `additionalContext` in JSON response (becomes `<system-reminder>`)
- Flag: Any hook that writes to system prompt files or modifies CLAUDE.md
- Pass: Hooks that return JSON with `additionalContext` key
- Check: Is `currentDate` injected via message or hardcoded in system prompt?
- Check: Is git status coming from hook -> message, or somewhere static?

**Scoring:**
- PASS: All hooks use additionalContext pattern
- FAIL: Any hook modifies system prompt or CLAUDE.md mid-session

### Check 3 — Tool Set Stability (No Add/Remove Mid-Session)

**Read:** `~/.claude/settings.json`, skills, MCP server configurations

**Look for:**
- Tools should be identical at every turn
- Flag: Skills that explicitly add new tools when invoked
- Flag: MCP tools not using deferred loading
- Pass: MCP tools present as lightweight stubs, full schemas loaded on demand via ToolSearch

**Scoring:**
- PASS: Tool set fixed at session start, MCP tools deferred
- WARNING: Some conditional tool loading causing cache misses
- FAIL: Skills or hooks that add/remove tools mid-conversation

### Check 4 — No Mid-Session Model Switches

**Read:** `~/.claude/settings.json`, skills, agent configurations

**Look for:**
- Model field should be set and stable
- Flag: Skills that switch models in the same conversation thread
- Pass: Model switches done via subagents (separate conversations)

**Scoring:**
- PASS: Single model per conversation, subagents for delegation
- FAIL: Inline model switching in same conversation thread

### Check 5 — Dynamic Content Size

**Read:** Hook files, git status injection, session-reminder outputs

**Measure:**
- Estimate size of dynamic content injected per session/turn
- Check git status hook output size
- Check all SessionStart hook output sizes

**Thresholds:**
- < 2k chars/turn: PASS
- 2k-10k chars: WARNING (correct pattern, just expensive)
- > 10k chars: FLAG — consider trimming

**Git status fix for large repos:**
```bash
git branch --show-current
git diff --stat HEAD | tail -5
git status --short | grep "^[^?]" | head -20
```

### Check 6 — Fork Safety (Compaction & Subagent Calls)

**Read:** Compaction configuration, skill invocations that fork context

**Look for:**
- When compaction runs, does summary request reuse same system prompt + tools?
- When skills fork subagents, do they pass same prefix?
- Claude Code handles this correctly by default

**Scoring:**
- PASS: Using Claude Code's built-in compaction
- MANUAL CHECK: Custom compaction or summarization flows

## Output Format

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 PROMPT CACHE AUDIT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Score: X/6

✅/⚠️/❌ Rule 1 — Ordering: [PASS/WARNING/FAIL]
 → [Finding]

✅/⚠️/❌ Rule 2 — Message injection: [PASS/WARNING/FAIL]
 → [Hooks checked and their pattern]

✅/⚠️/❌ Rule 3 — Tool stability: [PASS/WARNING/FAIL]
 → [MCP tool count, defer status]

✅/⚠️/❌ Rule 4 — Model switching: [PASS/WARNING/FAIL]
 → [Model in settings, any inline switches]

✅/⚠️/❌ Rule 5 — Dynamic content size: [PASS/WARNING/FAIL]
 → [Estimated chars/turn per injection point]

✅/⚠️/❌ Rule 6 — Fork safety: [PASS/MANUAL CHECK]
 → [Compaction pattern]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 TOP FIX
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Most impactful change with exact config to implement]
```

## Quick Reference

| Rule | Do | Don't |
|------|----|----|
| 1. Ordering | Static prompt -> CLAUDE.md -> messages | Dynamic data in system prompt |
| 2. Updates | Inject via `<system-reminder>` in messages | Edit system prompt mid-session |
| 3. Tools | Fixed tool set + deferred stubs | Add/remove tools per turn |
| 4. Models | One model per conversation, subagents for switches | Inline model switching |
| 5. Size | Trim dynamic injections to minimum | Dump full git status (40k chars) |
| 6. Forks | Same prefix for compaction/subagents | Different system prompt for summary |
