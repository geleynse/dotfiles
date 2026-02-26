#!/usr/bin/env python3
"""
czkawka-dedup.py — Process czkawka perceptual duplicate results and generate a deletion plan.

Reads the text output from `czkawka_cli image` and classifies duplicate groups into
confidence tiers, then generates a plan for which files to keep and which to delete.

Designed for deduplicating across two Google Photos takeout accounts:
  - account1-gpth-output/ (primary, preferred)
  - account2-gpth-output/ (secondary)

Tiers:
  1: Cross-account, identical hash, same filename         -> Auto-delete account2
  2: Same-account, identical hash, same base filename      -> Auto-keep largest
  3: Cross-account, identical hash, different filenames    -> Auto-keep largest, spot-check
  4: Same-account, identical hash, different filenames     -> Auto-keep largest, review
  5: Non-identical hash (Very High / High similarity)      -> Keep largest, visual review
  6: Mixed similarity levels in one group                  -> Manual review

Usage:
  python3 czkawka-dedup.py analyze /path/to/czkawka-similar.txt
  python3 czkawka-dedup.py plan /path/to/czkawka-similar.txt
  python3 czkawka-dedup.py review /path/to/czkawka-similar.txt
  python3 czkawka-dedup.py delete /path/to/dedup-plan.json --confirm [--trash-dir /path]
"""

import argparse
import json
import logging
import os
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import quote

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACCOUNT1_MARKER = "account1-gpth-output"
ACCOUNT2_MARKER = "account2-gpth-output"

# Similarity levels in czkawka output
SIMILARITY_IDENTICAL = "Original"
SIMILARITY_LEVELS = ["Original", "Very High", "High", "Medium", "Small"]

# Size unit multipliers (binary, matching czkawka output)
SIZE_UNITS = {
    "B": 1,
    "KiB": 1024,
    "MiB": 1024 ** 2,
    "GiB": 1024 ** 3,
    "TiB": 1024 ** 4,
}

# Regex for parsing an image entry line
# Example: "/path/to/file.jpg" - 1520x2032 - 848.74 KiB - Original
ENTRY_RE = re.compile(
    r'^"(.+?)"\s+-\s+(\d+)x(\d+)\s+-\s+([\d.]+)\s+(B|KiB|MiB|GiB|TiB)\s+-\s+(.+)$'
)

# Regex for parsing a group header line
# Example: Found 2 images which have similar friends
GROUP_HEADER_RE = re.compile(r"^Found (\d+) images? which have similar friends$")

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


class ImageEntry:
    """A single image entry from a czkawka duplicate group."""

    __slots__ = ("path", "width", "height", "size_bytes", "size_display", "similarity", "account")

    def __init__(self, path: str, width: int, height: int, size_bytes: int,
                 size_display: str, similarity: str):
        self.path = path
        self.width = width
        self.height = height
        self.size_bytes = size_bytes
        self.size_display = size_display
        self.similarity = similarity
        self.account = self._detect_account(path)

    @staticmethod
    def _detect_account(path: str) -> str:
        if ACCOUNT1_MARKER in path:
            return "account1"
        elif ACCOUNT2_MARKER in path:
            return "account2"
        return "unknown"

    @property
    def filename(self) -> str:
        return os.path.basename(self.path)

    @property
    def base_filename(self) -> str:
        """Filename with (1), (2), etc. suffixes removed for comparison."""
        name = self.filename
        stem, ext = os.path.splitext(name)
        # Remove trailing (1), (2), etc.
        cleaned = re.sub(r"\(\d+\)$", "", stem)
        return (cleaned + ext).lower()

    @property
    def has_numbered_suffix(self) -> bool:
        """Whether the filename has a (1), (2) etc. suffix."""
        stem = os.path.splitext(self.filename)[0]
        return bool(re.search(r"\(\d+\)$", stem))

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "width": self.width,
            "height": self.height,
            "size_bytes": self.size_bytes,
            "size_display": self.size_display,
            "similarity": self.similarity,
            "account": self.account,
            "filename": self.filename,
        }


