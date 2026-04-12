#!/usr/bin/env python3
"""
Factorio LTN Blueprint Generator

Generates importable blueprint strings for LTN train stations with allowlist filtering.
Supports 3 station types: provider, receiver, and dual-mode.

Station alignment:
  - Train approaches RIGHT to LEFT
  - Unload inserters on TOP (train → chests)
  - Load inserters on BOTTOM (chests → train)
  - Provider-only can optionally load from TOP

Usage:
  python factorio-blueprint-generator.py --provider --allowlist iron-plate copper-plate
  python factorio-blueprint-generator.py --receiver --allowlist iron-ore copper-ore
  python factorio-blueprint-generator.py --dual --provide iron-plate --request copper-ore
  python factorio-blueprint-generator.py --all --output stations.md
  python factorio-blueprint-generator.py --config my-stations.json --output out.md

Config file format (JSON):
  {
    "provider": {
      "allowlist": ["iron-plate", "copper-plate"],
      "wagons": 2,
      "inserters_per_wagon": 6,
      "load_from_top": false,
      "station_name": "Provider Iron+Copper"
    },
    "receiver": {
      "allowlist": ["iron-ore", "copper-ore"],
      "wagons": 2,
      "inserters_per_wagon": 6,
      "station_name": "Receiver Ores"
    },
    "dual": {
      "provide_allowlist": ["iron-plate"],
      "request_allowlist": ["copper-ore"],
      "wagons": 2,
      "inserters_per_wagon": 6,
      "station_name": "Dual Iron/Copper"
    }
  }
"""

import argparse
import base64
import json
import sys
import zlib
from dataclasses import dataclass, field
from typing import Optional


# ─── Factorio item signal mapping ───────────────────────────────────────────
# Factorio 2.0 uses "item" type for most signals
def item_signal(name: str) -> dict:
    """Create a Factorio signal reference for an item."""
    return {"type": "item", "name": name}


# ─── Blueprint data structures ──────────────────────────────────────────────

@dataclass
class Entity:
    """A single entity in the blueprint."""
    entity_number: int
    name: str
    position: dict  # {"x": float, "y": float}
    direction: int = 0  # 0=north, 2=east, 4=south, 6=west (Factorio directions * 2 in 2.0)
    control_behavior: Optional[dict] = None
    connections: Optional[dict] = None
    station: Optional[str] = None  # for train-stop

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
        if self.connections:
            d["connections"] = self.connections
        if self.station:
            d["station"] = self.station
        return d


def encode_blueprint(blueprint_dict: dict) -> str:
    """Encode a blueprint dict to a Factorio-importable string.

    Format: '0' + base64(zlib_deflate(json))
    The leading '0' is the version byte used by Factorio.
    """
    json_bytes = json.dumps(blueprint_dict, separators=(",", ":")).encode("utf-8")
    compressed = zlib.compress(json_bytes, level=9)
    b64 = base64.b64encode(compressed).decode("ascii")
    return "0" + b64


def decode_blueprint(bp_string: str) -> dict:
    """Decode a Factorio blueprint string back to dict for verification."""
    if not bp_string.startswith("0"):
        raise ValueError("Blueprint string must start with '0' version byte")
    b64_data = bp_string[1:]
    compressed = base64.b64decode(b64_data)
    json_bytes = zlib.decompress(compressed)
    return json.loads(json_bytes)


def verify_blueprint(bp_string: str, label: str) -> bool:
    """Decode a blueprint string and verify it parses correctly."""
    try:
        data = decode_blueprint(bp_string)
        if "blueprint" not in data:
            print(f"  WARN: {label} — decoded but missing 'blueprint' key", file=sys.stderr)
            return False
        entities = data["blueprint"].get("entities", [])
        print(f"  OK: {label} — {len(entities)} entities, decodes cleanly", file=sys.stderr)
        return True
    except Exception as e:
        print(f"  FAIL: {label} — {e}", file=sys.stderr)
        return False


# ─── Entity ID counter ──────────────────────────────────────────────────────

class IDCounter:
    def __init__(self, start=1):
        self._n = start
    def next(self) -> int:
        n = self._n
        self._n += 1
        return n


