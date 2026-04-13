"""Factorio 2.0 blueprint primitives — reusable across any blueprint generator.

Not a CLI. Import from generator scripts.

Provides:
  - Direction/wire constants (NORTH/EAST/SOUTH/WEST, RED/GREEN/OUT_RED/OUT_GREEN)
  - Signal helpers (item_signal, virtual_signal)
  - Entity dataclass, IDCounter
  - add_wire (sorts endpoints by id per Factorio convention)
  - encode_blueprint / decode_blueprint / verify_blueprint
  - build_blueprint / build_book
  - Generic entity builders: build_power_pole, build_rail, build_curved_rail
"""

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
COPPER = 5      # power pole copper connection

# Blueprint version. Using the value observed in blueprints exported from
# current Factorio 2.0 (avoids auto-migration shifts on import).
FACTORIO_VERSION = 562949958402048


# ─── Signal helpers ──────────────────────────────────────────────────────────

def item_signal(name: str) -> dict:
    return {"type": "item", "name": name}


def virtual_signal(name: str) -> dict:
    return {"type": "virtual", "name": name}


# ─── Blueprint data structures ───────────────────────────────────────────────

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
    use_filters: Optional[bool] = None

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
        if self.use_filters is not None:
            d["use_filters"] = self.use_filters
        return d


class IDCounter:
    def __init__(self, start=1):
        self._n = start

    def next(self) -> int:
        n = self._n
        self._n += 1
        return n


# ─── Wire helpers ────────────────────────────────────────────────────────────

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
    """Decode a Factorio blueprint string back to its dict form."""
    if not bp_string.startswith("0"):
        raise ValueError("Blueprint string must start with '0' version byte")
    return json.loads(zlib.decompress(base64.b64decode(bp_string[1:])))


def verify_blueprint(bp_string: str, label: str) -> bool:
    """Round-trip a blueprint string and print a one-line summary to stderr."""
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


# ─── Blueprint & book assemblers ─────────────────────────────────────────────

def build_blueprint(label: str, entities: list, wires: list,
                    description: str = "",
                    icons: list = None,
                    parameters: list = None) -> dict:
    """Wrap entities+wires into a blueprint dict. Icons default to a single rail icon
    to match what Factorio produces natively for station blueprints.

    If `parameters` is given, it's a list of {"type", "name", "id", ...} dicts that
    become blueprint-level parameter definitions, prompted at paste time.
    """
    bp = {"blueprint": {"item": "blueprint"}}
    bp["blueprint"]["icons"] = icons if icons is not None else [
        {"signal": {"name": "rail"}, "index": 1}
    ]
    if label:
        bp["blueprint"]["label"] = label
    bp["blueprint"]["entities"] = [e.to_dict() for e in entities]
    if wires:
        bp["blueprint"]["wires"] = wires
    if parameters:
        bp["blueprint"]["parameters"] = parameters
    if description:
        bp["blueprint"]["description"] = description
    bp["blueprint"]["version"] = FACTORIO_VERSION
    return bp


def build_book(label: str, blueprints: list) -> dict:
    """Wrap a list of blueprint dicts into a blueprint book."""
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


# ─── Generic entity builders ─────────────────────────────────────────────────

def build_power_pole(ids: IDCounter, x: float, y: float,
                     name: str = "medium-electric-pole") -> tuple:
    """Power pole at (x, y). Returns (id, entity)."""
    eid = ids.next()
    return eid, Entity(entity_number=eid, name=name, position={"x": x, "y": y})


def build_rail(ids: IDCounter, x: float, y: float, direction: int = EAST) -> tuple:
    """Straight rail at (x, y). Returns (id, entity)."""
    eid = ids.next()
    return eid, Entity(
        entity_number=eid,
        name="straight-rail",
        position={"x": x, "y": y},
        direction=direction,
    )


def build_curved_rail(ids: IDCounter, x: float, y: float, direction: int,
                      name: str = "curved-rail-a") -> tuple:
    """Curved rail at (x, y). Returns (id, entity)."""
    eid = ids.next()
    return eid, Entity(
        entity_number=eid,
        name=name,
        position={"x": x, "y": y},
        direction=direction,
    )