class DuplicateGroup:
    """A group of perceptually similar/identical images."""

    def __init__(self, group_id: int, expected_count: int, entries: list):
        self.group_id = group_id
        self.expected_count = expected_count
        self.entries: list[ImageEntry] = entries
        self.tier: int = 0
        self.keep: list[ImageEntry] = []
        self.delete: list[ImageEntry] = []
        self.flags: list[str] = []

    @property
    def all_identical_hash(self) -> bool:
        """True if all entries have 'Original' similarity (identical perceptual hash)."""
        return all(e.similarity == SIMILARITY_IDENTICAL for e in self.entries)

    @property
    def is_cross_account(self) -> bool:
        accounts = {e.account for e in self.entries}
        return len(accounts) > 1

    @property
    def is_same_account(self) -> bool:
        return not self.is_cross_account

    @property
    def has_same_filenames(self) -> bool:
        """Check if all entries share the same base filename."""
        base_names = {e.base_filename for e in self.entries}
        return len(base_names) == 1

    @property
    def similarity_levels_present(self) -> set:
        return {e.similarity for e in self.entries}

    def to_dict(self) -> dict:
        return {
            "group_id": self.group_id,
            "tier": self.tier,
            "entry_count": len(self.entries),
            "flags": self.flags,
            "keep": [e.to_dict() for e in self.keep],
            "delete": [e.to_dict() for e in self.delete],
            "all_entries": [e.to_dict() for e in self.entries],
        }


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_size(value_str: str, unit: str) -> int:
    """Convert a size string like '848.74 KiB' to bytes."""
    multiplier = SIZE_UNITS.get(unit)
    if multiplier is None:
        raise ValueError(f"Unknown size unit: {unit}")
    return int(float(value_str) * multiplier)


def parse_czkawka_txt(filepath: str) -> list[DuplicateGroup]:
    """Parse czkawka-similar.txt and return a list of DuplicateGroups."""
    groups = []
    current_entries = []
    current_expected = 0
    group_id = 0
    in_header = True

    with open(filepath, "r", encoding="utf-8") as f:
        for line_num, raw_line in enumerate(f, 1):
            line = raw_line.rstrip("\n").rstrip("\r")

            # Skip blank lines (group separators)
            if not line.strip():
                # If we have accumulated entries, finalize the group
                if current_entries:
                    group_id += 1
                    groups.append(DuplicateGroup(group_id, current_expected, current_entries))
                    current_entries = []
                    current_expected = 0
                in_header = False
                continue

            # Check for group header
            header_match = GROUP_HEADER_RE.match(line)
            if header_match:
                # Finalize any previous group that wasn't terminated by blank line
                if current_entries:
                    group_id += 1
                    groups.append(DuplicateGroup(group_id, current_expected, current_entries))
                    current_entries = []
                current_expected = int(header_match.group(1))
                in_header = False
                continue

            # Skip the file header lines (first few lines before any group)
            if in_header:
                continue

            # Try to parse as an image entry
            entry_match = ENTRY_RE.match(line)
            if entry_match:
                path = entry_match.group(1)
                width = int(entry_match.group(2))
                height = int(entry_match.group(3))
                size_val = entry_match.group(4)
                size_unit = entry_match.group(5)
                similarity = entry_match.group(6).strip()
                size_bytes = parse_size(size_val, size_unit)
                size_display = f"{size_val} {size_unit}"

                entry = ImageEntry(path, width, height, size_bytes, size_display, similarity)
                current_entries.append(entry)
            else:
                # Unknown line — could be part of the preamble, just skip
                logging.debug("Skipping unrecognized line %d: %s", line_num, line[:100])

    # Finalize last group if file doesn't end with blank line
    if current_entries:
        group_id += 1
        groups.append(DuplicateGroup(group_id, current_expected, current_entries))

    return groups


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify_group(group: DuplicateGroup) -> None:
    """Classify a group into a tier and determine keep/delete decisions."""
    levels = group.similarity_levels_present

    # Check for mixed similarity levels (tier 6)
    non_original_levels = levels - {SIMILARITY_IDENTICAL}
    has_original = SIMILARITY_IDENTICAL in levels
    has_non_original = len(non_original_levels) > 0

    if group.all_identical_hash:
        # All entries are "Original" — identical perceptual hash
        if group.is_cross_account and group.has_same_filenames:
            group.tier = 1
        elif group.is_same_account and group.has_same_filenames:
            group.tier = 2
        elif group.is_cross_account and not group.has_same_filenames:
            group.tier = 3
            group.flags.append("spot-check")
        else:
            # Same account, different filenames, identical hash
            group.tier = 4
            group.flags.append("review")
    elif has_original and has_non_original and len(non_original_levels) > 1:
        # Mixed: Original + multiple different similarity levels
        group.tier = 6
        group.flags.append("manual-review")
    elif not has_original and len(non_original_levels) > 1:
        # Mixed non-identical levels without Original
        group.tier = 6
        group.flags.append("manual-review")
    else:
        # Non-identical hash: Very High, High, or single non-Original level
        # Also covers: Original + one non-Original level (common pattern)
        group.tier = 5
        group.flags.append("visual-review")

    # Decide keep/delete
    _decide_keep_delete(group)


