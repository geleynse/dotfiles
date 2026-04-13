#!/usr/bin/env python3
"""
Factorio 2.0 LTN Blueprint Generator — parameterized stations only.

Generates importable blueprint strings for LTN (Logistic Train Network) train
stations (3-wagon only). All blueprints are parameterized: items are filled in
at paste time rather than baked in.

Required mods:
  - LTN (Logistic Train Network)
  - LTN Combinator (original, 2.0-compatible)
  - Bob's Inserters (for bob-red-inserter on the train-adjacent row)

For full design documentation see:
  ~/Obsidian/vault/projects/factorio-ltn-blueprints.md  (in-game guide)
  ~/Obsidian/vault/projects/factorio-ltn-generator.md   (script & format docs)

Usage:
  python factorio-ltn-generator.py --provider
  python factorio-ltn-generator.py --receiver --param-count 3
  python factorio-ltn-generator.py --dual --input-count 2 --output-count 3
  python factorio-ltn-generator.py --all --output stations.md
  python factorio-ltn-generator.py --config my-stations.json --output out.md

Primitives live in factorio_blueprint.py (same directory).
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from factorio_blueprint import (
    NORTH, EAST, SOUTH, WEST,
    RED, GREEN, OUT_RED, OUT_GREEN, COPPER,
    FACTORIO_VERSION,
    item_signal, virtual_signal,
    Entity, IDCounter,
    add_wire,
    encode_blueprint, decode_blueprint, verify_blueprint,
    build_blueprint, build_book,
    build_power_pole, build_rail as _build_rail_lib, build_curved_rail,
)


# Wrap build_rail to carry the LTN default y.
def build_rail(ids, x, y=None):
    return _build_rail_lib(ids, x, y if y is not None else Y_RAILS, direction=EAST)


# Absolute-position offset. Factorio 2.0's rail grid requires odd-parity absolute
# coordinates for rail/stop placements. If all positions are at even integers
# (or half-integer offsets from even), Factorio snaps during placement. Shifting
# the whole blueprint by (+1, +1) puts rails/stops at odd integers.
WORLD_X_OFFSET = 1
WORLD_Y_OFFSET = 1


def _apply_world_offset(entities):
    """Shift every entity's position by (WORLD_X_OFFSET, WORLD_Y_OFFSET)."""
    for e in entities:
        e.position = {
            "x": e.position["x"] + WORLD_X_OFFSET,
            "y": e.position["y"] + WORLD_Y_OFFSET,
        }


# ─── Layout constants ────────────────────────────────────────────────────────

# Stop centered at origin (0, 0) with direction=WEST (trains approach from east).
# Stop is 2x2, occupies tiles (-1..1) x (-1..1).
#
# LTN 3-entity group — lamp and output CC OVERLAP the stop's 2x2 footprint
# (LTN gives them zero collision so this is legal):
#   ltn-combinator at (-1.5, -0.5)          — 1 tile W of stop NW corner
#   input lamp at    (-0.5, -0.5)           — OVERLAPS stop NW tile
#   output CC at     (-0.5, +0.5) dir=WEST  — OVERLAPS stop SW tile
#
# Row layout:
#   y=-1.5: NORTH combinators row — arith at (+2, -1.5), decider at (+4, -1.5)
#   y=-0.5: LTN stop row — ltn-comb, lamp, allowlist CC at (+2.5, -0.5), poles, chests
#   y=+0.0: stop (2x2 tiles at y=-1..+1)
#   y=+0.5: LTN output CC, north inserters
#   y=+2.0: rails (train occupies y=+1..+3)
#   y=+3.5: SOUTH COMPACT row — poles, bob-red-inserter, chests interleaved
#   y=+4.5: SOUTH combinators row (dual only) — arith at (+1, +4.5), decider at (+3, +4.5)
#   y=+5.5: SOUTH allowlist CC (dual only) at (+1.5, +5.5)
#
# Wagons: 7-tile pitch. First wagon chest/inserter at x=+5.5..+10.5.
# Poles at x=+4.5 (before wagon 1), +11.5 (between 1-2), +18.5 (between 2-3), +25.5 (after 3).

# ─── Station layout (relative to stop center at (0, 0), dir=WEST) ────────────
# Train approaches from the east and stops at x=0. Rails at y=+2.
#
# NORTH = UNLOADING (3 rows):
#   y=-1.5: output inserters (picks chest, drops north to belt) + decider #2
#   y=-0.5: chest row + LTN/lamp + CC/arith/decider #1 inline
#   y=+0.5: bob-red unload inserters (pick wagon south, drop chest north) + output_CC + end pole
#
# SOUTH = LOADING (1 compact row + CC row):
#   y=+3.5: compact row — poles, arith, decider, bob-reds + chests interleaved per wagon
#           Pattern per wagon (6 tiles from wagon_start_x): B C B B C B
#           B picks from adjacent C (custom pickup_position), drops north to wagon.
#   y=+4.5: south allowlist CC
#
# Wagons: 7-tile pitch. First wagon at x=+7.5..+12.5.
# Poles: north chest row at +6.5/+13.5/+20.5, one at +27.5 on bob row.
#        south compact row at -0.5/+6.5/+13.5/+20.5/+27.5.

