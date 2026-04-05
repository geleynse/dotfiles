#!/usr/bin/env python3
"""Dendron → Obsidian migration script.

Converts a Dendron vault (flat dot-notation files) into an Obsidian-friendly
folder hierarchy with converted frontmatter and updated wikilinks.

Usage:
    # Dry run (no changes):
    python3 dendron-to-obsidian.py --dry-run

    # Execute migration:
    python3 dendron-to-obsidian.py

    # Custom paths:
    python3 dendron-to-obsidian.py --vault ~/Dendron/vault.personal --output ~/Obsidian/vault

The script:
1. Converts dot-notation filenames → folder hierarchy
2. Converts Dendron frontmatter → Obsidian Properties
3. Updates wikilinks to new paths
4. Generates a link mapping for verification
5. Leaves task files in a flat tasks/ folder for CLI compatibility

All operations are logged. Original vault is NOT modified unless --in-place is used.
"""

import argparse
import datetime
import json
import pathlib
import re
import shutil
import sys
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_VAULT = pathlib.Path.home() / "Dendron" / "vault.personal"
DEFAULT_OUTPUT = pathlib.Path.home() / "Obsidian" / "vault"

# Files to skip entirely (Dendron-only, no Obsidian equivalent)
SKIP_FILES = {
    "root.schema.yml",
    "daily.schema.yml",
}

# Files to copy as-is (no rename, no frontmatter conversion)
COPY_AS_IS = {
    "README.md",
    "CLAUDE.md",
}

# Hierarchy → tag mapping
HIERARCHY_TAGS = {
    "daily": "daily",
    "projects": "projects",
    "infra": "infra",
    "electronics": "electronics",
    "legal": "legal",
    "tasks": "tasks",
    "3dprinting": "3dprinting",
    "brewing": "brewing",
    "linux": "linux",
    "spacemolt": "spacemolt",
    "clover": "clover",
    "at": "location",
    "laptop": "laptop",
    "tools": "tools",
    "chrome": "chrome",
}

# Journal date pattern
JOURNAL_RE = re.compile(r"^daily\.journal\.(\d{4})\.(\d{2})\.(\d{2})$")

# Project log date pattern (with optional suffix like -extended or d)
PROJECT_LOG_RE = re.compile(r"^projects\.log\.(\d{4})\.(\d{2})\.(\d{2})(.*)$")