def _decide_keep_delete(group: DuplicateGroup) -> None:
    """For a classified group, decide which files to keep and which to delete."""
    entries = list(group.entries)

    if group.tier == 1:
        # Cross-account, identical hash, same filename: keep account1, delete account2
        group.keep = [e for e in entries if e.account == "account1"]
        group.delete = [e for e in entries if e.account == "account2"]
        # If somehow no account1 entries, keep the first and delete the rest
        if not group.keep:
            group.keep = [entries[0]]
            group.delete = entries[1:]
    else:
        # Tiers 2-6: keep the largest file, with tiebreakers
        _keep_largest(group)


def _keep_largest(group: DuplicateGroup) -> None:
    """Keep the largest file. Tiebreak: prefer account1, then prefer no (N) suffix."""
    entries = list(group.entries)

    # Sort by: size descending, then account1 preferred, then no-suffix preferred
    def sort_key(e: ImageEntry):
        return (
            -e.size_bytes,                      # Largest first
            0 if e.account == "account1" else 1, # account1 preferred
            1 if e.has_numbered_suffix else 0,   # No suffix preferred
            e.path,                              # Stable sort by path
        )

    entries.sort(key=sort_key)
    group.keep = [entries[0]]
    group.delete = entries[1:]


def classify_all(groups: list[DuplicateGroup]) -> None:
    """Classify all groups."""
    for group in groups:
        classify_group(group)


# ---------------------------------------------------------------------------
# Analysis / Summary
# ---------------------------------------------------------------------------


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.2f} KiB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / 1024**2:.2f} MiB"
    else:
        return f"{size_bytes / 1024**3:.2f} GiB"


def generate_summary(groups: list[DuplicateGroup]) -> str:
    """Generate a human-readable summary of the classification."""
    tier_counts = defaultdict(int)
    tier_delete_counts = defaultdict(int)
    tier_delete_bytes = defaultdict(int)
    tier_descriptions = {
        1: "Cross-account, identical hash, same filename",
        2: "Same-account, identical hash, same base filename",
        3: "Cross-account, identical hash, different filenames",
        4: "Same-account, identical hash, different filenames",
        5: "Non-identical hash (perceptual similarity)",
        6: "Mixed similarity levels",
    }

    total_delete = 0
    total_delete_bytes = 0

    for g in groups:
        tier_counts[g.tier] += 1
        del_count = len(g.delete)
        del_bytes = sum(e.size_bytes for e in g.delete)
        tier_delete_counts[g.tier] += del_count
        tier_delete_bytes[g.tier] += del_bytes
        total_delete += del_count
        total_delete_bytes += del_bytes

    lines = [
        "=" * 72,
        "czkawka Deduplication Summary",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "=" * 72,
        "",
        f"Total groups: {len(groups)}",
        f"Total images: {sum(len(g.entries) for g in groups)}",
        f"Total files to delete: {total_delete}",
        f"Estimated space savings: {format_size(total_delete_bytes)}",
        "",
        "-" * 72,
        f"{'Tier':<6} {'Groups':>7} {'Deletes':>8} {'Savings':>12}  Description",
        "-" * 72,
    ]

    for tier in sorted(tier_counts.keys()):
        desc = tier_descriptions.get(tier, "Unknown")
        lines.append(
            f"  {tier:<4} {tier_counts[tier]:>7} {tier_delete_counts[tier]:>8} "
            f"{format_size(tier_delete_bytes[tier]):>12}  {desc}"
        )

    lines.append("-" * 72)
    lines.append(
        f"{'Total':>10} {sum(tier_counts.values()):>7} {total_delete:>8} "
        f"{format_size(total_delete_bytes):>12}"
    )
    lines.append("")

    # Breakdown of auto vs review
    auto_tiers = {1, 2}
    spot_check_tiers = {3}
    review_tiers = {4, 5, 6}

    auto_del = sum(tier_delete_counts[t] for t in auto_tiers)
    spot_del = sum(tier_delete_counts[t] for t in spot_check_tiers)
    review_del = sum(tier_delete_counts[t] for t in review_tiers)

    lines.append("Confidence breakdown:")
    lines.append(f"  Auto-delete (tier 1-2):         {auto_del:>6} files")
    lines.append(f"  Auto-delete, spot-check (tier 3): {spot_del:>4} files")
    lines.append(f"  Flagged for review (tier 4-6):  {review_del:>6} files")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Plan output