# Original (unshifted) positions — matches user's in-game-built manual station.
# Note: Factorio shifts entities during placement in a non-idempotent way, but
# we can't pre-compensate (each roundtrip shifts further). Use these positions
# and the user can fix alignment in-game if needed.
Y_OUTPUT_INS = -1.5       # North output inserter row
Y_CHEST_N = -0.5          # North chest/combinator row
Y_UNLOAD_INS = 0.5        # North bob-red unload row
Y_RAILS = 2               # Straight rail row (int — Factorio rail grid; avoid float)
Y_COMPACT_S = 3.5         # South compact row
Y_CC_S_ROW = 4.5          # South allowlist CC row

WAGON_PITCH = 7
WAGON_START_X = 7         # first chest at x=+7.5
INSERTERS_PER_WAGON = 6

# North combinator positions (all on chest row y=-0.5 except decider #2 on y=-1.5)
X_CC_N = 1.5
Y_CC_N = -0.5
X_ARITH_N = 3
Y_ARITH_N = -0.5
X_DECIDER1_N = 5
Y_DECIDER1_N = -0.5
X_DECIDER2_N = 4
Y_DECIDER2_N = -1.5

# South combinator positions (all on compact row y=+3.5 except CC on y=+4.5)
X_ARITH_S = 2
Y_ARITH_S = 3.5
X_DECIDER1_S = 4
Y_DECIDER1_S = 3.5
X_CC_S = 2.5
Y_CC_S = 4.5

# Interleave pattern per wagon (6 tile slots): B C B B C B (0-indexed offsets from wagon start)
SOUTH_CHEST_OFFSETS = (1, 4)
SOUTH_BOB_OFFSETS = (0, 2, 3, 5)

# Each south bob-red has a direction and pickup_position (relative to bob position).
# Pattern per wagon slot (offset, direction, pickup_relative):
#   offset 0: B picks from C at offset+1 (east). dir=8, pickup=[+1, 0]
#   offset 2: B picks from C at offset-1 (west, same C as offset 0). dir=4, pickup=[0, +1]
#   offset 3: B picks from C at offset+1 (east, the 2nd C at wagon offset 4). dir=12, pickup=[0, +1]
#   offset 5: B picks from C at offset-1 (west, the 2nd C). dir=8, pickup=[-1, 0]
# (Directions copied verbatim from user's working manual.)
SOUTH_BOB_CONFIG = {
    0: {"direction": 8,  "pickup_position": [1, 0]},
    2: {"direction": 4,  "pickup_position": [0, 1]},
    3: {"direction": 12, "pickup_position": [0, 1]},
    5: {"direction": 8,  "pickup_position": [-1, 0]},
}

def _pole_x_positions_north(wagons):
    """North chest-row poles: between combinators and wagon 1, and between wagon gaps.
    W=3 → x=[+6.5, +13.5, +20.5]. Last end pole is on bob row separately.
    """
    return [(WAGON_START_X - 0.5) + w * WAGON_PITCH for w in range(wagons)]


def _pole_x_positions_south(wagons):
    """South compact-row poles: leading + wagon boundaries.
    W=3 → x=[-0.5, +6.5, +13.5, +20.5, +27.5].
    """
    return [-0.5] + [(WAGON_START_X - 0.5) + w * WAGON_PITCH for w in range(wagons + 1)]


# ─── Shared entity builders ──────────────────────────────────────────────────

def build_allowlist_cc(eid: int, position: dict, items: list[str]) -> Entity:
    """Constant combinator with allowlist items (each = 1). Uses Factorio 2.0
    `sections` format so the blueprint doesn't trigger auto-migration on import.

    If an item name starts with "parameter-" (e.g. "parameter-0"), it's treated as
    a blueprint parameter reference — pasting prompts the user to fill it in.
    """
    filters = [
        {
            "index": i + 1,
            "name": name,
            "quality": "normal",
            "comparator": "=",
            "count": 1,
        }
        for i, name in enumerate(items)
    ]
    return Entity(
        entity_number=eid,
        name="constant-combinator",
        position=position,
        control_behavior={"sections": {"sections": [{"index": 1, "filters": filters}]}},
    )


def build_parameter_defs(names: list[str]) -> list[dict]:
    """Build blueprint-level parameter definitions. `names` is the human-readable
    label for each slot (e.g. ["Input 1", "Input 2", "Output 1", "Output 2"]).
    Returns a list of dicts ready for the blueprint's `parameters` field.
    """
    return [
        {
            "type": "id",
            "name": names[i],
            "id": f"parameter-{i}",
            "quality-condition": {"quality": "normal", "comparator": "="},
        }
        for i in range(len(names))
    ]


