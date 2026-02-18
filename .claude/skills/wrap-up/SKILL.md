---
name: wrap-up
description: Use when user says "wrap up", "close session", "end session",
  "wrap things up", "close out this task", or invokes /wrap-up — runs
  end-of-session checklist for shipping, memory, logging, and self-improvement
---

# Session Wrap-Up

Run five phases in order. Each phase is conversational and inline — no
separate documents. All phases auto-apply without asking; present a
consolidated report at the end.

## Phase 1: Ship It

**Commit:**
1. Run `git status` in each repo/directory touched during the session
   - Home dotfiles repo (`~`)
   - SpaceMolt (`~/claude/spacemolt`)
   - HA config (`~/code/8354-home-assistant`)
   - Any other repos touched
2. If uncommitted changes exist, stage relevant files and commit with a
   descriptive message
3. Push to remote

**File placement check:**
4. If files were created during the session:
   - Documentation (.md) belongs in `~/Dendron/vault.personal/`
   - SpaceMolt data files belong in `~/claude/spacemolt/drifter-gale/` or
     `~/claude/spacemolt/spacemolt-*.json`
   - Fleet agent configs belong in `~/claude/spacemolt/fleet-agents/`
   - Scripts belong in `~/scripts/`
   - Auto-move misplaced files to correct locations

**Deploy:**
5. If SpaceMolt fleet agent prompts were changed, run `spacemolt-fleet sync`
6. If proxy code was changed, run `spacemolt-fleet proxy deploy && spacemolt-fleet proxy restart`
7. For other projects, check for deploy scripts and run them
8. If nothing to deploy, skip — do not ask about manual deployment

**Task cleanup:**
9. Check the task list for in-progress or stale items
10. Mark completed tasks as done, flag orphaned ones

## Phase 2: Remember It

Review what was learned during the session. Place knowledge in the right tier:

| Destination | What goes there |
|-------------|-----------------|
| **Auto memory** (`~/.claude/projects/-home-alan/memory/MEMORY.md`) | Debugging insights, project quirks, patterns discovered |
| **Global `~/.claude/CLAUDE.md`** | Permanent workflow rules, session logging conventions |
| **Project `CLAUDE.md`** (in repo root) | Project-specific conventions, architecture decisions |
| **`.claude/rules/`** | Topic-scoped rules with `paths:` frontmatter |
| **Dendron vault** (`~/Dendron/vault.personal/`) | Infrastructure docs, research notes, reference material |

**Decision framework:**
- Permanent project convention? → CLAUDE.md
- Pattern or insight Claude discovered? → Auto memory
- Infrastructure/device/network fact? → Dendron vault (`infra.*.md`)
- SpaceMolt game knowledge? → Auto memory + data files in `~/claude/spacemolt/`

Note anything important in the appropriate location.

## Phase 3: Session Log

Update (or create) today's session log at
`~/Dendron/vault.personal/projects.log.YYYY.MM.DD.md`.

If creating a new file, include Dendron frontmatter:
```
---
id: projects-log-YYYY-MM-DD
title: "Project Log: YYYY-MM-DD"
desc: "Brief summary of session work"
updated: {epoch}
created: {epoch}
---
```

Append a section covering:
- Tasks completed
- Files modified (grouped by project/repo)
- Key decisions or findings
- Any issues left unresolved

If the file already exists, append a new section and update the `desc` and
`updated` fields in the frontmatter to reflect the new work.

## Phase 4: Publish It

Review the full conversation for material worth publishing. Look for:

- Interesting technical solutions or debugging stories
- Educational content (how-tos, tips, lessons learned)
- Project milestones or feature launches
- Community-relevant announcements

**If publishable material exists:**

Draft the article for the appropriate platform and save to
`~/Dendron/vault.personal/drafts/`. Present suggestions:

```
Potential content to publish:

1. "Title of Post" — 1-2 sentence description.
   Platform: Reddit / HN / blog
   Draft saved to: ~/Dendron/vault.personal/drafts/title-of-post.md
```

Wait for user response. If approved, post or prepare per platform.
If declined, drafts remain for later.

**If no publishable material:** Say "Nothing worth publishing from this
session" and move on.

**Scheduling:** If multiple publishable items, space posts hours apart.
Post the most time-sensitive one first and present a schedule for the rest.

## Phase 5: Review & Improve

Analyze the conversation for self-improvement findings. If the session was
short or routine with nothing notable, say "Nothing to improve" and move on.

**Auto-apply all actionable findings** — do not ask for approval on each one.
Apply changes, commit them, then present a summary.

**Finding categories:**
- **Skill gap** — Things Claude struggled with or needed multiple attempts
- **Friction** — Repeated manual steps that should have been automatic
- **Knowledge** — Facts about projects, preferences, or setup Claude didn't know
- **Automation** — Repetitive patterns that could become skills, hooks, or scripts

**Action types:**
- **CLAUDE.md** — Edit the relevant CLAUDE.md
- **Auto memory** — Save insight to memory files
- **Rules** — Create or update `.claude/rules/` file
- **Skill / Hook** — Document a new skill or hook spec
- **Dendron** — Update infrastructure or reference docs

Present a summary with two sections:

```
Findings (applied):

1. [checkmark] Knowledge: Discovered X about HA entity registry
   → [Dendron] Updated infra.home.assistant.md

2. [checkmark] Friction: Had to manually check fleet status twice
   → [Auto memory] Added fleet check pattern

---
No action needed:

3. Knowledge: Y already documented in MEMORY.md
```

Commit any changes made in this phase.

## Final Report

After all phases, present a one-line summary per phase:

```
Session wrapped:
- Ship: 2 repos committed and pushed
- Memory: Added 1 insight to auto memory
- Log: Updated projects.log.2026.02.18.md
- Publish: 1 draft saved / Nothing worth publishing
- Improve: 1 finding applied, 0 skipped
```