# ---------------------------------------------------------------------------


def write_plan(groups: list[DuplicateGroup], output_dir: str) -> None:
    """Write the full dedup plan as JSON and a simple delete list."""
    plan_path = os.path.join(output_dir, "dedup-plan.json")
    delete_list_path = os.path.join(output_dir, "dedup-delete-list.txt")
    summary_path = os.path.join(output_dir, "dedup-summary.txt")

    # Full plan JSON
    plan = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "total_groups": len(groups),
        "total_files": sum(len(g.entries) for g in groups),
        "total_deletes": sum(len(g.delete) for g in groups),
        "total_delete_bytes": sum(sum(e.size_bytes for e in g.delete) for g in groups),
        "tier_summary": {},
        "groups": [],
    }

    tier_data = defaultdict(lambda: {"groups": 0, "deletes": 0, "delete_bytes": 0})
    for g in groups:
        td = tier_data[g.tier]
        td["groups"] += 1
        td["deletes"] += len(g.delete)
        td["delete_bytes"] += sum(e.size_bytes for e in g.delete)
        plan["groups"].append(g.to_dict())

    plan["tier_summary"] = {str(k): v for k, v in sorted(tier_data.items())}

    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
    logging.info("Wrote plan: %s", plan_path)

    # Simple delete list
    with open(delete_list_path, "w", encoding="utf-8") as f:
        for g in groups:
            for e in g.delete:
                f.write(e.path + "\n")
    logging.info("Wrote delete list: %s", delete_list_path)

    # Summary
    summary = generate_summary(groups)
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary)
    logging.info("Wrote summary: %s", summary_path)

    print(summary)
    print(f"Plan written to:        {plan_path}")
    print(f"Delete list written to: {delete_list_path}")
    print(f"Summary written to:     {summary_path}")


# ---------------------------------------------------------------------------
# HTML review
# ---------------------------------------------------------------------------