# ─── Wire connection helpers ────────────────────────────────────────────────
# Factorio 2.0 blueprint wire format:
#   "wires": [[from_entity, from_connector, to_entity, to_connector, color], ...]
# connector: 1 = input (left), 2 = output (right) for combinators; 1 for other entities
# color: not used in the wires array; instead wires are in "connections" on each entity
#
# Actually, Factorio 2.0 uses a simpler format for blueprint wires.
# The entity "connections" field maps circuit_id -> color -> [{entity_id, circuit_id}]
#
# circuit_id: 1 = default / input side, 2 = output side (for combinators)

def add_wire(entities: dict, from_id: int, from_circuit: int,
             to_id: int, to_circuit: int, color: str):
    """Add a wire connection between two entities.

    entities: dict mapping entity_number -> Entity object
    color: "red" or "green"
    circuit_id: 1 = input/default, 2 = output (combinators)
    """
    for (eid, cid, other_eid, other_cid) in [
        (from_id, from_circuit, to_id, to_circuit),
        (to_id, to_circuit, from_id, from_circuit),
    ]:
        ent = entities[eid]
        if ent.connections is None:
            ent.connections = {}
        cid_str = str(cid)
        if cid_str not in ent.connections:
            ent.connections[cid_str] = {}
        if color not in ent.connections[cid_str]:
            ent.connections[cid_str][color] = []
        # Avoid duplicate connections
        conn_entry = {"entity_id": other_eid, "circuit_id": other_cid}
        if conn_entry not in ent.connections[cid_str][color]:
            ent.connections[cid_str][color].append(conn_entry)


# ─── Blueprint generators ──────────────────────────────────────────────────

def generate_provider_blueprint(
    allowlist: list[str],
    wagons: int = 2,
    inserters_per_wagon: int = 6,
    load_from_top: bool = False,
    station_name: str = "LTN Provider",
) -> tuple[dict, str]:
    """Generate a provider station blueprint.

    Returns (blueprint_dict, annotation_json_str).
    """
    ids = IDCounter()
    ent_map: dict[int, Entity] = {}

    # ─── Train stop ───
    stop_id = ids.next()
    stop = Entity(
        entity_number=stop_id,
        name="train-stop",
        position={"x": 0, "y": 0},
        direction=6,  # west — train approaches from east (right to left)
        station=station_name,
    )
    ent_map[stop_id] = stop

    # ─── LTN Combinator ───
    ltn_id = ids.next()
    # LTN combinator placed near station
    # NOTE: The actual LTN combinator entity name depends on mod version.
    # "ltn-combinator" for LTN Combinator Modernized
    ltn = Entity(
        entity_number=ltn_id,
        name="ltn-combinator",
        position={"x": 2, "y": 2},
    )
    ent_map[ltn_id] = ltn

    # ─── Constant Combinator (Allowlist) ───
    allowlist_id = ids.next()
    # Build the filter signals: each allowed item = 1
    filters = []
    for i, item_name in enumerate(allowlist):
        filters.append({
            "signal": item_signal(item_name),
            "count": 1,
            "index": i + 1,
        })

    allowlist_cb = Entity(
        entity_number=allowlist_id,
        name="constant-combinator",
        position={"x": 4, "y": 2},
        control_behavior={
            "filters": filters,
            # Comment: "Allowlist — each item set to 1. Only these items will be
            # loaded onto trains. Edit this combinator to change the allowlist."
        },
    )
    ent_map[allowlist_id] = allowlist_cb

    # ─── Decider Combinator (Filter) ───
    decider_id = ids.next()
    decider = Entity(
        entity_number=decider_id,
        name="decider-combinator",
        position={"x": 6, "y": 2},
        control_behavior={
            "decider_conditions": {
                "conditions": [
                    {
                        "first_signal": {"type": "virtual", "name": "signal-each"},
                        "constant": 0,
                        "comparator": ">",
                        # Check green wire (allowlist) > 0
                    }
                ],
                "outputs": [
                    {
                        "signal": {"type": "virtual", "name": "signal-each"},
                        "copy_count_from_input": True,
                    }
                ],
            },
            # Comment: "Filter — only passes signals where the allowlist has a
            # positive value. Output goes to load inserters."
        },
    )
    ent_map[decider_id] = decider

    # ─── Wiring: LTN → Decider (red), Allowlist → Decider (green) ───
    # LTN output → Decider input (red wire)
    add_wire(ent_map, ltn_id, 1, decider_id, 1, "red")
    # Allowlist → Decider input (green wire)
    add_wire(ent_map, allowlist_id, 1, decider_id, 1, "green")

    # ─── Chests and Inserters per wagon ───
    inserter_ids = []
    for w in range(wagons):
        wagon_x_base = -2 + (w * 7 * -1)  # wagons extend to the right (east)
        # Actually, train goes right-to-left, so wagons are to the right of the stop
        wagon_x_base = (w + 1) * -7  # each wagon is 7 tiles wide

        for i in range(inserters_per_wagon):
            x = wagon_x_base - i
            # Load inserters: bottom side by default, top side if load_from_top
            if load_from_top:
                ins_y = -1  # top side of track
                chest_y = -2
                ins_direction = 4  # south — grab from chest above, place into train
            else:
                ins_y = 1  # bottom side of track
                chest_y = 2
                ins_direction = 0  # north — grab from chest below, place into train

            # Chest
            chest_id = ids.next()
            chest = Entity(
                entity_number=chest_id,
                name="steel-chest",
                position={"x": x, "y": chest_y},
            )
            ent_map[chest_id] = chest

            # Inserter (stack filter inserter for throughput)
            ins_id = ids.next()
            inserter = Entity(
                entity_number=ins_id,
                name="bulk-inserter",
                position={"x": x, "y": ins_y},
                direction=ins_direction,
                control_behavior={
                    "circuit_mode_of_operation": 1,  # Set filters
                    # Comment: "Set filters mode — inserter only grabs items whose
                    # signal name appears on the connected green wire."
                },
            )
            ent_map[ins_id] = inserter
            inserter_ids.append(ins_id)

    # ─── Wire: Decider output → all inserters (green wire) ───
    for ins_id in inserter_ids:
        add_wire(ent_map, decider_id, 2, ins_id, 1, "green")

    # ─── Build blueprint ───
    entities_list = [e.to_dict() for e in ent_map.values()]
    bp = {
        "blueprint": {
            "item": "blueprint",
            "label": station_name,
            "entities": entities_list,
            "version": 562949954076672,  # Factorio 2.0
        }
    }

    # Build annotated JSON
    annotated = json.dumps(bp, indent=2)

    return bp, annotated


