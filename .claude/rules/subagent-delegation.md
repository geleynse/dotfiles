---
paths: ~
description: When to spawn Sonnet or Opus subagents vs doing work in-session
---

# Subagent Delegation Rules

## Golden Rule

**Delegate when the task is complex, long-running, or requires stronger reasoning.**

Don't try to do everything in the main session. Better to spawn a focused subagent than burn context or degrade quality.

## When to Use Sonnet (Subagent)

- **Design work** — Architecture decisions, design documents, specs
- **Analysis** — Code review, debugging complex issues, architecture analysis
- **Technical writing** — Implementation guides, RFCs, technical documentation
- **Iterative refinement** — Multiple rounds of work (design → review → refine)
- **Cross-cutting concerns** — Tasks that touch multiple systems/repos

**Duration:** 10-30 minutes
**Example:** `/sessions_spawn task="Design Discord integration for SpaceMolt fleet" model="claude-3-5-sonnet-20241022"`

## When to Use Opus (Subagent)

- **Complex problem-solving** — Tricky bugs, system redesigns, novel patterns
- **Large codebase work** — Refactoring, migrations, broad feature builds
- **Decision making** — Weighing multiple options with nuance
- **Cross-domain knowledge** — Tasks requiring deep expertise across areas

**Duration:** 30-60 minutes
**Example:** `/sessions_spawn task="Refactor fleet proxy architecture for rate limiting" model="claude-3-7-opus-20250219"`

## When to Work In-Session (Haiku)

- Quick answers, status checks
- Reading/exploring existing code
- Simple edits or one-liners
- Steering/managing subagents
- Conversational work

## Subagent Task Requirements

**Always include:**
1. **What to create/decide** — Explicit output expectation
   - "Create 4 design documents for features #86, #97, #4, #59"
   - NOT "Design SpaceMolt improvements" (too vague)

2. **What to keep** — Files, branches, or artifacts to preserve
   - "Save all docs to workspace root"
   - "Create feature/ship-images branch with all code files"

3. **Testing/verification** — How you'll know it's done
   - "Include comprehensive tests (100+ lines per file)"
   - "Verify build passes before commit"

4. **Clear definition of done** — No ambiguity
   - "Implementation complete when: (1) all 11 files created, (2) build passes, (3) tests passing, (4) committed to branch"

## After Subagent Completes

1. **Review output** — Read what was created
2. **Test locally** — Build, run tests, verify assumptions
3. **Decide next step** — Merge, iterate, archive, or pivot
4. **Log decision** — Commit notes to workspace/Dendron

## Pattern Examples

### ✅ Good Delegation
> "Spawn Sonnet to design #86 Discord integration. Output: 3 docs (architecture, payloads, implementation guide). Save to workspace root. Done when ready for implementation hand-off."

### ❌ Bad Delegation
> "Do the Discord thing"

### ✅ Good In-Session
> "Read spacemolt-server/src/proxy/nudge-state.ts and review test coverage" (Haiku is fine for this)

### ❌ Bad In-Session
> "Refactor the entire nudge system architecture" (use Sonnet for this)

## Current Patterns We Use

**Working well:**
- Design work via parallel Sonnet subagents (4 agents, specs in parallel)
- Implementation via Sonnet with explicit file requirements
- Code review + debugging in-session (Haiku)
- Fleet improvement analysis via Sonnet subagent

**To remember:**
- Always spawn for design; saves rework
- Always spawn for complex code; better quality
- Keep main session for steering and quick work