def _html_escape(s: str) -> str:
    """Minimal HTML escaping without importing html module."""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def write_review_html(groups: list[DuplicateGroup], output_dir: str) -> None:
    """Generate an HTML review page for tier 4, 5, and 6 groups."""
    review_path = os.path.join(output_dir, "dedup-review.html")
    review_tiers = {4, 5, 6}
    review_groups = [g for g in groups if g.tier in review_tiers]

    if not review_groups:
        print("No groups require visual review (tiers 4-6).")
        return

    parts = [
        "<!DOCTYPE html>",
        "<html><head>",
        "<meta charset='utf-8'>",
        "<title>czkawka Dedup Review</title>",
        "<style>",
        "body { font-family: sans-serif; margin: 20px; background: #1a1a1a; color: #e0e0e0; }",
        "h1, h2 { color: #fff; }",
        ".tier-section { margin-bottom: 40px; }",
        ".group { border: 1px solid #444; margin: 15px 0; padding: 15px; "
        "border-radius: 8px; background: #2a2a2a; }",
        ".group-header { font-weight: bold; margin-bottom: 10px; color: #aaa; }",
        ".entries { display: flex; flex-wrap: wrap; gap: 15px; }",
        ".entry { text-align: center; max-width: 320px; }",
        ".entry img { max-width: 300px; max-height: 300px; border: 2px solid #555; "
        "border-radius: 4px; }",
        ".entry.keep img { border-color: #4caf50; }",
        ".entry.delete img { border-color: #f44336; opacity: 0.7; }",
        ".entry .label { font-size: 12px; margin-top: 4px; word-break: break-all; }",
        ".entry .meta { font-size: 11px; color: #888; }",
        ".badge { display: inline-block; padding: 2px 6px; border-radius: 3px; "
        "font-size: 11px; font-weight: bold; }",
        ".badge.keep { background: #4caf50; color: #fff; }",
        ".badge.delete { background: #f44336; color: #fff; }",
        ".badge.tier { background: #ff9800; color: #000; }",
        ".tier-description { color: #aaa; margin-bottom: 10px; }",
        "summary { cursor: pointer; font-size: 16px; font-weight: bold; padding: 8px; }",
        "</style>",
        "</head><body>",
        "<h1>czkawka Dedup Review</h1>",
        f"<p>Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</p>",
        f"<p>Groups requiring review: {len(review_groups)}</p>",
    ]

    tier_desc = {
        4: "Same-account, identical hash, different filenames",
        5: "Non-identical hash (perceptual similarity)",
        6: "Mixed similarity levels",
    }

    for tier in sorted(review_tiers):
        tier_groups = [g for g in review_groups if g.tier == tier]
        if not tier_groups:
            continue

        parts.append(f'<div class="tier-section">')
        parts.append(f"<h2>Tier {tier}: {_html_escape(tier_desc.get(tier, ''))}</h2>")
        parts.append(f'<p class="tier-description">{len(tier_groups)} groups</p>')

        for g in tier_groups:
            parts.append(f'<details class="group"><summary>')
            parts.append(
                f'<span class="badge tier">Tier {g.tier}</span> '
                f"Group {g.group_id} &mdash; {len(g.entries)} images"
            )
            if g.flags:
                parts.append(f" [{', '.join(g.flags)}]")
            parts.append("</summary>")
            parts.append('<div class="entries">')

            for e in g.entries:
                is_keep = e in g.keep
                css_class = "keep" if is_keep else "delete"
                badge = "KEEP" if is_keep else "DELETE"
                badge_class = "keep" if is_keep else "delete"

                # Percent-encode the path for use in file:// URL (preserve /)
                url_path = quote(e.path, safe="/")
                parts.append(f'<div class="entry {css_class}">')
                parts.append(f'<img src="file://{url_path}" loading="lazy">')
                parts.append(
                    f'<div class="label">'
                    f'<span class="badge {badge_class}">{badge}</span> '
                    f"{_html_escape(e.filename)}</div>"
                )
                parts.append(
                    f'<div class="meta">'
                    f"{e.size_display} | {e.width}x{e.height} | "
                    f"{_html_escape(e.similarity)} | {e.account}</div>"
                )
                parts.append("</div>")

            parts.append("</div></details>")
        parts.append("</div>")

    parts.append("</body></html>")

    with open(review_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    logging.info("Wrote review HTML: %s", review_path)
    print(f"Review HTML written to: {review_path}")
    print(f"  ({len(review_groups)} groups for visual inspection)")


# ---------------------------------------------------------------------------
# Delete (move to trash)
# ---------------------------------------------------------------------------


def execute_delete(plan_path: str, trash_dir: str, confirm: bool) -> None:
    """Read a plan JSON and move files to trash directory."""
    if not confirm:
        print("ERROR: --confirm flag required for delete mode.", file=sys.stderr)
        print("  This will move files to the trash directory, not permanently delete them.")
        print(f"  Run with: delete {plan_path} --confirm")
        sys.exit(1)

    if not os.path.isfile(plan_path):
        print(f"ERROR: Plan file not found: {plan_path}", file=sys.stderr)
        sys.exit(1)

    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    total = plan.get("total_deletes", 0)
    print(f"Plan has {total} files to delete (move to trash).")
    print(f"Trash directory: {trash_dir}")

    os.makedirs(trash_dir, exist_ok=True)

    moved = 0
    skipped = 0
    errors = 0
    log_path = os.path.join(trash_dir, "delete-log.txt")

    with open(log_path, "a", encoding="utf-8") as log_f:
        log_f.write(f"\n--- Delete run: {datetime.now(timezone.utc).isoformat()} ---\n")

        for group_data in plan.get("groups", []):
            for entry in group_data.get("delete", []):
                src = entry["path"]

                # Safety: only allow absolute paths and reject path traversal
                real_src = os.path.realpath(src)
                if not os.path.isabs(src) or ".." in src.split(os.sep):
                    logging.warning("Rejecting suspicious path: %s", src)
                    log_f.write(f"SKIP (suspicious path): {src}\n")
                    skipped += 1
                    continue

                if not os.path.isfile(real_src):
                    logging.warning("File not found, skipping: %s", src)
                    log_f.write(f"SKIP (not found): {src}\n")
                    skipped += 1
                    continue

                # Create a unique destination path preserving some structure
                # Use the relative path from the common root to avoid collisions
                # Strip the leading path up to and including google-takeout/
                rel = src
                marker_idx = src.find("google-takeout/")
                if marker_idx >= 0:
                    rel = src[marker_idx + len("google-takeout/"):]

                dest = os.path.join(trash_dir, rel)
                dest_dir = os.path.dirname(dest)

                try:
                    os.makedirs(dest_dir, exist_ok=True)
                    shutil.move(real_src, dest)
                    log_f.write(f"MOVED: {src} -> {dest}\n")
                    moved += 1
                except OSError as e:
                    logging.error("Failed to move %s: %s", src, e)
                    log_f.write(f"ERROR: {src} -> {e}\n")
                    errors += 1

                if (moved + skipped + errors) % 500 == 0:
                    print(f"  Progress: {moved} moved, {skipped} skipped, {errors} errors")

    print(f"\nDone. Moved: {moved}, Skipped: {skipped}, Errors: {errors}")
    print(f"Log: {log_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def cmd_analyze(args: argparse.Namespace) -> None:
    """Analyze mode: print summary statistics."""
    groups = parse_czkawka_txt(args.input)
    classify_all(groups)
    print(generate_summary(groups))


def cmd_plan(args: argparse.Namespace) -> None:
    """Plan mode: write detailed plan files."""
    groups = parse_czkawka_txt(args.input)
    classify_all(groups)
    output_dir = os.path.dirname(os.path.abspath(args.input))
    write_plan(groups, output_dir)


def cmd_review(args: argparse.Namespace) -> None:
    """Review mode: generate HTML review page."""
    groups = parse_czkawka_txt(args.input)
    classify_all(groups)
    output_dir = os.path.dirname(os.path.abspath(args.input))
    write_review_html(groups, output_dir)


def cmd_delete(args: argparse.Namespace) -> None:
    """Delete mode: move files to trash."""
    plan_path = args.input
    trash_dir = args.trash_dir
    if not trash_dir:
        trash_dir = os.path.join(os.path.dirname(os.path.abspath(plan_path)), "czkawka-trash")
    execute_delete(plan_path, trash_dir, args.confirm)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Process czkawka perceptual duplicate results and generate a deletion plan.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose/debug logging"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # analyze
    p_analyze = subparsers.add_parser("analyze", help="Print summary statistics by tier")
    p_analyze.add_argument("input", help="Path to czkawka-similar.txt")
    p_analyze.set_defaults(func=cmd_analyze)

    # plan
    p_plan = subparsers.add_parser(
        "plan", help="Write a detailed JSON plan and delete list"
    )
    p_plan.add_argument("input", help="Path to czkawka-similar.txt")
    p_plan.set_defaults(func=cmd_plan)

    # review
    p_review = subparsers.add_parser(
        "review", help="Generate HTML review page for uncertain groups"
    )
    p_review.add_argument("input", help="Path to czkawka-similar.txt")
    p_review.set_defaults(func=cmd_review)

    # delete
    p_delete = subparsers.add_parser(
        "delete", help="Move files to trash based on a plan JSON"
    )
    p_delete.add_argument("input", help="Path to dedup-plan.json")
    p_delete.add_argument(
        "--confirm", action="store_true",
        help="Required flag to actually move files (safety check)"
    )
    p_delete.add_argument(
        "--trash-dir", default=None,
        help="Directory to move deleted files to (default: ./czkawka-trash/ next to plan)"
    )
    p_delete.set_defaults(func=cmd_delete)

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    args.func(args)


if __name__ == "__main__":
    main()