def generate_receiver_blueprint(
    allowlist: list[str],
    wagons: int = 2,
    inserters_per_wagon: int = 6,
    station_name: str = "LTN Receiver",
) -> tuple[dict, str]:
    """Generate a receiver station blueprint.

    Includes an arithmetic combinator to invert negative request signals.
    """
    ids = IDCounter()
    ent_map: dict[int, Entity] = {}

    # ─── Train stop ───
    stop_id = ids.next()
    stop = Entity(
        entity_number=stop_id,
        name="train-stop",
        position={"x": 0, "y": 0},
        direction=6,
        station=station_name,
    )
    ent_map[stop_id] = stop

    # ─── LTN Combinator ───
    ltn_id = ids.next()
    ltn = Entity(
        entity_number=ltn_id,
        name="ltn-combinator",
        position={"x": 2, "y": 2},
    )
    ent_map[ltn_id] = ltn

    # ─── Arithmetic Combinator (Inverter: Each * -1) ───
    arith_id = ids.next()
    arith = Entity(
        entity_number=arith_id,
        name="arithmetic-combinator",
        position={"x": 4, "y": 2},
        control_behavior={
            "arithmetic_conditions": {
                "first_signal": {"type": "virtual", "name": "signal-each"},
                "second_constant": -1,
                "operation": "*",
                "output_signal": {"type": "virtual", "name": "signal-each"},
            },
            # Comment: "Inverter — flips negative LTN request signals to positive
            # so inserter 'Set filters' mode can use them."
        },
    )
    ent_map[arith_id] = arith

    # ─── Constant Combinator (Allowlist) ───
    allowlist_id = ids.next()
    filters = []
    for i, item_name in enumerate(allowlist):
        filters.append({
            "signal": item_signal(item_name),
            "count": 1,
            "index": i + 1,
        })
    allowlist_cb = Entity(
        entity_number=allowlist_id,
        name="constant-combinator",
        position={"x": 6, "y": 2},
        control_behavior={
            "filters": filters,
        },
    )
    ent_map[allowlist_id] = allowlist_cb

    # ─── Decider Combinator (Filter) ───
    decider_id = ids.next()
    decider = Entity(
        entity_number=decider_id,
        name="decider-combinator",
        position={"x": 8, "y": 2},
        control_behavior={
            "decider_conditions": {
                "conditions": [
                    {
                        "first_signal": {"type": "virtual", "name": "signal-each"},
                        "constant": 0,
                        "comparator": ">",
                    }
                ],
                "outputs": [
                    {
                        "signal": {"type": "virtual", "name": "signal-each"},
                        "copy_count_from_input": True,
                    }
                ],
            },
        },
    )
    ent_map[decider_id] = decider

    # ─── Wiring ───
    # LTN → Arithmetic (red)
    add_wire(ent_map, ltn_id, 1, arith_id, 1, "red")
    # Arithmetic output → Decider input (red)
    add_wire(ent_map, arith_id, 2, decider_id, 1, "red")
    # Allowlist → Decider input (green)
    add_wire(ent_map, allowlist_id, 1, decider_id, 1, "green")

    # ─── Chests and Unload Inserters (top side) ───
    inserter_ids = []
    for w in range(wagons):
        wagon_x_base = (w + 1) * -7

        for i in range(inserters_per_wagon):
            x = wagon_x_base - i

            # Chest on top
            chest_id = ids.next()
            chest = Entity(
                entity_number=chest_id,
                name="steel-chest",
                position={"x": x, "y": -2},
            )
            ent_map[chest_id] = chest

            # Unload inserter (top side, grabs from train, places into chest)
            ins_id = ids.next()
            inserter = Entity(
                entity_number=ins_id,
                name="bulk-inserter",
                position={"x": x, "y": -1},
                direction=0,  # north — facing up, grabs from train (south), places in chest (north)
                control_behavior={
                    "circuit_mode_of_operation": 1,  # Set filters
                },
            )
            ent_map[ins_id] = inserter
            inserter_ids.append(ins_id)

    # ─── Wire: Decider output → all inserters (green) ───
    for ins_id in inserter_ids:
        add_wire(ent_map, decider_id, 2, ins_id, 1, "green")

    entities_list = [e.to_dict() for e in ent_map.values()]
    bp = {
        "blueprint": {
            "item": "blueprint",
            "label": station_name,
            "entities": entities_list,
            "version": 562949954076672,
        }
    }
    annotated = json.dumps(bp, indent=2)
    return bp, annotated


