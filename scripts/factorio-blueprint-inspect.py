#!/usr/bin/env python3
"""Inspect a Factorio blueprint by grouping entities into rows.

Loads a blueprint (string or file), normalizes positions relative to an anchor
entity, then prints one line per y-coordinate with abbreviated entity names.
Also prints a summary (entity count, wire count, bounding box, entity types).

Examples:
  factorio-blueprint-inspect.py 0eNrtW...
  factorio-blueprint-inspect.py /tmp/bp.txt
  factorio-blueprint-inspect.py /tmp/bp.txt --anchor logistic-train-stop
  factorio-blueprint-inspect.py /tmp/bp.txt --json  # full JSON dump
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from factorio_blueprint import decode_blueprint


# Short names for common entities (extend as needed)
ABBREV = {
    "medium-electric-pole": "P",
    "big-electric-pole": "Pbig",
    "small-electric-pole": "p",
    "substation": "SUB",
    "steel-chest": "C",
    "iron-chest": "Ci",
    "wooden-chest": "Cw",
    "bob-red-inserter": "B",
    "inserter": "I",
    "fast-inserter": "I+",
    "long-handed-inserter": "Il",
    "stack-inserter": "Is",
    "logistic-train-stop": "STOP",
    "logistic-train-stop-input": "LAMP",
    "logistic-train-stop-output": "OUT_CC",
    "ltn-combinator": "LTN",
    "arithmetic-combinator": "A",
    "decider-combinator": "D",
    "constant-combinator": "CC",
    "selector-combinator": "SEL",
    "straight-rail": "R",
    "curved-rail-a": "R*",
    "curved-rail-b": "R*b",
    "train-stop": "TS",
    "rail-signal": "rs",
    "rail-chain-signal": "rcs",
    "transport-belt": "=",
    "fast-transport-belt": "=+",
    "express-transport-belt": "=*",
    "underground-belt": "U",
    "splitter": "S",
    "assembling-machine-1": "AM1",
    "assembling-machine-2": "AM2",
    "assembling-machine-3": "AM3",
    "stone-furnace": "F",
    "steel-furnace": "Fs",
    "electric-furnace": "Fe",
    "pipe": "|",
    "pipe-to-ground": "|_",
    "pump": "PUMP",
    "storage-tank": "TANK",
    "lamp": "L",
}


def load(source: str) -> dict:
    if source.startswith("0") and len(source) > 20 and not os.path.exists(source):
        return decode_blueprint(source.strip())
    content = open(source).read()
    m = re.search(r"0eNr\S+", content)
    if not m:
        raise SystemExit(f"no blueprint string found in {source}")
    return decode_blueprint(m.group(0))


def pick_anchor(entities: list, requested: str = None):
    if requested:
        for e in entities:
            if e["name"] == requested:
                return e
        raise SystemExit(f"no entity with name={requested}")
    counts = Counter(e["name"] for e in entities)
    for e in entities:
        if counts[e["name"]] == 1:
            return e
    return entities[0]


def short(name: str) -> str:
    return ABBREV.get(name, name)


def inspect_blueprint(bp: dict, anchor_name: str = None, show_json: bool = False):
    if show_json:
        print(json.dumps(bp, indent=2))
        return

    if "blueprint_book" in bp:
        bps = bp["blueprint_book"].get("blueprints", [])
        print(f"Blueprint book: {bp['blueprint_book'].get('label', '(no label)')!r}")
        print(f"  {len(bps)} entries")
        for i, entry in enumerate(bps):
            if "blueprint" in entry:
                inner = entry["blueprint"]
                ents = len(inner.get("entities", []))
                wires = len(inner.get("wires", []))
                print(f"  [{i}] {inner.get('label', '?')!r} — {ents} entities, {wires} wires")
            elif "blueprint_book" in entry:
                inner = entry["blueprint_book"]
                print(f"  [{i}] (nested book) {inner.get('label', '?')!r}")
        return

    inner = bp["blueprint"]
    entities = inner.get("entities", [])
    wires = inner.get("wires", [])

    anchor = pick_anchor(entities, anchor_name)
    ax, ay = anchor["position"]["x"], anchor["position"]["y"]

    print(f"Blueprint: {inner.get('label', '(no label)')!r}")
    print(f"  {len(entities)} entities, {len(wires)} wires")
    print(f"  anchor: {anchor['name']} @ ({ax}, {ay})")

    xs = [e["position"]["x"] - ax for e in entities]
    ys = [e["position"]["y"] - ay for e in entities]
    print(f"  bbox (relative): x=[{min(xs):.1f}, {max(xs):.1f}]  y=[{min(ys):.1f}, {max(ys):.1f}]")

    types = Counter(e["name"] for e in entities)
    print(f"  types: {dict(types.most_common())}")
    print()

    rows = defaultdict(list)
    for e in entities:
        x = round(e["position"]["x"] - ax, 2)
        y = round(e["position"]["y"] - ay, 2)
        rows[y].append((x, e["name"], e.get("direction", 0)))

    for y in sorted(rows):
        items = sorted(rows[y])
        label = f"y={y:>6.1f}"
        parts = [f"{short(n)}@{x}" for x, n, _d in items]
        print(f"{label}: {' '.join(parts)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("source", help="Blueprint string or path to file containing one")
    ap.add_argument("--anchor", help="Entity name to use as origin")
    ap.add_argument("--json", action="store_true", help="Dump full decoded JSON")
    args = ap.parse_args()

    bp = load(args.source)
    inspect_blueprint(bp, args.anchor, args.json)


if __name__ == "__main__":
    main()
