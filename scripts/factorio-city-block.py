#!/usr/bin/env python3
"""
Factorio 2.0 city block blueprint generator.

Emits a 128×128 rail city block:
  - 2-track RHD perimeter loop (outer + inner rails, 10 tiles apart)
  - 4-way roundabout intersection at each corner
  - Chain signals at roundabout entries, rail signals at exits
  - 16 big-electric-poles along the perimeter
  - 8 roboports (4 at corners, 4 at side midpoints)
  - 4 radars (1 per corner)
  - 128×128 sand-3 tile fill (configurable)

The corner roundabout geometry is verified against a hand-edited NE corner and
rotated 90°/180°/270° around the block center (62, 62) to produce the other 3.
Support entities (roboports/poles/radars) are hand-placed per corner because
they'd collide under naïve rotation.

Usage:
  python factorio-city-block.py                  # prints blueprint string
  python factorio-city-block.py --output bp.md   # writes markdown w/ string
  python factorio-city-block.py --json out.json  # dumps decoded JSON (debug)
  python factorio-city-block.py --no-tiles       # skip tile fill
  python factorio-city-block.py --tile concrete  # alt tile type
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from factorio_blueprint import (
    Entity, IDCounter, COPPER,
    add_wire,
    encode_blueprint, verify_blueprint, build_blueprint,
)


# ─── Geometry constants ──────────────────────────────────────────────────────

BLOCK_SIZE = 128
CENTER = 62  # rotation pivot; NE→SE→SW→NW maps via 90° CW around (62, 62)

# Perimeter rail offsets from block edge (top/left): outer=y8, inner=y18.
# Rotational symmetry around (62, 62) puts the bottom/right rails at 106/116.
OUTER_OFFSET = 8
INNER_OFFSET = 18
BOTTOM_INNER = 2 * CENTER - INNER_OFFSET  # 106
BOTTOM_OUTER = 2 * CENTER - OUTER_OFFSET  # 116

# Straight-rail span per side (x-range for top/bottom, y-range for left/right).
# 31 rails × 2 tiles each = 62 tile span between corner roundabout exits.
RAIL_SPAN_LO = 32
RAIL_SPAN_HI = 92
RAIL_SPAN_STEP = 2


# ─── NE corner template ──────────────────────────────────────────────────────
#
# Rail + signal geometry for the NE corner, extracted from a hand-edited
# blueprint. Rotating this 90°/180°/270° around (62, 62) gives SE/SW/NW.
# Format: (entity_name, x, y, direction)
NE_CORNER_TEMPLATE = [
    # North-side curves (extend toward y=0 edge; required for the roundabout loop)
    ("curved-rail-a", 109.0,  0.0, 12),
    ("curved-rail-a", 113.0,  0.0,  6),
    ("curved-rail-b", 104.0,  2.0, 12),
    ("curved-rail-b", 118.0,  2.0,  6),

    # Interior roundabout curves
    ("curved-rail-b", 100.0,  6.0,  4),
    ("curved-rail-b", 100.0,  6.0,  2),
    ("curved-rail-b", 122.0,  6.0,  0),

    # West-side connector: top perimeter rails → roundabout
    ("curved-rail-a",  95.0,  8.0,  4),
    ("curved-rail-a",  95.0, 18.0,  6),

    # Interior roundabout curves (continued)
    ("curved-rail-a",  98.0, 11.0,  2),
    ("curved-rail-a", 124.0, 11.0,  0),
    ("curved-rail-a",  98.0, 15.0,  8),
    ("curved-rail-a", 124.0, 15.0, 10),
    ("curved-rail-b", 100.0, 20.0,  8),
    ("curved-rail-b", 100.0, 20.0,  6),
    ("curved-rail-b", 122.0, 20.0, 10),
    ("curved-rail-b", 104.0, 24.0, 14),
    ("curved-rail-b", 104.0, 24.0,  0),
    ("curved-rail-b", 118.0, 24.0,  4),
    ("curved-rail-b", 118.0, 24.0,  2),
    ("curved-rail-a", 109.0, 26.0, 14),
    ("curved-rail-a", 113.0, 26.0,  4),

    # South-side connector: right perimeter rails → roundabout
    ("curved-rail-a", 106.0, 29.0,  0),
    ("curved-rail-a", 116.0, 29.0,  2),

    # Signals — reference NE positions minus 3 rail-signals that user verified
    # were redundant ((97.5,8.5,1), (121.5,3.5,6), (106.5,26.5,13)).
    ("rail-chain-signal", 100.5,  3.5,  2),
    ("rail-signal",        98.5,  5.5,  3),
    ("rail-chain-signal",  97.5, 17.5, 15),
    ("rail-chain-signal",  98.5, 20.5, 13),
    ("rail-signal",       103.5, 25.5, 15),
    ("rail-chain-signal", 115.5, 26.5, 11),
    ("rail-chain-signal", 118.5, 25.5,  9),
]


# ─── Support entities (user-verified positions) ──────────────────────────────
#
# 28 entities: 4 corner roboports + 4 corner poles + 4 corner radars +
# 4 side-mid roboports + 12 edge poles. The layout is 4-fold symmetric around
# (61, 61), which is the "visual center" for 4×4 entities placed at integer
# coordinates (0.5 tile offset from rail-center (62, 62)).
SUPPORT_ENTITIES = [
    # Corner roboports (rotation around (61, 61))
    ("roboport",  10.0,  12.0),   # NW
    ("roboport", 110.0,  10.0),   # NE
    ("roboport", 112.0, 110.0),   # SE
    ("roboport",  12.0, 112.0),   # SW

    # Corner poles
    ("big-electric-pole",  13.0,  11.0),   # NW
    ("big-electric-pole", 111.0,  13.0),   # NE
    ("big-electric-pole", 109.0, 111.0),   # SE
    ("big-electric-pole",  11.0, 109.0),   # SW

    # Corner radars
    ("radar",  12.5,   8.5),   # NW
    ("radar", 113.5,  12.5),   # NE
    ("radar", 109.5, 113.5),   # SE
    ("radar",   8.5, 109.5),   # SW

    # Side-midpoint roboports
    ("roboport",  60.0,  14.0),   # top mid
    ("roboport", 112.0,  60.0),   # right mid
    ("roboport",  60.0, 112.0),   # bottom mid
    ("roboport",  14.0,  60.0),   # left mid

    # Edge poles — 3 per side
    ("big-electric-pole", 40.0,  11.0),
    ("big-electric-pole", 60.0,  11.0),
    ("big-electric-pole", 80.0,  11.0),
    ("big-electric-pole", 40.0, 109.0),
    ("big-electric-pole", 60.0, 109.0),
    ("big-electric-pole", 80.0, 109.0),
    ("big-electric-pole", 11.0,  40.0),
    ("big-electric-pole", 11.0,  60.0),
    ("big-electric-pole", 11.0,  80.0),
    ("big-electric-pole", 109.0, 40.0),
    ("big-electric-pole", 109.0, 60.0),
    ("big-electric-pole", 109.0, 80.0),
]


# ─── Rotation math ───────────────────────────────────────────────────────────

def rotate_position(x: float, y: float, steps: int) -> tuple:
    """Rotate (x, y) by `steps` * 90° CW around (CENTER, CENTER).
    steps=0 NE, 1 SE, 2 SW, 3 NW.
    """
    cx = cy = CENTER
    dx, dy = x - cx, y - cy
    for _ in range(steps % 4):
        dx, dy = -dy, dx
    return (cx + dx, cy + dy)


def rotate_direction(d: int, steps: int) -> int:
    return (d + 4 * steps) % 16


# ─── Straight-rail builders for perimeter ────────────────────────────────────

def add_straight_rail_row(ids, entities, y, direction=4):
    for x in range(RAIL_SPAN_LO, RAIL_SPAN_HI + 1, RAIL_SPAN_STEP):
        eid = ids.next()
        entities.append(Entity(
            entity_number=eid, name="straight-rail",
            position={"x": x, "y": y}, direction=direction,
        ))


def add_straight_rail_col(ids, entities, x, direction=0):
    for y in range(RAIL_SPAN_LO, RAIL_SPAN_HI + 1, RAIL_SPAN_STEP):
        eid = ids.next()
        entities.append(Entity(
            entity_number=eid, name="straight-rail",
            position={"x": x, "y": y}, direction=direction,
        ))


# ─── Top-level block assembly ────────────────────────────────────────────────

def build_block():
    ids = IDCounter()
    entities = []
    pole_ids = {}  # (x, y) → entity_id for big-electric-poles

    # Perimeter straight rails
    add_straight_rail_row(ids, entities, y=OUTER_OFFSET)
    add_straight_rail_row(ids, entities, y=INNER_OFFSET)
    add_straight_rail_row(ids, entities, y=BOTTOM_INNER)
    add_straight_rail_row(ids, entities, y=BOTTOM_OUTER)
    add_straight_rail_col(ids, entities, x=OUTER_OFFSET)
    add_straight_rail_col(ids, entities, x=INNER_OFFSET)
    add_straight_rail_col(ids, entities, x=BOTTOM_INNER)
    add_straight_rail_col(ids, entities, x=BOTTOM_OUTER)

    # 4 corner roundabouts via rotation (NE, SE, SW, NW)
    for steps in range(4):
        for (name, x, y, d) in NE_CORNER_TEMPLATE:
            nx, ny = rotate_position(x, y, steps)
            nd = rotate_direction(d, steps)
            eid = ids.next()
            entities.append(Entity(
                entity_number=eid, name=name,
                position={"x": nx, "y": ny}, direction=nd,
            ))

    # Hand-placed support entities (user-verified positions)
    for (name, x, y) in SUPPORT_ENTITIES:
        eid = ids.next()
        entities.append(Entity(
            entity_number=eid, name=name,
            position={"x": x, "y": y},
        ))
        if name == "big-electric-pole":
            pole_ids[(x, y)] = eid

    # Copper wires: chain 16 poles clockwise around the perimeter.
    # Max segment < 32 tiles (big-pole wire reach).
    wire_order = [
        (13.0,  11.0),  # NW corner
        (40.0,  11.0), (60.0,  11.0), (80.0,  11.0),  # top edge
        (111.0, 13.0),  # NE corner
        (109.0, 40.0), (109.0, 60.0), (109.0, 80.0),  # right edge
        (109.0, 111.0), # SE corner
        (80.0, 109.0), (60.0, 109.0), (40.0, 109.0),  # bottom edge
        (11.0, 109.0),  # SW corner
        (11.0,  80.0), (11.0,  60.0), (11.0,  40.0),  # left edge
    ]
    wires = []
    for i in range(len(wire_order)):
        a = pole_ids[wire_order[i]]
        b = pole_ids[wire_order[(i + 1) % len(wire_order)]]
        add_wire(wires, a, COPPER, b, COPPER)

    return entities, wires


def build_tiles(tile_name: str = "sand-3") -> list:
    """Generate a 128×128 tile square (x=0..127, y=0..127)."""
    return [
        {"position": {"x": x, "y": y}, "name": tile_name}
        for y in range(BLOCK_SIZE) for x in range(BLOCK_SIZE)
    ]


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--output", "-o", help="Write markdown w/ blueprint string")
    ap.add_argument("--json", help="Dump decoded JSON (debug)")
    ap.add_argument("--label", default="City Block (128×128)", help="Blueprint label")
    ap.add_argument("--tile", default="sand-3",
                    help="Background tile name (default: sand-3). Any valid tile works.")
    ap.add_argument("--no-tiles", action="store_true", help="Skip background tile fill")
    args = ap.parse_args()

    entities, wires = build_block()
    bp = build_blueprint(
        label=args.label,
        entities=entities,
        wires=wires,
        description="128×128 2-track RHD city block with 4 roundabout corners. No stations.",
        icons=[{"signal": {"name": "rail"}, "index": 1}],
    )

    if not args.no_tiles:
        bp["blueprint"]["tiles"] = build_tiles(args.tile)

    bp_string = encode_blueprint(bp)

    if args.json:
        with open(args.json, "w") as f:
            json.dump(bp, f, indent=2)
        print(f"wrote decoded JSON: {args.json}", file=sys.stderr)

    verify_blueprint(bp_string, args.label)

    if args.output:
        with open(args.output, "w") as f:
            f.write(f"# {args.label}\n\n")
            f.write(f"{len(entities)} entities.\n\n")
            f.write(f"```\n{bp_string}\n```\n")
        print(f"wrote blueprint: {args.output}", file=sys.stderr)
    else:
        print(bp_string)


if __name__ == "__main__":
    main()
