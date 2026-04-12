#!/usr/bin/env python3
"""
Factorio 2.0 LTN Blueprint Generator

Generates importable blueprint strings for LTN (Logistic Train Network) train
stations (3-wagon only). Each station is a single-sided 3-row design with two
decider combinators per side: one for inserter filtering, one for inventory
filtering to LTN.

Required mods:
  - LTN (Logistic Train Network)
  - LTN Combinator (original, 2.0-compatible)
  - Bob's Inserters (for bob-red-inserter on the train-adjacent row)

For full design documentation see:
  ~/Obsidian/vault/projects/factorio-ltn-blueprints.md  (in-game guide)
  ~/Obsidian/vault/projects/factorio-ltn-generator.md   (script & format docs)

LTN 3-entity stop architecture (all placeable in blueprints):
  1. logistic-train-stop         — visible 2x2 stop, read_from_train enabled
  2. logistic-train-stop-input   — lamp that feeds config INTO LTN (overlaps stop NW)
  3. logistic-train-stop-output  — yellow CC holding the active delivery signal
                                   (overlaps stop SW; positive=load, negative=unload)
  Plus: ltn-combinator — holds LTN configuration, wired GREEN to the input lamp.

Station layout (3 wagons, positions relative to stop at (0,0) dir=WEST):
  y=-1.5: 18 feed/output inserters (placeholder — user wires to external belts)
  y=-0.5: 18 chests, daisy-chained RED (contents → decider #2)
  y=+0.5: 18 bob-red-inserters, daisy-chained RED via poles (driven by decider #1)
  y=+2.0: 13 straight rails + 2 curved rails at ends
  First wagon chests at x=+7.5..+12.5; 7-tile wagon pitch.

Two-decider design (per side):
  Decider #1 — drives bob-red inserter filter:
    Provider: (output_CC RED + stop cargo ×-1) ∩ allowlist → remaining items
    Receiver: (output_CC ×-1 through arith) ∩ allowlist → allowed unload items
    Output RED → first pole RED → bob-red chain
  Decider #2 — filters chest contents fed to LTN lamp (GREEN):
    chest chain (RED) ∩ allowlist (GREEN) → OUT_GREEN → lamp
    So LTN only sees inventory that matches the allowlist (ignores contamination).

Dual stations stack provider (north) + receiver (south) around the rails with
two independent sub-circuits sharing the output yellow CC and LTN lamp.

Usage:
  python factorio-blueprint-generator.py --provider --allowlist iron-plate copper-plate
  python factorio-blueprint-generator.py --receiver --allowlist iron-ore copper-ore
  python factorio-blueprint-generator.py --dual --provide iron-plate --request copper-ore
  python factorio-blueprint-generator.py --all --output stations.md
  python factorio-blueprint-generator.py --config my-stations.json --output out.md
"""

import argparse
import base64
import json
import sys
import zlib
from dataclasses import dataclass
from typing import Optional


# ─── Factorio 2.0 constants ──────────────────────────────────────────────────

# 16-direction system (N=0, E=4, S=8, W=12)
NORTH = 0
EAST = 4
SOUTH = 8
WEST = 12

# Wire connector IDs (defines.wire_connector_id)
RED = 1         # circuit_red / combinator_input_red
GREEN = 2       # circuit_green / combinator_input_green
OUT_RED = 3     # combinator_output_red
OUT_GREEN = 4   # combinator_output_green

# Blueprint version: 2.0.10.0
FACTORIO_VERSION = 562949954076672


# ─── Signal helpers ───────────────────────────────────────────────────────────

def item_signal(name: str) -> dict:
    return {"type": "item", "name": name}


def virtual_signal(name: str) -> dict:
    return {"type": "virtual", "name": name}


# ─── Blueprint data structures ────────────────────────────────────────────────