def generate_dual_blueprint(
    provide_allowlist: list[str],
    request_allowlist: list[str],
    wagons: int = 2,
    inserters_per_wagon: int = 6,
    station_name: str = "LTN Dual",
) -> tuple[dict, str]:
    """Generate a dual-mode station blueprint (provider + receiver).

    Two separate filtering paths:
    - Provider path: LTN → Decider #1 (with provider allowlist) → load inserters (bottom)
    - Receiver path: LTN → Arithmetic → Decider #2 (with receiver allowlist) → unload inserters (top)
    """
    ids = IDCounter()
    ent_map: dict[int, Entity] = {}

    # ─── Train stop ───
    stop_id = ids.next()
    stop = Entity(
        entity_number=stop_id,
        name="train-stop",
        position={"x": 0, "y": 0},
        direction=6,
        station=station_name,
    )
    ent_map[stop_id] = stop

    # ─── LTN Combinator ───
    ltn_id = ids.next()
    ltn = Entity(
        entity_number=ltn_id,
        name="ltn-combinator",
        position={"x": 2, "y": 3},
    )
    ent_map[ltn_id] = ltn

    # ═══ PROVIDER PATH ═══

    # ─── Provider Allowlist (Constant Combinator #1) ───
    prov_allowlist_id = ids.next()
    prov_filters = []
    for i, item_name in enumerate(provide_allowlist):
        prov_filters.append({
            "signal": item_signal(item_name),
            "count": 1,
            "index": i + 1,
        })
    prov_allowlist = Entity(
        entity_number=prov_allowlist_id,
        name="constant-combinator",
        position={"x": 4, "y": 3},
        control_behavior={"filters": prov_filters},
    )
    ent_map[prov_allowlist_id] = prov_allowlist

    # ─── Provider Decider (#1) ───
    prov_decider_id = ids.next()
    prov_decider = Entity(
        entity_number=prov_decider_id,
        name="decider-combinator",
        position={"x": 6, "y": 3},
        control_behavior={
            "decider_conditions": {
                "conditions": [
                    {
                        "first_signal": {"type": "virtual", "name": "signal-each"},
                        "constant": 0,
                        "comparator": ">",
                    }
                ],
                "outputs": [
                    {
                        "signal": {"type": "virtual", "name": "signal-each"},
                        "copy_count_from_input": True,
                    }
                ],
            },
        },
    )
    ent_map[prov_decider_id] = prov_decider

    # Provider wiring
    add_wire(ent_map, ltn_id, 1, prov_decider_id, 1, "red")
    add_wire(ent_map, prov_allowlist_id, 1, prov_decider_id, 1, "green")

    # ═══ RECEIVER PATH ═══

    # ─── Arithmetic Combinator (Inverter) ───
    arith_id = ids.next()
    arith = Entity(
        entity_number=arith_id,
        name="arithmetic-combinator",
        position={"x": 2, "y": 5},
        control_behavior={
            "arithmetic_conditions": {
                "first_signal": {"type": "virtual", "name": "signal-each"},
                "second_constant": -1,
                "operation": "*",
                "output_signal": {"type": "virtual", "name": "signal-each"},
            },
        },
    )
    ent_map[arith_id] = arith

    # ─── Receiver Allowlist (Constant Combinator #2) ───
    recv_allowlist_id = ids.next()
    recv_filters = []
    for i, item_name in enumerate(request_allowlist):
        recv_filters.append({
            "signal": item_signal(item_name),
            "count": 1,
            "index": i + 1,
        })
    recv_allowlist = Entity(
        entity_number=recv_allowlist_id,
        name="constant-combinator",
        position={"x": 4, "y": 5},
        control_behavior={"filters": recv_filters},
    )
    ent_map[recv_allowlist_id] = recv_allowlist

    # ─── Receiver Decider (#2) ───
    recv_decider_id = ids.next()
    recv_decider = Entity(
        entity_number=recv_decider_id,
        name="decider-combinator",
        position={"x": 6, "y": 5},
        control_behavior={
            "decider_conditions": {
                "conditions": [
                    {
                        "first_signal": {"type": "virtual", "name": "signal-each"},
                        "constant": 0,
                        "comparator": ">",
                    }
                ],
                "outputs": [
                    {
                        "signal": {"type": "virtual", "name": "signal-each"},
                        "copy_count_from_input": True,
                    }
                ],
            },
        },
    )
    ent_map[recv_decider_id] = recv_decider

    # Receiver wiring
    add_wire(ent_map, ltn_id, 1, arith_id, 1, "red")
    add_wire(ent_map, arith_id, 2, recv_decider_id, 1, "red")
    add_wire(ent_map, recv_allowlist_id, 1, recv_decider_id, 1, "green")

    # ─── Load Inserters + Chests (bottom = provider) ───
    load_inserter_ids = []
    for w in range(wagons):
        wagon_x_base = (w + 1) * -7
        for i in range(inserters_per_wagon):
            x = wagon_x_base - i

            # Provider chest (bottom)
            chest_id = ids.next()
            chest = Entity(
                entity_number=chest_id,
                name="steel-chest",
                position={"x": x, "y": 2},
            )
            ent_map[chest_id] = chest

            # Load inserter (bottom, grabs from chest, places into train)
            ins_id = ids.next()
            inserter = Entity(
                entity_number=ins_id,
                name="bulk-inserter",
                position={"x": x, "y": 1},
                direction=0,  # north — grab from south (chest), place north (train)
                control_behavior={
                    "circuit_mode_of_operation": 1,
                },
            )
            ent_map[ins_id] = inserter
            load_inserter_ids.append(ins_id)

    # ─── Unload Inserters + Chests (top = receiver) ───
    unload_inserter_ids = []
    for w in range(wagons):
        wagon_x_base = (w + 1) * -7
        for i in range(inserters_per_wagon):
            x = wagon_x_base - i

            # Receiver chest (top)
            chest_id = ids.next()
            chest = Entity(
                entity_number=chest_id,
                name="steel-chest",
                position={"x": x, "y": -2},
            )
            ent_map[chest_id] = chest

            # Unload inserter (top, grabs from train, places into chest)
            ins_id = ids.next()
            inserter = Entity(
                entity_number=ins_id,
                name="bulk-inserter",
                position={"x": x, "y": -1},
                direction=0,  # north — grab from south (train), place north (chest)
                control_behavior={
                    "circuit_mode_of_operation": 1,
                },
            )
            ent_map[ins_id] = inserter
            unload_inserter_ids.append(ins_id)

    # ─── Wire: Provider Decider output → load inserters (green) ───
    for ins_id in load_inserter_ids:
        add_wire(ent_map, prov_decider_id, 2, ins_id, 1, "green")

    # ─── Wire: Receiver Decider output → unload inserters (green) ───
    for ins_id in unload_inserter_ids:
        add_wire(ent_map, recv_decider_id, 2, ins_id, 1, "green")

    entities_list = [e.to_dict() for e in ent_map.values()]
    bp = {
        "blueprint": {
            "item": "blueprint",
            "label": station_name,
            "entities": entities_list,
            "version": 562949954076672,
        }
    }
    annotated = json.dumps(bp, indent=2)
    return bp, annotated