def build_provider_decider(eid: int, position: dict, direction: int = EAST,
                           output_green: bool = False) -> Entity:
    """Decider for provider stations: per-network red Each > 0 AND green Each > 0.

    Uses Factorio 2.0 per-network conditions to check BOTH:
      - Red wire: remaining = delivery − train_contents > 0  (still items to load)
      - Green wire: allowlist signal > 0  (item is permitted)
    Output copies count from red wire only (the remaining amount).
    When remaining hits 0, signal vanishes and inserter filter clears.

    Default direction=EAST: 2-tile-wide horizontal layout (position.y at INT+0.5).
    output_green=True: output on green terminal (for inventory filter decider #2, wired via OUT_GREEN).
    output_green=False: output on red terminal (for inserter filter decider #1, wired via OUT_RED).
    """
    return Entity(
        entity_number=eid,
        name="decider-combinator",
        position=position,
        direction=direction,
        control_behavior={
            "decider_conditions": {
                "conditions": [
                    {
                        "first_signal": virtual_signal("signal-each"),
                        "comparator": ">",
                        "first_signal_networks": {"red": True, "green": False},
                    },
                    {
                        "first_signal": virtual_signal("signal-each"),
                        "comparator": ">",
                        "first_signal_networks": {"red": False, "green": True},
                    },
                ],
                "outputs": [{
                    "signal": virtual_signal("signal-each"),
                    "networks": {"red": not output_green, "green": output_green},
                }],
            },
        },
    )


def build_inverter(eid: int, position: dict, direction: int = EAST) -> Entity:
    """Arithmetic combinator: Each * -1.

    Default direction=EAST: 2-tile-wide horizontal (position.y at INT+0.5).
    """
    return Entity(
        entity_number=eid,
        name="arithmetic-combinator",
        position=position,
        direction=direction,
        control_behavior={
            "arithmetic_conditions": {
                "first_signal": virtual_signal("signal-each"),
                "second_constant": -1,
                "operation": "*",
                "output_signal": virtual_signal("signal-each"),
            },
        },
    )


# ─── LTN stop group builder (3 placeable entities) ───────────────────────────

def build_ltn_stop_group(ids, station_name, ltn_tags):
    """Create the 3 LTN stop entities. Lamp and output CC OVERLAP the stop footprint
    (LTN gives them zero collision so this is valid):
      - stop at (0, 0) dir=WEST, 2x2
      - input lamp at (-0.5, -0.5) — overlaps stop NW tile, always_on
      - output CC at (-0.5, +0.5) dir=WEST — overlaps stop SW tile

    Returns (stop_id, input_lamp_id, output_cc_id, entities_list).
    """
    entities = []

    stop_id = ids.next()
    entities.append(Entity(
        entity_number=stop_id,
        name="logistic-train-stop",
        position={"x": 0, "y": 0},
        direction=WEST,
        station=station_name,
        control_behavior={
            "read_from_train": True,
            "train_stopped_signal": virtual_signal("signal-T"),
        },
    ))

    input_lamp_id = ids.next()
    entities.append(Entity(
        entity_number=input_lamp_id,
        name="logistic-train-stop-input",
        position={"x": -0.5, "y": -0.5},
        control_behavior={
            "circuit_condition": {
                "first_signal": virtual_signal("signal-anything"),
                "constant": 0,
                "comparator": ">",
            },
            "use_colors": True,
        },
        always_on=True,
    ))

    output_cc_id = ids.next()
    entities.append(Entity(
        entity_number=output_cc_id,
        name="logistic-train-stop-output",
        position={"x": -0.5, "y": 0.5},
        direction=WEST,
        control_behavior={"sections": {"sections": [{"index": 1}]}},
    ))

    return stop_id, input_lamp_id, output_cc_id, entities


def build_ltn_combinator(ids, ltn_tags):
    """Create the ltn-combinator at (-1.5, -0.5), 1 tile west of stop NW corner.
    Tags set provider/requester flags for LTN. Returns (id, entity).
    """
    eid = ids.next()
    ent = Entity(
        entity_number=eid,
        name="ltn-combinator",
        position={"x": -1.5, "y": -0.5},
        control_behavior={"sections": {"sections": [{"index": 1}]}},
        tags={"ltnc": {"provider": False, "requester": False, **ltn_tags}},
    )
    return eid, ent


# ─── Station generators ──────────────────────────────────────────────────────


def _build_ltn_head(ids, station_name, ltn_tags, entities, wires):
    """Build stop + input lamp + output_CC + ltn-combinator + config wire.
    Returns (stop_id, input_lamp_id, output_cc_id, ltn_id).
    """
    stop_id, input_lamp_id, output_cc_id, stop_ents = build_ltn_stop_group(
        ids, station_name, ltn_tags
    )
    entities.extend(stop_ents)
    ltn_id, ltn_ent = build_ltn_combinator(ids, ltn_tags)
    entities.append(ltn_ent)
    add_wire(wires, ltn_id, GREEN, input_lamp_id, GREEN)
    return stop_id, input_lamp_id, output_cc_id, ltn_id