# Wikilink pattern
WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(\|[^\]]*)?\]\]")


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown content.

    Returns (frontmatter_dict, body) where body excludes the --- delimiters.
    If no frontmatter, returns ({}, content).
    """
    if not content.startswith("---"):
        return {}, content

    # Find closing ---
    end = content.find("\n---", 3)
    if end == -1:
        return {}, content

    fm_text = content[4:end].strip()  # skip opening ---\n
    body = content[end + 4:]  # skip closing ---\n

    # Simple YAML parser (our frontmatter is always simple key: value)
    fm = {}
    for line in fm_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        colon = line.find(":")
        if colon == -1:
            continue
        key = line[:colon].strip()
        value = line[colon + 1:].strip()
        # Strip quotes
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1]
        fm[key] = value

    return fm, body


def epoch_to_date(value: str) -> Optional[str]:
    """Convert epoch ms or ISO string to YYYY-MM-DD."""
    if not value:
        return None

    # Already ISO date
    if re.match(r"^\d{4}-\d{2}-\d{2}", value):
        return value[:10]

    # Epoch milliseconds (13 digits)
    try:
        ts = int(value)
        if ts > 1e12:  # milliseconds
            ts = ts / 1000
        if ts > 0 and ts < 2e10:  # reasonable range
            return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except (ValueError, OSError):
        pass

    return None


def convert_frontmatter(fm: dict, hierarchy: str) -> str:
    """Convert Dendron frontmatter to Obsidian Properties format."""
    props = {}

    # Title
    if fm.get("title"):
        props["title"] = fm["title"]
        # Add as alias for search
        props["aliases"] = [fm["title"]]

    # Description
    if fm.get("desc") and fm["desc"] not in ("", "''", '""'):
        props["description"] = fm["desc"]

    # Dates
    created = epoch_to_date(fm.get("created", ""))
    updated = epoch_to_date(fm.get("updated", ""))
    if created:
        props["created"] = created
    if updated:
        props["updated"] = updated

    # Tags from hierarchy
    top_level = hierarchy.split(".")[0] if hierarchy else ""
    if top_level in HIERARCHY_TAGS:
        props["tags"] = [HIERARCHY_TAGS[top_level]]

    # Build YAML
    lines = ["---"]
    for key, value in props.items():
        if isinstance(value, list):
            items = ", ".join(f'"{v}"' if isinstance(v, str) else str(v) for v in value)
            lines.append(f"{key}: [{items}]")
        elif isinstance(value, str) and any(c in value for c in ":#[]{}|>&*!%@`,"):
            lines.append(f'{key}: "{value}"')
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Path conversion
# ---------------------------------------------------------------------------

def dendron_to_obsidian_path(stem: str) -> pathlib.PurePosixPath:
    """Convert a Dendron dot-notation stem to an Obsidian folder path.

    Examples:
        daily.journal.2026.03.27 → daily/journal/2026-03-27
        projects.log.2026.03.27 → projects/log/2026-03-27
        projects.spacemolt.client-comparison → projects/spacemolt/client-comparison
        infra.home.network → infra/home/network
        tasks.backlog → tasks/backlog
        tasks.projects.spacemolt → tasks/projects-spacemolt
    """
    # Special: journal entries → compact date
    m = JOURNAL_RE.match(stem)
    if m:
        y, mo, d = m.groups()
        return pathlib.PurePosixPath(f"daily/journal/{y}-{mo}-{d}")

    # Special: project log entries → compact date (with optional suffix)
    m = PROJECT_LOG_RE.match(stem)
    if m:
        y, mo, d, suffix = m.groups()
        # suffix is "" for normal, "-extended" or "d" for variants
        return pathlib.PurePosixPath(f"projects/log/{y}-{mo}-{d}{suffix}")

    # Special: task project files → flatten to tasks/
    if stem.startswith("tasks.projects."):
        project_name = stem.replace("tasks.projects.", "").replace(".", "-")
        return pathlib.PurePosixPath(f"tasks/projects-{project_name}")

    # Special: task files → tasks/ folder
    if stem.startswith("tasks."):
        task_name = stem.replace("tasks.", "")
        return pathlib.PurePosixPath(f"tasks/{task_name}")

    # Special: template files → templates/
    if stem.startswith("templates."):
        template_name = stem.replace("templates.", "").replace(".", "-")
        return pathlib.PurePosixPath(f"templates/{template_name}")

    # General: dots → folder separators
    parts = stem.split(".")
    return pathlib.PurePosixPath(*parts)


# ---------------------------------------------------------------------------
# Wikilink update
# ---------------------------------------------------------------------------

def build_link_map(mappings: dict[str, pathlib.PurePosixPath]) -> dict[str, str]:
    """Build a map from old Dendron link targets to new Obsidian targets.

    In Obsidian, wikilinks resolve by filename (not path), so we just need
    the final filename. If there are collisions, use the full relative path.
    """
    # Map old dendron stem → new obsidian stem (filename only)
    link_map = {}
    seen_names = {}

    for old_stem, new_path in mappings.items():
        new_name = new_path.name
        if new_name in seen_names:
            # Collision — use full path for both
            collision_old = seen_names[new_name]
            link_map[collision_old] = str(mappings[collision_old])
            link_map[old_stem] = str(new_path)
        else:
            seen_names[new_name] = old_stem
            link_map[old_stem] = new_name

    return link_map


def update_wikilinks(content: str, link_map: dict[str, str]) -> str:
    """Update wikilinks in content using the link map."""
    def replace_link(match):
        target = match.group(1)
        alias = match.group(2) or ""
        if target in link_map:
            new_target = link_map[target]
            return f"[[{new_target}{alias}]]"
        return match.group(0)

    return WIKILINK_RE.sub(replace_link, content)


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

def migrate(vault_dir: pathlib.Path, output_dir: pathlib.Path,
            dry_run: bool = False) -> dict:
    """Run the full migration.

    Returns a summary dict with counts and any warnings.
    """
    if not vault_dir.exists():
        print(f"❌ Vault not found: {vault_dir}")
        sys.exit(1)

    md_files = sorted(vault_dir.glob("*.md"))
    yml_files = sorted(vault_dir.glob("*.yml"))

    # Build mapping: old stem → new relative path
    mappings: dict[str, pathlib.PurePosixPath] = {}
    skipped = []
    copy_direct = []

    for f in md_files:
        if f.name in SKIP_FILES:
            skipped.append(f.name)
            continue
        if f.name in COPY_AS_IS:
            copy_direct.append(f.name)
            continue
        # Skip lock files
        if f.name.endswith(".lock"):
            skipped.append(f.name)
            continue
        stem = f.stem
        mappings[stem] = dendron_to_obsidian_path(stem)

    for f in yml_files:
        skipped.append(f.name)

    # Build link map for wikilink updates
    link_map = build_link_map(mappings)

    # Report
    print(f"\n📂 Source: {vault_dir}")
    print(f"📂 Output: {output_dir}")
    print(f"📄 Files to migrate: {len(mappings)}")
    print(f"📋 Files to copy as-is: {len(copy_direct)}")
    print(f"⏭️  Files to skip: {len(skipped)}")
    print(f"🔗 Wikilinks to update: {len(link_map)} unique targets")

    if dry_run:
        print(f"\n{'='*60}")
        print("DRY RUN — showing planned changes:\n")

    # Preview/execute
    warnings = []
    migrated = 0
    folders_created = set()

    for old_stem, new_path in sorted(mappings.items()):
        old_file = vault_dir / f"{old_stem}.md"
        new_file = output_dir / f"{new_path}.md"

        content = old_file.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(content)

        # Convert frontmatter
        new_fm = convert_frontmatter(fm, old_stem)

        # Update wikilinks in body
        new_body = update_wikilinks(body, link_map)

        # Reconstruct
        new_content = new_fm + "\n" + new_body

        if dry_run:
            folder = str(new_path.parent)
            if folder not in folders_created and folder != ".":
                print(f"  📁 mkdir {folder}/")
                folders_created.add(folder)
            moved = "→" if str(new_path) != old_stem else "="
            print(f"  {moved} {old_stem}.md → {new_path}.md")

            # Show frontmatter change for first few
            if migrated < 3 and fm:
                print(f"    FM: id={fm.get('id', '?')[:30]}, "
                      f"title={fm.get('title', '?')[:40]}")
                created = epoch_to_date(fm.get("created", ""))
                print(f"    → created={created}, "
                      f"tags={HIERARCHY_TAGS.get(old_stem.split('.')[0], 'none')}")
        else:
            # Create directories
            new_file.parent.mkdir(parents=True, exist_ok=True)
            new_file.write_text(new_content, encoding="utf-8")

        migrated += 1

    # Copy as-is files
    for fname in copy_direct:
        src = vault_dir / fname
        dst = output_dir / fname
        if dry_run:
            print(f"  = {fname} (copy as-is)")
        else:
            shutil.copy2(src, dst)

    # Create .obsidian directory with minimal config
    if not dry_run:
        obsidian_dir = output_dir / ".obsidian"
        obsidian_dir.mkdir(parents=True, exist_ok=True)

        # Enable community plugins
        (obsidian_dir / "community-plugins.json").write_text(
            json.dumps(["dataview", "calendar", "obsidian-git", "obsidian-linter"]),
            encoding="utf-8"
        )

        # Daily notes config
        daily_notes_config = {
            "format": "daily/journal/YYYY-MM-DD",
            "folder": "",
            "template": "templates/daily-journal",
            "autorun": False,
        }
        app_config = {
            "showLineNumber": True,
            "strictLineBreaks": True,
            "useTab": False,
            "tabSize": 2,
        }
        (obsidian_dir / "daily-notes.json").write_text(
            json.dumps(daily_notes_config, indent=2), encoding="utf-8"
        )
        (obsidian_dir / "app.json").write_text(
            json.dumps(app_config, indent=2), encoding="utf-8"
        )

    # Create daily note template
    template_dir = output_dir / "templates"
    template_content = """---