# ─── Output formatting ──────────────────────────────────────────────────────

def format_blueprint_section(
    title: str,
    bp_dict: dict,
    bp_string: str,
    annotated_json: str,
) -> str:
    """Format a single blueprint as a markdown section."""
    lines = [
        f"## {title}",
        "",
        f"**Station name:** {bp_dict['blueprint']['label']}",
        f"**Entities:** {len(bp_dict['blueprint']['entities'])}",
        "",
        "### Blueprint String (paste into Factorio)",
        "",
        "```",
        bp_string,
        "```",
        "",
        "### Uncompressed JSON (for reference/editing)",
        "",
        "```json",
        annotated_json,
        "```",
        "",
    ]
    return "\n".join(lines)


def generate_output(sections: list[tuple[str, dict, str, str]], output_path: Optional[str] = None):
    """Generate final markdown output with all blueprint sections."""
    lines = [
        "# LTN Station Blueprints",
        "",
        f"Generated by `factorio-blueprint-generator.py`",
        "",
        "---",
        "",
    ]

    for title, bp_dict, bp_string, annotated in sections:
        lines.append(format_blueprint_section(title, bp_dict, bp_string, annotated))
        lines.append("---\n")

    content = "\n".join(lines)

    if output_path:
        with open(output_path, "w") as f:
            f.write(content)
        print(f"Written to {output_path}", file=sys.stderr)
    else:
        print(content)