def _build_north_side(
    ids, entities, wires, wagons,
    *,
    output_cc_id, stop_id, input_lamp_id,
    allowlist,
    mode,  # "unload" (receiver/dual-north) or "load" (unused in new design; kept for parity)
):
    """NORTH 3-row side — used for receiver standalone and dual's unloading half.

    Layout (stop-rel):
      y=-1.5: output inserters (picks chest, drops north) + decider #2 (inventory filter)
      y=-0.5: LTN, lamp, CC, arith, decider #1, chests (combinators all on chest row)
      y=+0.5: bob-red inserters (wagon → chest for unload) + end pole

    Poles:
      chest row: x=+6.5, +13.5, +20.5 (between combinators and wagons, and between wagon gaps)
      bob-red row: x=+27.5 (end, after last wagon)

    Wiring (receiver / unload):
      stop RED → decider #1 RED  (cargo drives filter; when wagon empty signal clears)
      output_CC RED → decider #1 RED  (LTN delivery signal; negative, sums with cargo)
      CC GREEN → decider #1 GREEN
      CC GREEN → decider #2 GREEN
      chest chain RED → decider #2 RED
      decider #2 OUT_GREEN → lamp GREEN
      decider #1 OUT_RED → first chest-row pole RED → bob-red chain (cross-row to y=+0.5)
      chest chain RED only (no green chain — decider #2 OUT_GREEN is the sole inventory path to lamp)

    Returns (pole_ids_chest_row + [end_pole], chest_ids, inserter_ids, bob_ids).
    """
    # Combinators on chest row (y=-0.5)
    cc_id = ids.next()
    entities.append(build_allowlist_cc(cc_id, {"x": X_CC_N, "y": Y_CC_N}, allowlist))

    decider1_id = ids.next()
    entities.append(build_provider_decider(decider1_id, {"x": X_DECIDER1_N, "y": Y_DECIDER1_N}, direction=EAST))

    # Decider #2 (inventory filter) on output-inserter row (y=-1.5), dir=WEST
    # output_green=True: wired via OUT_GREEN to lamp GREEN
    decider2_id = ids.next()
    entities.append(build_provider_decider(decider2_id, {"x": X_DECIDER2_N, "y": Y_DECIDER2_N}, direction=WEST, output_green=True))

    # Unload wiring: stop cargo + output_CC → decider #1 RED (remaining = cargo + delivery)
    # Cargo is positive; LTN delivery is negative; when cargo drains to 0, signal vanishes.
    add_wire(wires, stop_id, RED, decider1_id, RED)
    add_wire(wires, output_cc_id, RED, decider1_id, RED)
    add_wire(wires, cc_id, GREEN, decider1_id, GREEN)

    # Decider #2 (inventory filter): CC green + chest-chain red → OUT_GREEN → lamp green
    add_wire(wires, cc_id, GREEN, decider2_id, GREEN)
    add_wire(wires, decider2_id, OUT_GREEN, input_lamp_id, GREEN)

    # Poles on chest row (between combinators and wagons, and wagon gaps)
    chest_pole_ids = []
    for x in _pole_x_positions_north(wagons):
        pid, pent = build_power_pole(ids, x, Y_CHEST_N)
        entities.append(pent)
        chest_pole_ids.append(pid)

    # End pole on bob-red row (just past last wagon)
    end_pole_id, end_pole_ent = build_power_pole(
        ids, (WAGON_START_X - 0.5) + wagons * WAGON_PITCH, Y_UNLOAD_INS
    )
    entities.append(end_pole_ent)

    # Output inserters (y=-1.5) and chests (y=-0.5) and bob-reds (y=+0.5)
    insert_ids, chest_ids, bob_ids = [], [], []
    for w in range(wagons):
        wagon_start = WAGON_START_X + w * WAGON_PITCH
        for i in range(INSERTERS_PER_WAGON):
            x = wagon_start + i + 0.5

            # Output inserter (placeholder — user configures direction in-game to match belt)
            iid = ids.next()
            entities.append(Entity(iid, "inserter", {"x": x, "y": Y_OUTPUT_INS}, direction=SOUTH))
            insert_ids.append(iid)

            # Chest
            cid = ids.next()
            entities.append(Entity(cid, "steel-chest", {"x": x, "y": Y_CHEST_N}))
            chest_ids.append(cid)

            # Bob-red inserter (unload: picks wagon south, drops chest north; dir=8/SOUTH in manual)
            bid = ids.next()
            entities.append(Entity(bid, "bob-red-inserter", {"x": x, "y": Y_UNLOAD_INS}, direction=SOUTH,
                                   control_behavior={"circuit_set_filters": True}, use_filters=True))
            bob_ids.append(bid)

    # Chest chain RED → decider #2 RED (filtered inventory path; decider #2 OUT_GREEN → lamp)
    # No green chain — adding a direct chest GREEN → lamp would double-count inventory.
    for i in range(len(chest_ids) - 1):
        add_wire(wires, chest_ids[i], RED, chest_ids[i + 1], RED)
    add_wire(wires, chest_ids[0], RED, decider2_id, RED)

    # Bob-red RED chain: decider #1 OUT_RED → first chest-row pole RED (cross row via wire)
    add_wire(wires, decider1_id, OUT_RED, chest_pole_ids[0], RED)
    # Each chest-row pole feeds its wagon's bob-red chain via RED, and end pole too.
    all_poles = chest_pole_ids + [end_pole_id]
    for w in range(wagons):
        group = bob_ids[w * INSERTERS_PER_WAGON:(w + 1) * INSERTERS_PER_WAGON]
        add_wire(wires, all_poles[w], RED, group[0], RED)
        for i in range(len(group) - 1):
            add_wire(wires, group[i], RED, group[i + 1], RED)
        add_wire(wires, group[-1], RED, all_poles[w + 1], RED)

    # Copper along chest-row poles, and link end pole to last chest pole via copper
    for i in range(len(chest_pole_ids) - 1):
        add_wire(wires, chest_pole_ids[i], COPPER, chest_pole_ids[i + 1], COPPER)
    add_wire(wires, chest_pole_ids[-1], COPPER, end_pole_id, COPPER)

    return all_poles, chest_ids, decider1_id, decider2_id


