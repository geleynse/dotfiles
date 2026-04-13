#!/usr/bin/env python3
"""Decode a Factorio blueprint string and pretty-print the JSON.

Accepts either a blueprint string on the command line, a path to a file
containing one, or reads from stdin if no argument is given.

Examples:
  factorio-blueprint-decode.py 0eNrtW...
  factorio-blueprint-decode.py /tmp/correct.txt
  echo "0eNrtW..." | factorio-blueprint-decode.py
  factorio-blueprint-decode.py /tmp/correct.txt | jq '.blueprint.entities[0]'
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from factorio_blueprint import decode_blueprint


def load(source: str) -> str:
    """Return the blueprint string from a path, raw string, or stdin."""
    if source == "-":
        return sys.stdin.read().strip()
    if source.startswith("0") and len(source) > 20 and not os.path.exists(source):
        return source.strip()
    content = open(source).read()
    m = re.search(r"0eNr\S+", content)
    if not m:
        raise SystemExit(f"no blueprint string found in {source}")
    return m.group(0)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("source", nargs="?", default="-",
                    help="Blueprint string or file path (default: stdin)")
    ap.add_argument("--indent", type=int, default=2, help="JSON indent (default 2)")
    ap.add_argument("--compact", action="store_true", help="No indent, single line")
    args = ap.parse_args()

    bp_string = load(args.source)
    bp = decode_blueprint(bp_string)

    if args.compact:
        print(json.dumps(bp, separators=(",", ":")))
    else:
        print(json.dumps(bp, indent=args.indent))


if __name__ == "__main__":
    main()