@dataclass
class Entity:
    entity_number: int
    name: str
    position: dict
    direction: int = 0
    control_behavior: Optional[dict] = None
    station: Optional[str] = None
    tags: Optional[dict] = None
    always_on: Optional[bool] = None
    pickup_position: Optional[list] = None
    drop_position: Optional[list] = None

    def to_dict(self) -> dict:
        d = {
            "entity_number": self.entity_number,
            "name": self.name,
            "position": self.position,
        }
        if self.direction != 0:
            d["direction"] = self.direction
        if self.control_behavior:
            d["control_behavior"] = self.control_behavior
        if self.station:
            d["station"] = self.station
        if self.tags:
            d["tags"] = self.tags
        if self.always_on is not None:
            d["always_on"] = self.always_on
        if self.pickup_position is not None:
            d["pickup_position"] = self.pickup_position
        if self.drop_position is not None:
            d["drop_position"] = self.drop_position
        return d


class IDCounter:
    def __init__(self, start=1):
        self._n = start

    def next(self) -> int:
        n = self._n
        self._n += 1
        return n


# ─── Wire helpers ─────────────────────────────────────────────────────────────

def add_wire(wires: list, a_id: int, a_conn: int, b_id: int, b_conn: int):
    """Add a wire entry. Lower entity_number goes first (Factorio convention)."""
    if a_id > b_id:
        a_id, a_conn, b_id, b_conn = b_id, b_conn, a_id, a_conn
    wires.append([a_id, a_conn, b_id, b_conn])


# ─── Encoding / decoding ─────────────────────────────────────────────────────

def encode_blueprint(bp_dict: dict) -> str:
    """Encode blueprint dict → Factorio-importable string ('0' + base64(zlib(json)))."""
    json_bytes = json.dumps(bp_dict, separators=(",", ":")).encode("utf-8")
    return "0" + base64.b64encode(zlib.compress(json_bytes, level=9)).decode("ascii")


def decode_blueprint(bp_string: str) -> dict:
    if not bp_string.startswith("0"):
        raise ValueError("Blueprint string must start with '0' version byte")
    return json.loads(zlib.decompress(base64.b64decode(bp_string[1:])))


def verify_blueprint(bp_string: str, label: str) -> bool:
    try:
        data = decode_blueprint(bp_string)
        if "blueprint_book" in data:
            bps = data["blueprint_book"].get("blueprints", [])
            print(f"  OK: {label} — book with {len(bps)} blueprints", file=sys.stderr)
        elif "blueprint" in data:
            ents = len(data["blueprint"].get("entities", []))
            wires = len(data["blueprint"].get("wires", []))
            print(f"  OK: {label} — {ents} entities, {wires} wires", file=sys.stderr)
        return True
    except Exception as e:
        print(f"  FAIL: {label} — {e}", file=sys.stderr)
        return False


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
# Train approaches from the east and stops at x=0. Rails at y=+2 (wagon occupies y=+1..+3).
# Provider/receiver standalone use only north rows (y=-1.5, -0.5, +0.5).
# Dual adds mirrored receiver rows on south (y=+3.5, +4.5, +5.5).

Y_FEED_INS = -1.5         # Feed/output inserter row (user wires to external belts)
Y_CHEST_N = -0.5          # Chest row (same y as ltn-combinator and input lamp)
Y_LOAD_INS = 0.5          # Bob-red inserter row (adjacent to rail, reaches train)
Y_RAILS = 2.0             # Straight rail row

# Dual-only south-side row positions (mirror of north across rails)
Y_UNLOAD_INS = 3.5        # South bob-red inserters (unload)
Y_CHEST_S = 4.5      # South chest row
Y_OUTPUT_INS = 5.5        # South output inserter row

WAGON_PITCH = 7           # 6-tile wagon + 1-tile gap (for power pole)
WAGON_START_X = 7         # First wagon first tile at x=7 (first chest at x=7.5)
INSERTERS_PER_WAGON = 6

# ─── North-side combinator positions (used for provider, receiver, dual north) ─
# arith sits WEST of decider #1 so arith OUT_RED flows straight into decider #1 RED.
# Decider #2 sits above on the feed-inserter row, dir=WEST so its OUT_GREEN face
# points toward the lamp on the west.
X_ARITH_N = 3             # arith at (+3, -0.5) dir=EAST
Y_ARITH_N = -0.5
X_DECIDER1_N = 5          # decider #1 at (+5, -0.5) dir=EAST
Y_DECIDER1_N = -0.5
X_DECIDER2_N = 4          # decider #2 at (+4, -1.5) dir=WEST
Y_DECIDER2_N = -1.5
X_CC_N = 3.5              # allowlist CC at (+3.5, +0.5)
Y_CC_N = 0.5