def _build_south_compact_side(
    ids, entities, wires, wagons,
    *,
    output_cc_id, stop_id, input_lamp_id,
    allowlist,
):
    """SOUTH compact side — interleaved bob-reds + chests on a single row (LOADING).

    Layout (stop-rel):
      y=+3.5: poles (-0.5, +6.5, +13.5, +20.5, +27.5), arith(+2), decider(+4),
              interleaved pattern per wagon (offsets from wagon_start_x):
                 0: bob-red (picks east chest, drops wagon)
                 1: chest
                 2: bob-red (picks west chest, drops wagon)
                 3: bob-red (picks east chest, drops wagon)
                 4: chest
                 5: bob-red (picks west chest, drops wagon)
      y=+4.5: south allowlist CC (alone)

    Wiring (provider / load):
      stop RED → south arith RED (for subtracting train contents)
      arith OUT_RED → south decider RED
      output_CC RED → south decider RED (delivery remaining)
      south CC GREEN → south decider GREEN (allowlist)
      south decider OUT_RED → first compact-row pole RED → bob-red chain
      chest chain GREEN → lamp GREEN (inventory reading)
    """
    # Combinators
    arith_id = ids.next()
    entities.append(build_inverter(arith_id, {"x": X_ARITH_S, "y": Y_ARITH_S}, direction=EAST))

    decider_id = ids.next()
    entities.append(build_provider_decider(decider_id, {"x": X_DECIDER1_S, "y": Y_DECIDER1_S}, direction=EAST))

    cc_id = ids.next()
    entities.append(build_allowlist_cc(cc_id, {"x": X_CC_S, "y": Y_CC_S}, allowlist))

    # Wiring — provider-style: stop cargo + output_CC sum, inverted arith
    add_wire(wires, stop_id, RED, arith_id, RED)
    add_wire(wires, arith_id, OUT_RED, decider_id, RED)
    add_wire(wires, output_cc_id, RED, decider_id, RED)
    add_wire(wires, cc_id, GREEN, decider_id, GREEN)

    # Poles on compact row (leading pole + wagon-boundary poles)
    pole_ids = []
    for x in _pole_x_positions_south(wagons):
        pid, pent = build_power_pole(ids, x, Y_COMPACT_S)
        entities.append(pent)
        pole_ids.append(pid)

    # Decider OUT_RED → first "boundary" pole (index 1, at x=+6.5) RED — this is the one
    # just before first wagon, feeding the bob-red chain downstream.
    add_wire(wires, decider_id, OUT_RED, pole_ids[1], RED)

    # Build interleaved row per wagon
    chest_ids, bob_ids = [], []
    for w in range(wagons):
        wagon_start = WAGON_START_X + w * WAGON_PITCH
        for offset in SOUTH_CHEST_OFFSETS:
            x = wagon_start + offset + 0.5
            cid = ids.next()
            entities.append(Entity(cid, "steel-chest", {"x": x, "y": Y_COMPACT_S}))
            chest_ids.append(cid)

        for offset in SOUTH_BOB_OFFSETS:
            x = wagon_start + offset + 0.5
            cfg = SOUTH_BOB_CONFIG[offset]
            bid = ids.next()
            entities.append(Entity(
                entity_number=bid,
                name="bob-red-inserter",
                position={"x": x, "y": Y_COMPACT_S},
                direction=cfg["direction"],
                pickup_position=cfg["pickup_position"],
                control_behavior={"circuit_set_filters": True},
                use_filters=True,
            ))
            bob_ids.append(bid)

    # Chest chain GREEN → lamp GREEN (direct inventory reading, matches manual)
    for i in range(len(chest_ids) - 1):
        add_wire(wires, chest_ids[i], GREEN, chest_ids[i + 1], GREEN)
    add_wire(wires, chest_ids[0], GREEN, input_lamp_id, GREEN)

    # Bob-red chain RED per wagon, connected via boundary poles
    for w in range(wagons):
        group = bob_ids[w * 4:(w + 1) * 4]  # 4 bob-reds per wagon on compact row
        pole_before = pole_ids[1 + w]      # boundary pole before this wagon
        pole_after = pole_ids[1 + w + 1]   # boundary pole after this wagon
        add_wire(wires, pole_before, RED, group[0], RED)
        for i in range(len(group) - 1):
            add_wire(wires, group[i], RED, group[i + 1], RED)
        add_wire(wires, group[-1], RED, pole_after, RED)

    # Copper along compact-row poles
    for i in range(len(pole_ids) - 1):
        add_wire(wires, pole_ids[i], COPPER, pole_ids[i + 1], COPPER)

    return pole_ids, chest_ids, decider_id


def _add_rails_with_curves(ids, wagons, entities):
    """13 straight rails (y=+2, 2-tile pitch) + 2 curved rails at ends.
    W=3 → straight rails x=0..+24, curved at x=-3 (dir=WEST) and x=+27 (dir=6).
    """
    straight_end_x = wagons * WAGON_PITCH + 3
    for x in range(0, straight_end_x + 1, 2):
        _, rent = build_rail(ids, x, Y_RAILS)
        entities.append(rent)
    _, cw = build_curved_rail(ids, -3, Y_RAILS, WEST)
    entities.append(cw)
    _, ce = build_curved_rail(ids, straight_end_x + 3, Y_RAILS, 6)
    entities.append(ce)