title: "Daily Journal - {{date}}"
aliases: ["{{date}}"]
tags: [daily]
created: "{{date}}"
---

## Today
-

### Health
- Exercise:
- Tics:
- Medicine changes:

### Tasks
- [ ]

### Notes

"""
    if not dry_run:
        template_dir.mkdir(parents=True, exist_ok=True)
        (template_dir / "daily-journal.md").write_text(template_content, encoding="utf-8")

    # Save link map for verification
    if not dry_run:
        map_file = output_dir / ".migration-link-map.json"
        map_file.write_text(json.dumps(link_map, indent=2), encoding="utf-8")

        # Save reverse map (new → old) for debugging
        reverse_map = {v: k for k, v in link_map.items()}
        (output_dir / ".migration-reverse-map.json").write_text(
            json.dumps(reverse_map, indent=2), encoding="utf-8"
        )

    print(f"\n✅ {'Would migrate' if dry_run else 'Migrated'}: {migrated} files")
    print(f"📋 {'Would copy' if dry_run else 'Copied'}: {len(copy_direct)} files")
    print(f"⏭️  Skipped: {len(skipped)} files ({', '.join(skipped[:5])}{'...' if len(skipped) > 5 else ''})")

    if not dry_run:
        print(f"\n📁 Output: {output_dir}")
        print(f"📄 Link map: {output_dir / '.migration-link-map.json'}")
        print(f"\nNext steps:")
        print(f"  1. Open {output_dir} as an Obsidian vault")
        print(f"  2. Install recommended plugins")
        print(f"  3. Verify wikilinks in graph view")
        print(f"  4. Run the tasks CLI path update")

    return {
        "migrated": migrated,
        "copied": len(copy_direct),
        "skipped": len(skipped),
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Migrate Dendron vault to Obsidian folder structure"
    )
    parser.add_argument(
        "--vault", type=pathlib.Path, default=DEFAULT_VAULT,
        help=f"Source Dendron vault (default: {DEFAULT_VAULT})"
    )
    parser.add_argument(
        "--output", type=pathlib.Path, default=DEFAULT_OUTPUT,
        help=f"Output Obsidian vault (default: {DEFAULT_OUTPUT})"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be done without making changes"
    )
    args = parser.parse_args()

    if not args.dry_run and args.output.exists() and any(args.output.iterdir()):
        print(f"⚠️  Output directory is not empty: {args.output}")
        print("   Use --dry-run first, or remove the directory.")
        sys.exit(1)

    migrate(args.vault, args.output, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