# ─── South-side combinator positions (dual receiver side — mirror of north) ──
X_ARITH_S = 3
Y_ARITH_S = 4.5
X_DECIDER1_S = 5
Y_DECIDER1_S = 4.5
X_DECIDER2_S = 4
Y_DECIDER2_S = 5.5
X_CC_S = 3.5
Y_CC_S = 3.5

def _pole_x_positions(wagons):
    """Power pole x positions: one before each wagon + one after the last.
    For wagons starting at x=+7.5 (WAGON_START_X=7) with 7-tile pitch:
    W=3 → poles at x=+6.5, +13.5, +20.5, +27.5.
    """
    return [(WAGON_START_X - 0.5) + w * WAGON_PITCH for w in range(wagons + 1)]


# ─── Shared entity builders ──────────────────────────────────────────────────

def build_allowlist_cc(eid: int, position: dict, items: list[str]) -> Entity:
    """Constant combinator with allowlist items (each = 1)."""
    filters = [
        {"signal": item_signal(name), "count": 1, "index": i + 1}
        for i, name in enumerate(items)
    ]
    return Entity(
        entity_number=eid,
        name="constant-combinator",
        position=position,
        control_behavior={"filters": filters},
    )


def build_provider_decider(eid: int, position: dict, direction: int = EAST) -> Entity:
    """Decider for provider stations: per-network red Each > 0 AND green Each > 0.

    Uses Factorio 2.0 per-network conditions to check BOTH:
      - Red wire: remaining = delivery − train_contents > 0  (still items to load)
      - Green wire: allowlist signal > 0  (item is permitted)
    Output copies count from red wire only (the remaining amount).
    When remaining hits 0, signal vanishes and inserter filter clears.

    Default direction=EAST: 2-tile-wide horizontal layout (position.y at INT+0.5).
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
                        "constant": 0,
                        "comparator": ">",
                        "first_signal_networks": {"red": True, "green": False},
                    },
                    {
                        "first_signal": virtual_signal("signal-each"),
                        "constant": 0,
                        "comparator": ">",
                        "first_signal_networks": {"red": False, "green": True},
                    },
                ],
                "outputs": [{
                    "signal": virtual_signal("signal-each"),
                    "copy_count_from_input": True,
                    "networks": {"red": True, "green": False},
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


def build_blueprint(label: str, entities: list["Entity"], wires: list,
                    description: str = "") -> dict:
    bp = {
        "blueprint": {
            "item": "blueprint",
            "label": label,
            "entities": [e.to_dict() for e in entities],
            "version": FACTORIO_VERSION,
        }
    }
    if wires:
        bp["blueprint"]["wires"] = wires
    if description:
        bp["blueprint"]["description"] = description
    return bp


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
        tags={"ltnc": dict(ltn_tags)},
    )
    return eid, ent


def build_power_pole(ids, x, y):
    """Medium electric pole at (x, y)."""
    eid = ids.next()
    return eid, Entity(
        entity_number=eid,
        name="medium-electric-pole",
        position={"x": x, "y": y},
    )


def build_rail(ids, x, y=Y_RAILS):
    """Straight rail at (x, y) direction=EAST."""
    eid = ids.next()
    return eid, Entity(
        entity_number=eid,
        name="straight-rail",
        position={"x": x, "y": y},
        direction=EAST,
    )


def build_curved_rail(ids, x, y, direction):
    """Curved rail (curved-rail-a) at (x, y) with given direction.
    West end of station: x=-3, dir=12 (WEST).
    East end: x=+27 (for 3W), dir=6.
    """
    eid = ids.next()
    return eid, Entity(
        entity_number=eid,
        name="curved-rail-a",
        position={"x": x, "y": y},
        direction=direction,
    )


# ─── Inserter row builders ───────────────────────────────────────────────────

def build_book(label: str, blueprints: list[dict]) -> dict:
    """Wrap blueprint dicts into a blueprint book."""
    entries = []
    for i, bp in enumerate(blueprints):
        entry = {"index": i}
        if "blueprint" in bp:
            entry["blueprint"] = bp["blueprint"]
        elif "blueprint_book" in bp:
            entry["blueprint_book"] = bp["blueprint_book"]
        entries.append(entry)
    return {
        "blueprint_book": {
            "item": "blueprint-book",
            "label": label,
            "blueprints": entries,
            "active_index": 0,
            "version": FACTORIO_VERSION,
        }
    }


# ─── Station generators ──────────────────────────────────────────────────────


def _build_ltn_head(ids, station_name, ltn_tags, entities, wires):
    """Build the LTN stop group + ltn-combinator with config wire.
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