def _build_provider(allowlist, wagons=3, station_name="LTN Provider"):
    """Internal: provider station builder that accepts a specific allowlist.
    Public API uses `generate_provider` (parameterized). This helper exists so
    parameterized mode can pass "parameter-N" names as the allowlist.
    """
    ids = IDCounter()
    entities, wires = [], []
    stop_id, input_lamp_id, output_cc_id, _ = _build_ltn_head(
        ids, station_name, {"provider": True}, entities, wires
    )
    # Provider = loading: we want decider_1 RED = output_CC + (-stop_cargo). Use north side with
    # provider wiring: arith input is stop (not output_CC), plus extra output_CC into decider.
    # Combinators on chest row
    cc_id = ids.next()
    entities.append(build_allowlist_cc(cc_id, {"x": X_CC_N, "y": Y_CC_N}, allowlist))
    arith_id = ids.next()
    entities.append(build_inverter(arith_id, {"x": X_ARITH_N, "y": Y_ARITH_N}, direction=EAST))
    decider1_id = ids.next()
    entities.append(build_provider_decider(decider1_id, {"x": X_DECIDER1_N, "y": Y_DECIDER1_N}, direction=EAST))
    decider2_id = ids.next()
    entities.append(build_provider_decider(decider2_id, {"x": X_DECIDER2_N, "y": Y_DECIDER2_N}, direction=WEST, output_green=True))

    add_wire(wires, stop_id, RED, arith_id, RED)
    add_wire(wires, arith_id, OUT_RED, decider1_id, RED)
    add_wire(wires, output_cc_id, RED, decider1_id, RED)
    add_wire(wires, cc_id, GREEN, decider1_id, GREEN)
    add_wire(wires, cc_id, GREEN, decider2_id, GREEN)
    add_wire(wires, decider2_id, OUT_GREEN, input_lamp_id, GREEN)

    # Poles + chests + inserters + bob-reds
    chest_pole_ids = []
    for x in _pole_x_positions_north(wagons):
        pid, pent = build_power_pole(ids, x, Y_CHEST_N)
        entities.append(pent)
        chest_pole_ids.append(pid)
    end_pole_id, end_pole_ent = build_power_pole(
        ids, (WAGON_START_X - 0.5) + wagons * WAGON_PITCH, Y_UNLOAD_INS
    )
    entities.append(end_pole_ent)

    chest_ids, bob_ids = [], []
    for w in range(wagons):
        wagon_start = WAGON_START_X + w * WAGON_PITCH
        for i in range(INSERTERS_PER_WAGON):
            x = wagon_start + i + 0.5
            iid = ids.next()
            entities.append(Entity(iid, "inserter", {"x": x, "y": Y_OUTPUT_INS}, direction=SOUTH))
            cid = ids.next()
            entities.append(Entity(cid, "steel-chest", {"x": x, "y": Y_CHEST_N}))
            chest_ids.append(cid)
            bid = ids.next()
            entities.append(Entity(bid, "bob-red-inserter", {"x": x, "y": Y_UNLOAD_INS}, direction=SOUTH,
                                   control_behavior={"circuit_set_filters": True}, use_filters=True))
            bob_ids.append(bid)

    # Chest chain RED → decider #2 RED (filtered inventory path; decider #2 OUT_GREEN → lamp)
    # No green chain — direct chest GREEN → lamp would double-count inventory.
    for i in range(len(chest_ids) - 1):
        add_wire(wires, chest_ids[i], RED, chest_ids[i + 1], RED)
    add_wire(wires, chest_ids[0], RED, decider2_id, RED)

    all_poles = chest_pole_ids + [end_pole_id]
    add_wire(wires, decider1_id, OUT_RED, chest_pole_ids[0], RED)
    for w in range(wagons):
        group = bob_ids[w * INSERTERS_PER_WAGON:(w + 1) * INSERTERS_PER_WAGON]
        add_wire(wires, all_poles[w], RED, group[0], RED)
        for i in range(len(group) - 1):
            add_wire(wires, group[i], RED, group[i + 1], RED)
        add_wire(wires, group[-1], RED, all_poles[w + 1], RED)

    for i in range(len(chest_pole_ids) - 1):
        add_wire(wires, chest_pole_ids[i], COPPER, chest_pole_ids[i + 1], COPPER)
    add_wire(wires, chest_pole_ids[-1], COPPER, end_pole_id, COPPER)

    _add_rails_with_curves(ids, wagons, entities)
    _apply_world_offset(entities)
    return build_blueprint(station_name, entities, wires)


def _build_receiver(allowlist, wagons=3, station_name="LTN Receiver"):
    """Internal: receiver builder that accepts a specific allowlist."""
    ids = IDCounter()
    entities, wires = [], []
    stop_id, input_lamp_id, output_cc_id, _ = _build_ltn_head(
        ids, station_name, {"requester": True}, entities, wires
    )
    _build_north_side(
        ids, entities, wires, wagons,
        output_cc_id=output_cc_id, stop_id=stop_id, input_lamp_id=input_lamp_id,
        allowlist=allowlist, mode="unload",
    )
    _add_rails_with_curves(ids, wagons, entities)
    _apply_world_offset(entities)
    return build_blueprint(station_name, entities, wires)


