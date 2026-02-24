---
paths:
  - ~/claude/spacemolt
  - ~/Dendron/vault.personal/projects.log.*
  - ~/Dendron/vault.personal/office*
description: Office organization patterns — bin auditing, inventory tracking, consolidation
---

# Office Organization Rules

## Full Inventory Tracking

We maintain a **live inventory** of all bins as we audit. This is the source of truth.

### Current State (Updated 2026-02-23)
**Large bins (L1-L33):** 33/33 audited
**Small bins (S1-S7, renumbered to #38-#44):** 7/7 audited
**Remaining:** #35, #36, #37 (large), #38 (deferred—waiting for cable tester)

### How to Track

When auditing a new bin:

1. **Read existing inventory** — Check `Dendron/vault.personal/projects.log.*.md` for prior entries
2. **Document contents** — Specific item names, not "stuff"
   ```
   Example: ✅ Bin #22: SparkFun boards (qty 4), Adafruit HDMI cables (qty 2), misc connectors
   NOT: ✅ Bin #22: electronics
   ```
3. **Flag items to move/trash** — Inline notes:
   ```
   - Item name [MOVE to #X reason] or [TRASH: reason]
   ```
4. **Update Dendron log** — Append to `projects.log.YYYY.MM.DD.md` immediately
5. **Commit workspace** — Add findings to memory, commit notes

### Consolidation Phase

When all bins audited:
1. Review items flagged [MOVE]
2. Execute moves (update inventory as we go)
3. Free Hyvens boxes (track how many freed)
4. Update final storage summary

### Metrics to Track

- Bins audited this session
- Items moved between bins
- Items trashed (count + types)
- Hyvens boxes freed (cumulative)
- Time spent (for planning future sessions)

### Example Session Notes

```markdown
## Office Org Session: 2026-02-24

Bins audited: #35, #36, #37 (large)

**Bin #35: Power Supplies**
- 12V adapters (qty 8, labeled)
- USB-C chargers (qty 5, all working)
- XT60 connectors (qty 20)
[MOVE: 2 redundant USB-C to #44 (Electronics)]

**Bin #36: Cables (Misc)**
[TRASH: 4 unlabeled USB cables, 2 damaged micro-HDMI]
[MOVE: 10 good USB-A cables to #22 (Electronics)]

**Bin #37: Testing Equipment**
- Multimeter (Fluke, working)
- Logic analyzer (Saleae, working)
- Oscilloscope probe (1x, needs calibration)

Items moved: 12
Items trashed: 6
Time: 1 hour 20 min
```

## Language

- Be specific (item names, quantities, purposes)
- Use bin numbers consistently (#1, not "bin one")
- Use [MOVE] and [TRASH] tags for actions
- Update inventory after every session, not batched

## When to Pause/Defer

- Cable tester arrives → resume #38
- Storage needs assessment → pause until consolidation plan ready
- Items unclear (test first, then decide) → defer to next session with note

## When to Close

Bins fully audited AND consolidated → mark office org as "COMPLETE" in TODO, update MEMORY