def generate_provider(
    allowlist: list[str],
    wagons: int = 3,
    station_name: str = "LTN Provider",
) -> dict:
    """Provider station (3-row single-sided design).

    Layout per wagon (6 × 3 wagons = 18 per row):
      y=-1.5: feed inserters — user wires to external source belts
      y=-0.5: chests — daisy-chained RED, contents → decider #2 (provide filter)
      y=+0.5: bob-red-inserters — daisy-chained RED via poles, driven by decider #1

    Sub-circuits (see _build_station_side for wiring details):
      Decider #1 (overload prevention): output_CC + stop cargo ×−1 → filter signal
      Decider #2 (provide filter): chest contents ∩ allowlist → lamp GREEN
    """
    ids = IDCounter()
    entities: list[Entity] = []
    wires: list = []

    stop_id, input_lamp_id, output_cc_id, _ = _build_ltn_head(
        ids, station_name, {"provider": True}, entities, wires
    )

    _, _, pole_ids = _build_station_side(
        ids, entities, wires, wagons,
        y_top_ins=Y_FEED_INS, y_chest=Y_CHEST_N, y_bob_ins=Y_LOAD_INS,
        x_arith=X_ARITH_N, y_arith=Y_CHEST_N,
        x_decider1=X_DECIDER1_N, y_decider1=Y_DECIDER1_N,
        x_decider2=X_DECIDER2_N, y_decider2=Y_DECIDER2_N,
        x_cc=X_CC_N, y_cc=Y_CC_N,
        arith_input_id=stop_id,              # provider: stop cargo feeds arith
        extra_decider1_red_input=output_cc_id,  # + output_CC for overload prev
        input_lamp_id=input_lamp_id,
        allowlist=allowlist,
        side_label="provider",
    )

    # Combi pole near combinators: power + lamp R/G wires
    combi_pole_id, combi_pole_ent = build_power_pole(ids, -0.5, Y_FEED_INS)
    entities.append(combi_pole_ent)
    add_wire(wires, combi_pole_id, RED, input_lamp_id, RED)
    add_wire(wires, combi_pole_id, GREEN, input_lamp_id, GREEN)
    add_wire(wires, combi_pole_id, 5, pole_ids[0], 5)

    _add_rails_with_curves(ids, wagons, entities)

    return build_blueprint(station_name, entities, wires)