def _build_dual(provide_allowlist, request_allowlist, wagons=3, station_name="LTN Dual"):
    """Internal: dual builder that accepts specific allowlists per side."""
    ids = IDCounter()
    entities, wires = [], []
    stop_id, input_lamp_id, output_cc_id, _ = _build_ltn_head(
        ids, station_name, {"provider": True, "requester": True}, entities, wires
    )
    north_poles, _, _, _ = _build_north_side(
        ids, entities, wires, wagons,
        output_cc_id=output_cc_id, stop_id=stop_id, input_lamp_id=input_lamp_id,
        allowlist=request_allowlist, mode="unload",
    )
    south_poles, _, _ = _build_south_compact_side(
        ids, entities, wires, wagons,
        output_cc_id=output_cc_id, stop_id=stop_id, input_lamp_id=input_lamp_id,
        allowlist=provide_allowlist,
    )
    # Link north end pole (on bob row) to south's last pole via copper (tie electrical networks)
    add_wire(wires, north_poles[-1], COPPER, south_poles[-1], COPPER)

    _add_rails_with_curves(ids, wagons, entities)
    _apply_world_offset(entities)
    return build_blueprint(station_name, entities, wires)


# ─── Public station generators (all parameterized) ───────────────────────────
# Stations prompt the user to fill in items at paste time. Parameter signals are
# named "parameter-0", "parameter-1", etc. Human-readable labels come from the
# blueprint-level `parameters` field (e.g. "Input 1", "Output 1").

def _param_allowlist(count: int, start_index: int = 0) -> list[str]:
    return [f"parameter-{start_index + i}" for i in range(count)]


def generate_provider(param_count=2, wagons=3, station_name="LTN Provider"):
    """Provider station with `param_count` output slots prompted at paste time."""
    bp = _build_provider(_param_allowlist(param_count), wagons, station_name)
    labels = [f"Output {i+1}" for i in range(param_count)]
    bp["blueprint"]["parameters"] = build_parameter_defs(labels)
    return bp


def generate_receiver(param_count=2, wagons=3, station_name="LTN Receiver"):
    """Receiver station with `param_count` input slots prompted at paste time."""
    bp = _build_receiver(_param_allowlist(param_count), wagons, station_name)
    labels = [f"Input {i+1}" for i in range(param_count)]
    bp["blueprint"]["parameters"] = build_parameter_defs(labels)
    return bp


def generate_dual(input_count=2, output_count=2, wagons=3, station_name="LTN Dual"):
    """Dual station: `input_count` unload (north) slots + `output_count` load
    (south) slots, all prompted at paste. Parameter indices:
      0..input_count-1        → request (Input N) on north CC
      input_count..total-1    → provide (Output N) on south CC
    """
    request = _param_allowlist(input_count, start_index=0)
    provide = _param_allowlist(output_count, start_index=input_count)
    bp = _build_dual(provide_allowlist=provide, request_allowlist=request,
                     wagons=wagons, station_name=station_name)
    labels = [f"Input {i+1}" for i in range(input_count)] + \
             [f"Output {i+1}" for i in range(output_count)]
    bp["blueprint"]["parameters"] = build_parameter_defs(labels)
    return bp


# ─── Output formatting ───────────────────────────────────────────────────────

def format_section(title: str, bp_dict: dict, bp_string: str) -> str:
    if "blueprint" in bp_dict:
        ent_count = len(bp_dict["blueprint"].get("entities", []))
        wire_count = len(bp_dict["blueprint"].get("wires", []))
        meta = f"**Entities:** {ent_count} | **Wires:** {wire_count}"
    else:
        bp_count = len(bp_dict["blueprint_book"].get("blueprints", []))
        meta = f"**Blueprints:** {bp_count}"

    return "\n".join([
        f"## {title}", "",
        meta, "",
        "### Blueprint String (paste into Factorio)", "",
        "```", bp_string, "```", "",
    ])


def generate_output(sections: list[tuple[str, dict, str]], output_path: Optional[str] = None):
    lines = [
        "# LTN Station Blueprints",
        "",
        "Generated by `factorio-ltn-generator.py` for Factorio 2.0 + LTN.",
        "",
        "All LTN entities (stop, input lamp, output yellow CC) are included",
        "in the blueprint — no manual post-placement wiring is required.",
        "After placing, configure the **LTN Combinator** with desired items and",
        "counts (positive = provide, negative = request), and set the",
        "**Allowlist Constant Combinator** to limit which items are loaded/unloaded.",
        "",
        "Required mods: **LTN**, **LTN Combinator** (original, 2.0-compatible),",
        "**Bob's Inserters** (for `bob-red-inserter` on south compact rows).",
        "",
        "---",
        "",
    ]
    for title, bp_dict, bp_string in sections:
        lines.append(format_section(title, bp_dict, bp_string))
        lines.append("---\n")

    content = "\n".join(lines)
    if output_path:
        with open(output_path, "w") as f:
            f.write(content)
        print(f"Written to {output_path}", file=sys.stderr)
    else:
        print(content)


