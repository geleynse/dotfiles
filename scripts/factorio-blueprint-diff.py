#!/usr/bin/env python3
"""Diff two Factorio blueprint strings (or files containing them).

Normalizes entity positions relative to an anchor entity (default: first
instance of the first unique entity type, e.g. a train stop), then reports:
  - entity position / direction diffs
  - wire-topology diffs (wire endpoints identified by (name, x, y, dir))

Accepts either a blueprint string directly or a path to a file containing one
(reads the first token matching `^0eNr\\S+`).

Examples:
  factorio-blueprint-diff.py 0eNrtW... 0eNrtW...
  factorio-blueprint-diff.py /tmp/before.txt /tmp/after.txt
  factorio-blueprint-diff.py a.txt b.txt --anchor logistic-train-stop
  factorio-blueprint-diff.py a.txt b.txt --summary    # counts only
"""

import argparse
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from factorio_blueprint import decode_blueprint


def load(source: str) -> dict:
    """Accept either a raw blueprint string or a path to a file containing one."""
    if source.startswith("0") and len(source) > 20 and not os.path.exists(source):
        return decode_blueprint(source.strip())
    content = open(source).read()
    m = re.search(r"0eNr\S+", content)
    if not m:
        raise SystemExit(f"no blueprint string found in {source}")
    return decode_blueprint(m.group(0))


def unique_names(entities: list) -> set:
    """Return names that appear exactly once."""
    counts = Counter(e["name"] for e in entities)
    return {n for n, c in counts.items() if c == 1}


def choose_shared_anchor(ents_a: list, ents_b: list) -> str:
    """Pick an anchor name that's unique in both blueprints. Prefers common
    stable landmarks (stops/hubs), else alphabetical first in the intersection."""
    shared = unique_names(ents_a) & unique_names(ents_b)
    if not shared:
        return None
    preferred = [
        "logistic-train-stop", "train-stop", "roboport",
        "rocket-silo", "nuclear-reactor",
    ]
    for p in preferred:
        if p in shared:
            return p
    return sorted(shared)[0]


def normalize(bp: dict, anchor_name: str):
    """Return (anchor_used, by_num, wireset) with positions relative to anchor."""
    entities = bp["blueprint"]["entities"]
    anchor = None
    if anchor_name:
        for e in entities:
            if e["name"] == anchor_name:
                anchor = e
                break
    if anchor is None:
        # fallback: first unique-name entity in iteration order
        counts = Counter(e["name"] for e in entities)
        for e in entities:
            if counts[e["name"]] == 1:
                anchor = e
                break
        if anchor is None:
            anchor = entities[0]
    ax, ay = anchor["position"]["x"], anchor["position"]["y"]

    by_num = {}
    for e in entities:
        x = round(e["position"]["x"] - ax, 2)
        y = round(e["position"]["y"] - ay, 2)
        by_num[e["entity_number"]] = (e["name"], x, y, e.get("direction", 0))

    wireset = set()
    for w in bp["blueprint"].get("wires", []):
        a, ac, b, bc = w
        if a not in by_num or b not in by_num:
            continue
        k1 = (by_num[a], ac, by_num[b], bc)
        k2 = (by_num[b], bc, by_num[a], ac)
        wireset.add(min(k1, k2))

    return anchor["name"], by_num, wireset





def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("a", help="First blueprint (string or file)")
    ap.add_argument("b", help="Second blueprint (string or file)")
    ap.add_argument("--anchor", help="Entity name to use as origin (default: first unique-name entity)")
    ap.add_argument("--summary", action="store_true", help="Only counts, no per-diff lines")
    ap.add_argument("--max", type=int, default=50, help="Max lines per diff section (default 50)")
    args = ap.parse_args()

    bp_a = load(args.a)
    bp_b = load(args.b)

    if "blueprint" not in bp_a or "blueprint" not in bp_b:
        raise SystemExit("both inputs must be single blueprints (not books)")

    anchor = args.anchor or choose_shared_anchor(
        bp_a["blueprint"]["entities"], bp_b["blueprint"]["entities"]
    )
    anchor_a, by_a, wires_a = normalize(bp_a, anchor)
    anchor_b, by_b, wires_b = normalize(bp_b, anchor)

    ents_a = set(by_a.values())
    ents_b = set(by_b.values())

    print(f"A: {len(by_a)} entities, {len(wires_a)} wires (anchor={anchor_a!r})")
    print(f"B: {len(by_b)} entities, {len(wires_b)} wires (anchor={anchor_b!r})")

    ent_only_a = ents_a - ents_b
    ent_only_b = ents_b - ents_a
    wire_only_a = wires_a - wires_b
    wire_only_b = wires_b - wires_a

    print(f"\nEntity diffs: A_only={len(ent_only_a)}  B_only={len(ent_only_b)}")
    if not args.summary:
        for e in sorted(ent_only_a)[: args.max]:
            print(f"  A: {e}")
        for e in sorted(ent_only_b)[: args.max]:
            print(f"  B: {e}")

    print(f"\nWire diffs: A_only={len(wire_only_a)}  B_only={len(wire_only_b)}")
    if not args.summary:
        for w in sorted(wire_only_a)[: args.max]:
            print(f"  A: {w}")
        for w in sorted(wire_only_b)[: args.max]:
            print(f"  B: {w}")

    if ent_only_a or ent_only_b or wire_only_a or wire_only_b:
        sys.exit(1)


if __name__ == "__main__":
    main()