def _build_station_side(
    ids, entities, wires, wagons,
    *,
    y_top_ins,          # feed/output inserter row (y=-1.5 for north, y=+5.5 for south)
    y_chest,            # chest row
    y_bob_ins,          # bob-red inserter row (adjacent to rail)
    x_arith, y_arith,   # arith inverter position
    x_decider1, y_decider1,
    x_decider2, y_decider2,
    x_cc, y_cc,
    arith_input_id,     # what feeds arith's RED input (stop for provider, output_CC for receiver)
    extra_decider1_red_input=None,  # provider adds output_CC to decider #1 RED
    input_lamp_id,
    allowlist,
    side_label,         # "provider" or "receiver"
):
    """Build one side of a station (provider-style or receiver-style).

    Creates: arith + decider #1 (overload/request) + decider #2 (inventory filter)
             + allowlist CC + feed/output inserters + chests + bob-reds + poles.
    Wires up the circuit and returns (decider1_id, chest_ids, pole_ids, first_pole_id).
    """
    # Combinators
    arith_id = ids.next()
    entities.append(build_inverter(arith_id, {"x": x_arith, "y": y_arith}, direction=EAST))

    decider1_id = ids.next()
    entities.append(build_provider_decider(decider1_id, {"x": x_decider1, "y": y_decider1}, direction=EAST))

    decider2_id = ids.next()
    entities.append(build_provider_decider(decider2_id, {"x": x_decider2, "y": y_decider2}, direction=WEST))

    cc_id = ids.next()
    entities.append(build_allowlist_cc(cc_id, {"x": x_cc, "y": y_cc}, allowlist))

    # Wiring — decider #1 (overload prevention or request filter)
    add_wire(wires, arith_input_id, RED, arith_id, RED)
    add_wire(wires, arith_id, OUT_RED, decider1_id, RED)
    if extra_decider1_red_input is not None:
        add_wire(wires, extra_decider1_red_input, RED, decider1_id, RED)
    add_wire(wires, cc_id, GREEN, decider1_id, GREEN)

    # Wiring — decider #2 (inventory filter → LTN lamp)
    add_wire(wires, cc_id, GREEN, decider2_id, GREEN)
    add_wire(wires, decider2_id, OUT_GREEN, input_lamp_id, GREEN)

    # Top inserter row (feed or output; no circuit wires, user configures)
    top_ins_name = "inserter"
    for w in range(wagons):
        wagon_start = WAGON_START_X + w * WAGON_PITCH
        for i in range(INSERTERS_PER_WAGON):
            x = wagon_start + i + 0.5
            iid = ids.next()
            entities.append(Entity(iid, top_ins_name, {"x": x, "y": y_top_ins}))

    # Chest row — daisy-chained RED, first chest → decider #2 RED
    chest_ids = []
    for w in range(wagons):
        wagon_start = WAGON_START_X + w * WAGON_PITCH
        for i in range(INSERTERS_PER_WAGON):
            x = wagon_start + i + 0.5
            cid = ids.next()
            entities.append(Entity(cid, "steel-chest", {"x": x, "y": y_chest}))
            chest_ids.append(cid)
    for i in range(len(chest_ids) - 1):
        add_wire(wires, chest_ids[i], RED, chest_ids[i + 1], RED)
    add_wire(wires, decider2_id, RED, chest_ids[0], RED)

    # Bob-red row — daisy-chained RED via poles, driven by decider #1 OUT_RED
    pole_ids = []
    for x in _pole_x_positions(wagons):
        pid, pent = build_power_pole(ids, x, y_bob_ins)
        entities.append(pent)
        pole_ids.append(pid)

    ins_groups = []
    for w in range(wagons):
        wagon_start = WAGON_START_X + w * WAGON_PITCH
        wagon_ins = []
        for i in range(INSERTERS_PER_WAGON):
            x = wagon_start + i + 0.5
            iid = ids.next()
            entities.append(Entity(
                entity_number=iid,
                name="bob-red-inserter",
                position={"x": x, "y": y_bob_ins},
                control_behavior={
                    "circuit_mode_of_operation": 1,
                    "circuit_set_stack_size": False,
                },
            ))
            wagon_ins.append(iid)
        ins_groups.append(wagon_ins)

    for w, ins_group in enumerate(ins_groups):
        if not ins_group:
            continue
        add_wire(wires, pole_ids[w], RED, ins_group[0], RED)
        for i in range(len(ins_group) - 1):
            add_wire(wires, ins_group[i], RED, ins_group[i + 1], RED)
        add_wire(wires, ins_group[-1], RED, pole_ids[w + 1], RED)

    add_wire(wires, decider1_id, OUT_RED, pole_ids[0], RED)

    # Copper wires along the pole row
    for i in range(len(pole_ids) - 1):
        add_wire(wires, pole_ids[i], 5, pole_ids[i + 1], 5)

    return decider1_id, chest_ids, pole_ids


