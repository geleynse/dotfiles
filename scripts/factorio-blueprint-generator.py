#!/usr/bin/env python3
"""
Factorio 2.0 LTN Blueprint Generator

Generates importable blueprint strings for LTN (Logistic Train Network) train
stations with allowlist filtering and overload prevention. Outputs individual
blueprints or a blueprint book with 1/2/3 wagon variants.

Required mods:
  - LTN (Logistic Train Network)
  - LTN Combinator (original, 2.0-compatible)

For full design documentation see:
  ~/Obsidian/vault/projects/factorio-ltn-blueprints.md  (in-game guide)
  ~/Obsidian/vault/projects/factorio-ltn-generator.md   (script & format docs)

LTN 3-entity stop architecture:
  An LTN stop is THREE separate placeable entities, all included in blueprints:

  1. logistic-train-stop         — the visible 2x2 stop (vanilla read-train works)
  2. logistic-train-stop-input   — 1x1 lamp: feeds config INTO LTN (from circuit net)
  3. logistic-train-stop-output  — 1x1 yellow constant combinator: LTN writes the
                                   active delivery signal here (positive=load,
                                   negative=unload). This is the delivery source.

  The lamp and yellow CC sit overlapping the stop's footprint (LTN gives them
  no collision). Each has its own circuit connections, which lets us cleanly
  subtract train-contents from delivery for overload prevention.

  The ltn-combinator (config) is wired GREEN → input lamp.

Provider overload prevention circuit:
  output yellow CC (red, delivery)  ──→ ┐
  stop (red, train contents) → arith (×−1) → ┴→ decider RED input
                                                 (combined: remaining = delivery − cargo)
  allowlist CC (green) ──→ decider GREEN input

  Decider (per-network): red Each > 0 AND green Each > 0 → output Each from red
  Decider output (green) → load inserters (set-filters mode)

  When remaining hits 0, signal vanishes → inserter filter clears → loading stops.

Receiver circuit:
  output yellow CC (red, negative request) → arith (×−1) → decider RED input
  allowlist CC (green) → decider GREEN input
  Decider (per-network: red Each > 0 AND green Each > 0) → unload inserters

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


def build_provider_decider(eid: int, position: dict) -> Entity:
    """Decider for provider stations: per-network red Each > 0 AND green Each > 0.

    Uses Factorio 2.0 per-network conditions to check BOTH:
      - Red wire: remaining = delivery − train_contents > 0  (still items to load)
      - Green wire: allowlist signal > 0  (item is permitted)
    Output copies count from red wire only (the remaining amount).
    When remaining hits 0, signal vanishes and inserter filter clears.
    """
    return Entity(
        entity_number=eid,
        name="decider-combinator",
        position=position,
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


def build_receiver_decider(eid: int, position: dict) -> Entity:
    """Decider for receiver stations: Each > 0, output Each with copy_count.

    Simpler than provider — no quantity control needed. Just checks that the
    combined signal (inverted delivery + allowlist) is positive.
    """
    return Entity(
        entity_number=eid,
        name="decider-combinator",
        position=position,
        control_behavior={
            "decider_conditions": {
                "conditions": [{
                    "first_signal": virtual_signal("signal-each"),
                    "constant": 0,
                    "comparator": ">",
                }],
                "outputs": [{
                    "signal": virtual_signal("signal-each"),
                    "copy_count_from_input": True,
                }],
            },
        },
    )


def build_inverter(eid: int, position: dict) -> Entity:
    """Arithmetic combinator: Each * -1."""
    return Entity(
        entity_number=eid,
        name="arithmetic-combinator",
        position=position,
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

PROVIDER_DESC = (
    "AFTER PLACING: Connect ONE red wire from the LTN yellow combinator "
    "(auto-created output entity next to stop) to the decider combinator's "
    "red input. This provides the delivery signal for overload prevention. "
    "The stop reads train contents; the arithmetic inverts them; the decider "
    "computes remaining = delivery - cargo and filters through the allowlist."
)

RECEIVER_DESC = (
    "AFTER PLACING: Connect ONE red wire from the LTN yellow combinator "
    "(auto-created output entity next to stop) to the arithmetic combinator's "
    "red input. This provides the delivery signal. The arithmetic inverts "
    "negative request signals to positive; the decider filters through the "
    "allowlist. Extra unloading beyond the exact request amount is acceptable."
)

DUAL_DESC = (
    "AFTER PLACING: Connect TWO red wires from the LTN yellow combinator "
    "(auto-created output entity next to stop): one to the provider decider's "
    "red input (overload prevention), one to the receiver arithmetic's red "
    "input (delivery inversion). See vault docs for full signal flow."
)


def generate_provider(
    allowlist: list[str],
    wagons: int = 2,
    inserters_per_wagon: int = 6,
    load_from_top: bool = False,
    station_name: str = "LTN Provider",
) -> dict:
    """Generate a provider station blueprint with overload prevention.

    Signal flow:
      Yellow combinator (delivery, red) ──→ ┐
                                             ├→ decider input red = remaining
      Stop (read train, red) → arith (×-1, red out) ──→ ┘

      Allowlist CC (green) ──→ decider input green

      Decider: red Each > 0 AND green Each > 0
               output: Each, count from red (remaining amount)
      Decider output (green) → inserters (set-filters)

    When remaining hits 0, signal vanishes → inserter filter clears → stops loading.
    The yellow combinator wire must be connected manually after placement.
    """
    ids = IDCounter()
    entities: list[Entity] = []
    wires: list = []

    # ─── Logistic train stop (read stopped train enabled) ───
    stop_id = ids.next()
    entities.append(Entity(
        entity_number=stop_id,
        name="logistic-train-stop",
        position={"x": 0, "y": 0},
        direction=WEST,
        station=station_name,
        control_behavior={"read_stopped_train": True},
    ))

    # ─── LTN Combinator (input-only, auto-links to lamp) ───
    ltn_id = ids.next()
    entities.append(Entity(
        entity_number=ltn_id,
        name="ltn-combinator",
        position={"x": 2, "y": 2},
    ))

    # ─── Arithmetic combinator (invert train contents: Each × -1) ───
    arith_id = ids.next()
    entities.append(build_inverter(arith_id, {"x": 4, "y": 2}))

    # ─── Allowlist constant combinator ───
    cc_id = ids.next()
    entities.append(build_allowlist_cc(cc_id, {"x": 6, "y": 2}, allowlist))

    # ─── Decider combinator (per-network: red > 0 AND green > 0) ───
    decider_id = ids.next()
    entities.append(build_provider_decider(decider_id, {"x": 8, "y": 2}))

    # ─── Wiring ───
    # Stop (train contents, red) → arithmetic input
    add_wire(wires, stop_id, RED, arith_id, RED)
    # Arithmetic output (inverted train contents, red) → decider input red
    # This combines on the decider's red input with the yellow combinator wire
    # (which the user connects manually after placement)
    add_wire(wires, arith_id, OUT_RED, decider_id, RED)
    # Allowlist CC (green) → decider input green
    add_wire(wires, cc_id, GREEN, decider_id, GREEN)

    # ─── Chests + load inserters per wagon ───
    inserter_ids = []
    for w in range(wagons):
        wagon_x = (w + 1) * -7
        for i in range(inserters_per_wagon):
            x = wagon_x - i

            if load_from_top:
                chest_y, ins_y, ins_dir = -2, -1, SOUTH
            else:
                chest_y, ins_y, ins_dir = 2, 1, NORTH

            chest_id = ids.next()
            entities.append(Entity(chest_id, "steel-chest", {"x": x, "y": chest_y}))

            ins_id = ids.next()
            entities.append(Entity(
                entity_number=ins_id,
                name="bulk-inserter",
                position={"x": x, "y": ins_y},
                direction=ins_dir,
                control_behavior={"circuit_mode_of_operation": 1},
            ))
            inserter_ids.append(ins_id)

    # Decider output → all inserters (green)
    for ins_id in inserter_ids:
        add_wire(wires, decider_id, OUT_GREEN, ins_id, GREEN)

    return build_blueprint(station_name, entities, wires, description=PROVIDER_DESC)


def generate_receiver(
    allowlist: list[str],
    wagons: int = 2,
    inserters_per_wagon: int = 6,
    station_name: str = "LTN Receiver",
) -> dict:
    """Generate a receiver station blueprint.

    Signal flow:
      Yellow combinator (delivery, red) → arithmetic (×-1) → decider input red
      Allowlist CC (green) → decider input green
      Decider (Each > 0, copy count) output (green) → inserters (set-filters)

    No quantity control — inserters unload all matching items. Extra unloading
    is acceptable per design. The yellow combinator wire must be connected
    manually after placement.
    """
    ids = IDCounter()
    entities: list[Entity] = []
    wires: list = []

    stop_id = ids.next()
    entities.append(Entity(
        entity_number=stop_id,
        name="logistic-train-stop",
        position={"x": 0, "y": 0},
        direction=WEST,
        station=station_name,
    ))

    ltn_id = ids.next()
    entities.append(Entity(
        entity_number=ltn_id,
        name="ltn-combinator",
        position={"x": 2, "y": 2},
    ))

    # Arithmetic: invert delivery signals (negative → positive for set-filters)
    arith_id = ids.next()
    entities.append(build_inverter(arith_id, {"x": 4, "y": 2}))

    cc_id = ids.next()
    entities.append(build_allowlist_cc(cc_id, {"x": 6, "y": 2}, allowlist))

    decider_id = ids.next()
    entities.append(build_receiver_decider(decider_id, {"x": 8, "y": 2}))

    # Yellow combinator wire is manual — arith input is the connection point.
    # Arith output (inverted, red) → decider input red
    add_wire(wires, arith_id, OUT_RED, decider_id, RED)
    # Allowlist CC (green) → decider input green
    add_wire(wires, cc_id, GREEN, decider_id, GREEN)

    # Unload inserters + chests (top side)
    inserter_ids = []
    for w in range(wagons):
        wagon_x = (w + 1) * -7
        for i in range(inserters_per_wagon):
            x = wagon_x - i

            chest_id = ids.next()
            entities.append(Entity(chest_id, "steel-chest", {"x": x, "y": -2}))

            ins_id = ids.next()
            entities.append(Entity(
                entity_number=ins_id,
                name="bulk-inserter",
                position={"x": x, "y": -1},
                direction=NORTH,
                control_behavior={"circuit_mode_of_operation": 1},
            ))
            inserter_ids.append(ins_id)

    for ins_id in inserter_ids:
        add_wire(wires, decider_id, OUT_GREEN, ins_id, GREEN)

    return build_blueprint(station_name, entities, wires, description=RECEIVER_DESC)


def generate_dual(
    provide_allowlist: list[str],
    request_allowlist: list[str],
    wagons: int = 2,
    inserters_per_wagon: int = 6,
    station_name: str = "LTN Dual",
) -> dict:
    """Generate a dual-mode station (provider + receiver).

    Provider path (bottom inserters — load items onto train):
      Yellow combinator (red) + stop read-train → arith (×-1) → remaining on red
      → provider decider (per-network) + provider CC (green) → load inserters

    Receiver path (top inserters — unload items from train):
      Yellow combinator (red) → arith #2 (×-1) → decider + receiver CC → unload inserters

    Two manual red wires from yellow combinator needed after placement.
    """
    ids = IDCounter()
    entities: list[Entity] = []
    wires: list = []

    stop_id = ids.next()
    entities.append(Entity(
        entity_number=stop_id,
        name="logistic-train-stop",
        position={"x": 0, "y": 0},
        direction=WEST,
        station=station_name,
        control_behavior={"read_stopped_train": True},
    ))

    ltn_id = ids.next()
    entities.append(Entity(
        entity_number=ltn_id,
        name="ltn-combinator",
        position={"x": 2, "y": 3},
    ))

    # ═══ PROVIDER PATH (bottom — load onto train) ═══

    # Arithmetic: invert train contents for subtraction
    prov_arith_id = ids.next()
    entities.append(build_inverter(prov_arith_id, {"x": 4, "y": 3}))

    prov_cc_id = ids.next()
    entities.append(build_allowlist_cc(prov_cc_id, {"x": 6, "y": 3}, provide_allowlist))

    prov_decider_id = ids.next()
    entities.append(build_provider_decider(prov_decider_id, {"x": 8, "y": 3}))

    # Stop (train contents) → provider arithmetic
    add_wire(wires, stop_id, RED, prov_arith_id, RED)
    # Provider arithmetic output → provider decider red input
    add_wire(wires, prov_arith_id, OUT_RED, prov_decider_id, RED)
    # Provider allowlist → provider decider green input
    add_wire(wires, prov_cc_id, GREEN, prov_decider_id, GREEN)

    # ═══ RECEIVER PATH (top — unload from train) ═══

    # Arithmetic: invert delivery signals (negative → positive)
    recv_arith_id = ids.next()
    entities.append(build_inverter(recv_arith_id, {"x": 4, "y": 5}))

    recv_cc_id = ids.next()
    entities.append(build_allowlist_cc(recv_cc_id, {"x": 6, "y": 5}, request_allowlist))

    recv_decider_id = ids.next()
    entities.append(build_receiver_decider(recv_decider_id, {"x": 8, "y": 5}))

    # Yellow combinator wire to recv_arith is manual
    # Receiver arithmetic output → receiver decider red
    add_wire(wires, recv_arith_id, OUT_RED, recv_decider_id, RED)
    # Receiver allowlist → receiver decider green
    add_wire(wires, recv_cc_id, GREEN, recv_decider_id, GREEN)

    # ─── Load inserters + chests (bottom = provider) ───
    load_ids = []
    for w in range(wagons):
        wagon_x = (w + 1) * -7
        for i in range(inserters_per_wagon):
            x = wagon_x - i
            chest_id = ids.next()
            entities.append(Entity(chest_id, "steel-chest", {"x": x, "y": 2}))
            ins_id = ids.next()
            entities.append(Entity(
                entity_number=ins_id,
                name="bulk-inserter",
                position={"x": x, "y": 1},
                direction=NORTH,
                control_behavior={"circuit_mode_of_operation": 1},
            ))
            load_ids.append(ins_id)

    # ─── Unload inserters + chests (top = receiver) ───
    unload_ids = []
    for w in range(wagons):
        wagon_x = (w + 1) * -7
        for i in range(inserters_per_wagon):
            x = wagon_x - i
            chest_id = ids.next()
            entities.append(Entity(chest_id, "steel-chest", {"x": x, "y": -2}))
            ins_id = ids.next()
            entities.append(Entity(
                entity_number=ins_id,
                name="bulk-inserter",
                position={"x": x, "y": -1},
                direction=NORTH,
                control_behavior={"circuit_mode_of_operation": 1},
            ))
            unload_ids.append(ins_id)

    for ins_id in load_ids:
        add_wire(wires, prov_decider_id, OUT_GREEN, ins_id, GREEN)
    for ins_id in unload_ids:
        add_wire(wires, recv_decider_id, OUT_GREEN, ins_id, GREEN)

    return build_blueprint(station_name, entities, wires, description=DUAL_DESC)


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
        "Generated by `factorio-blueprint-generator.py` for Factorio 2.0 + LTN",
        "",
        "**IMPORTANT:** After placing any blueprint, connect a red wire from the",
        "LTN yellow combinator (auto-created output entity next to the stop) to",
        "the appropriate combinator input. See each blueprint's description.",
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
        """,
    )

    mode = parser.add_argument_group("Station type")
    mode.add_argument("--provider", action="store_true", help="Generate provider station")
    mode.add_argument("--receiver", action="store_true", help="Generate receiver station")
    mode.add_argument("--dual", action="store_true", help="Generate dual-mode station")
    mode.add_argument("--all", action="store_true",
                      help="Generate book with all types × 1/2/3 wagons")

    items = parser.add_argument_group("Item lists")
    items.add_argument("--allowlist", nargs="+", metavar="ITEM",
                       help="Items for provider/receiver (e.g., iron-plate copper-plate)")
    items.add_argument("--provide", nargs="+", metavar="ITEM",
                       help="Items for dual-mode provider allowlist")
    items.add_argument("--request", nargs="+", metavar="ITEM",
                       help="Items for dual-mode receiver allowlist")

    opts = parser.add_argument_group("Options")
    opts.add_argument("--wagons", type=int, default=2,
                      help="Cargo wagons per train (default: 2, ignored with --all)")
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
                inserters_per_wagon=c.get("inserters_per_wagon", 6),
                load_from_top=c.get("load_from_top", False),
                station_name=c.get("station_name", "LTN Provider"),
            )
            blueprints.append(bp)

        if "receiver" in config:
            c = config["receiver"]
            bp = generate_receiver(
                allowlist=c.get("allowlist", default_allowlist),
                wagons=c.get("wagons", 2),
                inserters_per_wagon=c.get("inserters_per_wagon", 6),
                station_name=c.get("station_name", "LTN Receiver"),
            )
            blueprints.append(bp)

        if "dual" in config:
            c = config["dual"]
            bp = generate_dual(
                provide_allowlist=c.get("provide_allowlist", default_allowlist),
                request_allowlist=c.get("request_allowlist", default_allowlist),
                wagons=c.get("wagons", 2),
                inserters_per_wagon=c.get("inserters_per_wagon", 6),
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

    # ─── --all mode: book with all types × 1/2/3 wagons ───
    elif args.all:
        allowlist = args.allowlist or default_allowlist
        provide = args.provide or allowlist
        request = args.request or allowlist
        ipw = args.inserters_per_wagon

        all_blueprints = []
        for wagon_count in (1, 2, 3):
            all_blueprints.append(generate_provider(
                allowlist=allowlist,
                wagons=wagon_count,
                inserters_per_wagon=ipw,
                load_from_top=args.load_from_top,
                station_name=f"Provider ({wagon_count}W)",
            ))
            all_blueprints.append(generate_receiver(
                allowlist=allowlist,
                wagons=wagon_count,
                inserters_per_wagon=ipw,
                station_name=f"Receiver ({wagon_count}W)",
            ))
            all_blueprints.append(generate_dual(
                provide_allowlist=provide,
                request_allowlist=request,
                wagons=wagon_count,
                inserters_per_wagon=ipw,
                station_name=f"Dual ({wagon_count}W)",
            ))

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
                inserters_per_wagon=args.inserters_per_wagon,
                load_from_top=args.load_from_top,
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
                inserters_per_wagon=args.inserters_per_wagon,
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
                inserters_per_wagon=args.inserters_per_wagon,
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