# ─── CLI ─────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate Factorio LTN station blueprints with allowlist filtering.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --provider --allowlist iron-plate copper-plate
  %(prog)s --receiver --allowlist iron-ore copper-ore --wagons 4
  %(prog)s --dual --provide iron-plate --request copper-ore
  %(prog)s --all --output stations.md
  %(prog)s --config stations.json --output out.md

Config file format (JSON):
  {
    "provider": {"allowlist": ["iron-plate"], "wagons": 2, "station_name": "My Provider"},
    "receiver": {"allowlist": ["iron-ore"], "wagons": 2},
    "dual": {"provide_allowlist": ["iron-plate"], "request_allowlist": ["copper-ore"]}
  }
        """,
    )

    mode = parser.add_argument_group("Station type (pick one or more)")
    mode.add_argument("--provider", action="store_true", help="Generate provider station")
    mode.add_argument("--receiver", action="store_true", help="Generate receiver station")
    mode.add_argument("--dual", action="store_true", help="Generate dual-mode station")
    mode.add_argument("--all", action="store_true", help="Generate all 3 station types")

    items = parser.add_argument_group("Item lists (for CLI mode)")
    items.add_argument("--allowlist", nargs="+", metavar="ITEM",
                       help="Items for provider/receiver allowlist (e.g., iron-plate copper-plate)")
    items.add_argument("--provide", nargs="+", metavar="ITEM",
                       help="Items for dual-mode provider allowlist")
    items.add_argument("--request", nargs="+", metavar="ITEM",
                       help="Items for dual-mode receiver allowlist")

    opts = parser.add_argument_group("Options")
    opts.add_argument("--wagons", type=int, default=2, help="Number of cargo wagons (default: 2)")
    opts.add_argument("--inserters", type=int, default=6, dest="inserters_per_wagon",
                      help="Inserters per wagon (default: 6)")
    opts.add_argument("--load-from-top", action="store_true",
                      help="Provider: load from top instead of bottom")
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

    sections: list[tuple[str, dict, str, str]] = []
    default_allowlist = ["iron-plate", "copper-plate"]

    # ─── Config file mode ───
    if args.config:
        with open(args.config) as f:
            config = json.load(f)

        if "provider" in config:
            c = config["provider"]
            bp, annotated = generate_provider_blueprint(
                allowlist=c.get("allowlist", default_allowlist),
                wagons=c.get("wagons", 2),
                inserters_per_wagon=c.get("inserters_per_wagon", 6),
                load_from_top=c.get("load_from_top", False),
                station_name=c.get("station_name", "LTN Provider"),
            )
            bp_str = encode_blueprint(bp)
            verify_blueprint(bp_str, "Provider")
            sections.append(("Provider Station", bp, bp_str, annotated))

        if "receiver" in config:
            c = config["receiver"]
            bp, annotated = generate_receiver_blueprint(
                allowlist=c.get("allowlist", default_allowlist),
                wagons=c.get("wagons", 2),
                inserters_per_wagon=c.get("inserters_per_wagon", 6),
                station_name=c.get("station_name", "LTN Receiver"),
            )
            bp_str = encode_blueprint(bp)
            verify_blueprint(bp_str, "Receiver")
            sections.append(("Receiver Station", bp, bp_str, annotated))

        if "dual" in config:
            c = config["dual"]
            bp, annotated = generate_dual_blueprint(
                provide_allowlist=c.get("provide_allowlist", default_allowlist),
                request_allowlist=c.get("request_allowlist", default_allowlist),
                wagons=c.get("wagons", 2),
                inserters_per_wagon=c.get("inserters_per_wagon", 6),
                station_name=c.get("station_name", "LTN Dual"),
            )
            bp_str = encode_blueprint(bp)
            verify_blueprint(bp_str, "Dual")
            sections.append(("Dual-Mode Station", bp, bp_str, annotated))

    # ─── CLI mode ───
    else:
        if not (args.provider or args.receiver or args.dual or args.all):
            parser.error("Specify at least one of: --provider, --receiver, --dual, --all")

        if args.all or args.provider:
            allowlist = args.allowlist or default_allowlist
            name = args.station_name or "LTN Provider"
            bp, annotated = generate_provider_blueprint(
                allowlist=allowlist,
                wagons=args.wagons,
                inserters_per_wagon=args.inserters_per_wagon,
                load_from_top=args.load_from_top,
                station_name=name,
            )
            bp_str = encode_blueprint(bp)
            verify_blueprint(bp_str, "Provider")
            sections.append(("Provider Station", bp, bp_str, annotated))

        if args.all or args.receiver:
            allowlist = args.allowlist or default_allowlist
            name = args.station_name or "LTN Receiver"
            bp, annotated = generate_receiver_blueprint(
                allowlist=allowlist,
                wagons=args.wagons,
                inserters_per_wagon=args.inserters_per_wagon,
                station_name=name,
            )
            bp_str = encode_blueprint(bp)
            verify_blueprint(bp_str, "Receiver")
            sections.append(("Receiver Station", bp, bp_str, annotated))

        if args.all or args.dual:
            provide = args.provide or args.allowlist or default_allowlist
            request = args.request or args.allowlist or default_allowlist
            name = args.station_name or "LTN Dual"
            bp, annotated = generate_dual_blueprint(
                provide_allowlist=provide,
                request_allowlist=request,
                wagons=args.wagons,
                inserters_per_wagon=args.inserters_per_wagon,
                station_name=name,
            )
            bp_str = encode_blueprint(bp)
            verify_blueprint(bp_str, "Dual")
            sections.append(("Dual-Mode Station", bp, bp_str, annotated))

    if not sections:
        parser.error("No stations to generate. Check your config or flags.")

    generate_output(sections, args.output)


if __name__ == "__main__":
    main()