def _add_rails_with_curves(ids, wagons, entities):
    """Add 13+ straight rails (y=+2, 2-tile pitch) with curved rails at both ends.

    For W=3: straight rails x=0..+24 (13 total), curved at x=-3 dir=WEST and x=+27 dir=6.
    """
    straight_end_x = wagons * WAGON_PITCH + 3  # For W=3: +24
    for x in range(0, straight_end_x + 1, 2):
        _, rent = build_rail(ids, x, Y_RAILS)
        entities.append(rent)
    _, cw = build_curved_rail(ids, -3, Y_RAILS, WEST)
    entities.append(cw)
    _, ce = build_curved_rail(ids, straight_end_x + 3, Y_RAILS, 6)
    entities.append(ce)


def generate_receiver(
    allowlist: list[str],
    wagons: int = 3,
    station_name: str = "LTN Receiver",
) -> dict:
    """Receiver station (new 3-row single-sided design, mirror of provider wiring).

    Layout per wagon (6 each × 3 wagons = 18 per row):
      y=-1.5: output inserters — user wires to take items from chests to external belts
      y=-0.5: chests — daisy-chained RED, contents feed decider #2 (inventory filter)
      y=+0.5: bob-red-inserters (UNLOAD: pick train → drop chest), driven by decider #1

    Note: bob-red directions may need configuration in-game to get unload behavior.

    Two sub-circuits:
      Decider #1 (request/unload filter):
        output_CC (RED, negative requests) → arith (×-1) → decider #1 RED input (positive)
        allowlist_CC (GREEN) → decider #1 GREEN input
        decider #1 OUT_RED → pole → bob-red chain (only allowed items get unloaded)
      Decider #2 (inventory filter → LTN lamp):
        chest chain (RED) → decider #2 RED input
        allowlist_CC (GREEN) → decider #2 GREEN input
        decider #2 OUT_GREEN → lamp (tells LTN what's currently stored)
    """
    ids = IDCounter()
    entities: list[Entity] = []
    wires: list = []

    stop_id, input_lamp_id, output_cc_id, _ = _build_ltn_head(
        ids, station_name, {"requester": True}, entities, wires
    )

    _, _, pole_ids = _build_station_side(
        ids, entities, wires, wagons,
        y_top_ins=Y_FEED_INS, y_chest=Y_CHEST_N, y_bob_ins=Y_LOAD_INS,
        x_arith=X_ARITH_N, y_arith=Y_CHEST_N,
        x_decider1=X_DECIDER1_N, y_decider1=Y_DECIDER1_N,
        x_decider2=X_DECIDER2_N, y_decider2=Y_DECIDER2_N,
        x_cc=X_CC_N, y_cc=Y_CC_N,
        arith_input_id=output_cc_id,  # receiver: output_CC feeds arith (not stop)
        extra_decider1_red_input=None,  # receiver: no cargo subtraction
        input_lamp_id=input_lamp_id,
        allowlist=allowlist,
        side_label="receiver",
    )

    # Combi pole near combinators (provides power + wires lamp R/G)
    combi_pole_id, combi_pole_ent = build_power_pole(ids, -0.5, Y_FEED_INS)
    entities.append(combi_pole_ent)
    add_wire(wires, combi_pole_id, RED, input_lamp_id, RED)
    add_wire(wires, combi_pole_id, GREEN, input_lamp_id, GREEN)
    add_wire(wires, combi_pole_id, 5, pole_ids[0], 5)

    _add_rails_with_curves(ids, wagons, entities)

    return build_blueprint(station_name, entities, wires)