# ─── CLI ──────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate parameterized Factorio 2.0 LTN station blueprints.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --provider
  %(prog)s --receiver --param-count 3
  %(prog)s --dual --input-count 2 --output-count 3
  %(prog)s --all --output stations.md

All stations are parameterized — items are filled in at paste time in Factorio.
--all generates a blueprint book with provider, receiver, and dual variants.
        """,
    )

    mode = parser.add_argument_group("Station type")
    mode.add_argument("--provider", action="store_true", help="Generate provider station")
    mode.add_argument("--receiver", action="store_true", help="Generate receiver station")
    mode.add_argument("--dual", action="store_true", help="Generate dual-mode station")
    mode.add_argument("--all", action="store_true",
                      help="Generate book with provider/receiver/dual, 3 wagons each")

    opts = parser.add_argument_group("Options")
    opts.add_argument("--wagons", type=int, default=3, choices=(3,),
                      help="Cargo wagons per train: only 3 supported.")
    opts.add_argument("--param-count", type=int, default=2, metavar="N",
                      help="Parameter slots per side for provider/receiver (default: 2)")
    opts.add_argument("--input-count", type=int, default=None, metavar="N",
                      help="Dual-mode input (unload) slot count (default: --param-count)")
    opts.add_argument("--output-count", type=int, default=None, metavar="N",
                      help="Dual-mode output (load) slot count (default: --param-count)")
    opts.add_argument("--station-name", type=str, default=None,
                      help="Custom station name")
    opts.add_argument("--config", type=str, metavar="FILE",
                      help="JSON config file for all stations")
    opts.add_argument("--output", "-o", type=str, metavar="FILE",
                      help="Output markdown file (default: stdout)")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    sections: list[tuple[str, dict, str]] = []
    input_count = args.input_count if args.input_count is not None else args.param_count
    output_count = args.output_count if args.output_count is not None else args.param_count

    # ─── Config file mode ───
    if args.config:
        with open(args.config) as f:
            config = json.load(f)

        blueprints = []
        if "provider" in config:
            c = config["provider"]
            blueprints.append(generate_provider(
                param_count=c.get("param_count", 2),
                wagons=c.get("wagons", 3),
                station_name=c.get("station_name", "LTN Provider"),
            ))
        if "receiver" in config:
            c = config["receiver"]
            blueprints.append(generate_receiver(
                param_count=c.get("param_count", 2),
                wagons=c.get("wagons", 3),
                station_name=c.get("station_name", "LTN Receiver"),
            ))
        if "dual" in config:
            c = config["dual"]
            blueprints.append(generate_dual(
                input_count=c.get("input_count", c.get("param_count", 2)),
                output_count=c.get("output_count", c.get("param_count", 2)),
                wagons=c.get("wagons", 3),
                station_name=c.get("station_name", "LTN Dual"),
            ))

        if not blueprints:
            parser.error("Config file has no valid station definitions.")

        if len(blueprints) == 1:
            book_or_bp = blueprints[0]
            label = "Config Station"
        else:
            book_or_bp = build_book("LTN Stations", blueprints)
            label = "Config Stations (book)"

        bp_string = encode_blueprint(book_or_bp)
        verify_blueprint(bp_string, label)
        sections.append((label, book_or_bp, bp_string))

    # ─── --all mode: provider + receiver + dual (all parameterized) ───
    elif args.all:
        all_blueprints = [
            generate_provider(param_count=args.param_count, wagons=3, station_name="Provider (3W)"),
            generate_receiver(param_count=args.param_count, wagons=3, station_name="Receiver (3W)"),
            generate_dual(input_count=input_count, output_count=output_count, wagons=3,
                          station_name="Dual (3W)"),
        ]
        book = build_book("LTN Stations", all_blueprints)
        sections = [
            ("Provider (3W)", all_blueprints[0], encode_blueprint(all_blueprints[0])),
            ("Receiver (3W)", all_blueprints[1], encode_blueprint(all_blueprints[1])),
            ("Dual (3W)", all_blueprints[2], encode_blueprint(all_blueprints[2])),
            ("Blueprint Book (all three)", book, encode_blueprint(book)),
        ]
        for name, _, s in sections:
            verify_blueprint(s, name)

    # ─── Individual station mode ───
    else:
        if not (args.provider or args.receiver or args.dual):
            parser.error("Specify at least one of: --provider, --receiver, --dual, --all")

        if args.provider:
            bp = generate_provider(
                param_count=args.param_count, wagons=args.wagons,
                station_name=args.station_name or "LTN Provider",
            )
            s = encode_blueprint(bp); verify_blueprint(s, "Provider")
            sections.append(("Provider Station", bp, s))

        if args.receiver:
            bp = generate_receiver(
                param_count=args.param_count, wagons=args.wagons,
                station_name=args.station_name or "LTN Receiver",
            )
            s = encode_blueprint(bp); verify_blueprint(s, "Receiver")
            sections.append(("Receiver Station", bp, s))

        if args.dual:
            bp = generate_dual(
                input_count=input_count, output_count=output_count,
                wagons=args.wagons, station_name=args.station_name or "LTN Dual",
            )
            s = encode_blueprint(bp); verify_blueprint(s, "Dual")
            sections.append(("Dual-Mode Station", bp, s))

    if not sections:
        parser.error("No stations to generate.")

    generate_output(sections, args.output)


if __name__ == "__main__":
    main()