def generate_dual(
    provide_allowlist: list[str],
    request_allowlist: list[str],
    wagons: int = 3,
    station_name: str = "LTN Dual",
) -> dict:
    """Dual station (provider on NORTH side + receiver on SOUTH side of rails).

    Six rows stacked around the rails at y=+2:
      y=-1.5: provider feed inserters
      y=-0.5: provider chests
      y=+0.5: provider load bob-reds
      y=+2:   rails
      y=+3.5: receiver unload bob-reds
      y=+4.5: receiver chests
      y=+5.5: receiver output inserters

    Each side has its own arith/decider#1/decider#2/allowlist CC — two fully
    independent sub-circuits that share the output yellow CC and the LTN lamp
    (both decider#2s feed GREEN into the lamp so LTN sees combined inventory).
    """
    ids = IDCounter()
    entities: list[Entity] = []
    wires: list = []

    stop_id, input_lamp_id, output_cc_id, _ = _build_ltn_head(
        ids, station_name, {"provider": True, "requester": True}, entities, wires
    )

    # NORTH side (provider)
    _, _, north_pole_ids = _build_station_side(
        ids, entities, wires, wagons,
        y_top_ins=Y_FEED_INS, y_chest=Y_CHEST_N, y_bob_ins=Y_LOAD_INS,
        x_arith=X_ARITH_N, y_arith=Y_CHEST_N,
        x_decider1=X_DECIDER1_N, y_decider1=Y_DECIDER1_N,
        x_decider2=X_DECIDER2_N, y_decider2=Y_DECIDER2_N,
        x_cc=X_CC_N, y_cc=Y_CC_N,
        arith_input_id=stop_id,  # provider: stop cargo feeds arith
        extra_decider1_red_input=output_cc_id,  # + output_CC for overload prev
        input_lamp_id=input_lamp_id,
        allowlist=provide_allowlist,
        side_label="provider",
    )

    # SOUTH side (receiver)
    _, _, south_pole_ids = _build_station_side(
        ids, entities, wires, wagons,
        y_top_ins=Y_OUTPUT_INS, y_chest=Y_CHEST_S, y_bob_ins=Y_UNLOAD_INS,
        x_arith=X_ARITH_S, y_arith=Y_DECIDER1_S,
        x_decider1=X_DECIDER1_S, y_decider1=Y_DECIDER1_S,
        x_decider2=X_DECIDER2_S, y_decider2=Y_DECIDER2_S,
        x_cc=X_CC_S, y_cc=Y_CC_S,
        arith_input_id=output_cc_id,  # receiver: output_CC feeds arith
        extra_decider1_red_input=None,
        input_lamp_id=input_lamp_id,
        allowlist=request_allowlist,
        side_label="receiver",
    )

    # Power poles near combinators (one north for provider, one south for receiver)
    north_combi_pole_id, north_combi_pole_ent = build_power_pole(ids, -0.5, Y_FEED_INS)
    entities.append(north_combi_pole_ent)
    add_wire(wires, north_combi_pole_id, RED, input_lamp_id, RED)
    add_wire(wires, north_combi_pole_id, GREEN, input_lamp_id, GREEN)
    add_wire(wires, north_combi_pole_id, 5, north_pole_ids[0], 5)

    south_combi_pole_id, south_combi_pole_ent = build_power_pole(ids, -0.5, Y_OUTPUT_INS)
    entities.append(south_combi_pole_ent)
    add_wire(wires, south_combi_pole_id, 5, south_pole_ids[0], 5)

    # Connect the two pole networks via copper (same-index poles across rows)
    for i in range(min(len(north_pole_ids), len(south_pole_ids))):
        add_wire(wires, north_pole_ids[i], 5, south_pole_ids[i], 5)

    _add_rails_with_curves(ids, wagons, entities)

    return build_blueprint(station_name, entities, wires)


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
        "Generated by `factorio-blueprint-generator.py` for Factorio 2.0 + LTN.",
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
        description="Generate Factorio 2.0 LTN station blueprints with allowlist filtering.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --provider --allowlist iron-plate copper-plate
  %(prog)s --receiver --allowlist iron-ore copper-ore --wagons 2
  %(prog)s --dual --provide iron-plate --request copper-ore
  %(prog)s --all --output stations.md

  --all generates a blueprint book with provider/receiver/dual for 1, 2, and 3 wagons.
  Layout: north roomy (chest+inserter rows) + south compact (interleaved row,
  requires Bob's Inserters for 90-degree bob-red-inserter).
        """,
    )

    mode = parser.add_argument_group("Station type")
    mode.add_argument("--provider", action="store_true", help="Generate provider station")
    mode.add_argument("--receiver", action="store_true", help="Generate receiver station")
    mode.add_argument("--dual", action="store_true", help="Generate dual-mode station")
    mode.add_argument("--all", action="store_true",
                      help="Generate book with provider/receiver/dual, 3 wagons each")

    items = parser.add_argument_group("Item lists")
    items.add_argument("--allowlist", nargs="+", metavar="ITEM",
                       help="Items for provider/receiver (e.g., iron-plate copper-plate)")
    items.add_argument("--provide", nargs="+", metavar="ITEM",
                       help="Items for dual-mode provider allowlist")
    items.add_argument("--request", nargs="+", metavar="ITEM",
                       help="Items for dual-mode receiver allowlist")

    opts = parser.add_argument_group("Options")
    opts.add_argument("--wagons", type=int, default=3, choices=(3,),
                      help="Cargo wagons per train: only 3 supported.")
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

    default_allowlist = ["iron-plate", "copper-plate"]
    sections: list[tuple[str, dict, str]] = []

    # ─── Config file mode ───
    if args.config:
        with open(args.config) as f:
            config = json.load(f)

        blueprints = []

        if "provider" in config:
            c = config["provider"]
            bp = generate_provider(
                allowlist=c.get("allowlist", default_allowlist),
                wagons=c.get("wagons", 2),
                station_name=c.get("station_name", "LTN Provider"),
            )
            blueprints.append(bp)

        if "receiver" in config:
            c = config["receiver"]
            bp = generate_receiver(
                allowlist=c.get("allowlist", default_allowlist),
                wagons=c.get("wagons", 2),
                station_name=c.get("station_name", "LTN Receiver"),
            )
            blueprints.append(bp)

        if "dual" in config:
            c = config["dual"]
            bp = generate_dual(
                provide_allowlist=c.get("provide_allowlist", default_allowlist),
                request_allowlist=c.get("request_allowlist", default_allowlist),
                wagons=c.get("wagons", 2),
                station_name=c.get("station_name", "LTN Dual"),
            )
            blueprints.append(bp)

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

    # ─── --all mode: book with 3-wagon variants only ───
    elif args.all:
        allowlist = args.allowlist or default_allowlist
        provide = args.provide or allowlist
        request = args.request or allowlist

        all_blueprints = [
            generate_provider(allowlist=allowlist, wagons=3, station_name="Provider (3W)"),
            generate_receiver(allowlist=allowlist, wagons=3, station_name="Receiver (3W)"),
            generate_dual(provide_allowlist=provide, request_allowlist=request,
                          wagons=3, station_name="Dual (3W)"),
        ]

        book = build_book("LTN Stations", all_blueprints)
        bp_string = encode_blueprint(book)
        verify_blueprint(bp_string, "LTN Stations Book")
        sections.append(("LTN Stations (Blueprint Book)", book, bp_string))

    # ─── Individual station mode ───
    else:
        if not (args.provider or args.receiver or args.dual):
            parser.error("Specify at least one of: --provider, --receiver, --dual, --all")

        if args.provider:
            allowlist = args.allowlist or default_allowlist
            name = args.station_name or "LTN Provider"
            bp = generate_provider(
                allowlist=allowlist,
                wagons=args.wagons,
                station_name=name,
            )
            bp_string = encode_blueprint(bp)
            verify_blueprint(bp_string, "Provider")
            sections.append(("Provider Station", bp, bp_string))

        if args.receiver:
            allowlist = args.allowlist or default_allowlist
            name = args.station_name or "LTN Receiver"
            bp = generate_receiver(
                allowlist=allowlist,
                wagons=args.wagons,
                station_name=name,
            )
            bp_string = encode_blueprint(bp)
            verify_blueprint(bp_string, "Receiver")
            sections.append(("Receiver Station", bp, bp_string))

        if args.dual:
            provide = args.provide or args.allowlist or default_allowlist
            request = args.request or args.allowlist or default_allowlist
            name = args.station_name or "LTN Dual"
            bp = generate_dual(
                provide_allowlist=provide,
                request_allowlist=request,
                wagons=args.wagons,
                station_name=name,
            )
            bp_string = encode_blueprint(bp)
            verify_blueprint(bp_string, "Dual")
            sections.append(("Dual-Mode Station", bp, bp_string))

    if not sections:
        parser.error("No stations to generate.")

    generate_output(sections, args.output)


if __name__ == "__main__":
    main()
