#!/usr/bin/env python3
"""Update ~/scripts/tasks to use Obsidian vault paths.

Changes:
  - VAULT_DIR: ~/Dendron/vault.personal → ~/Obsidian/vault/tasks
  - Task file names: tasks.inbox.md → inbox.md (no dot prefix in folder)
  - Project prefix: tasks.projects.* → projects-*.md
  - Docstring updated

Usage:
    # Dry run:
    python3 update-tasks-paths.py --dry-run

    # Execute:
    python3 update-tasks-paths.py

    # Custom paths:
    python3 update-tasks-paths.py --tasks-script ~/scripts/tasks --vault ~/Obsidian/vault
"""

import argparse
import pathlib
import re
import shutil
import sys

DEFAULT_TASKS_SCRIPT = pathlib.Path.home() / "scripts" / "tasks"
DEFAULT_OBSIDIAN_VAULT = pathlib.Path.home() / "Obsidian" / "vault"


def update_tasks_script(script_path: pathlib.Path, vault_path: pathlib.Path,
                         dry_run: bool = False) -> dict:
    """Update path constants in the tasks script."""

    if not script_path.exists():
        print(f"❌ Tasks script not found: {script_path}")
        sys.exit(1)

    content = script_path.read_text(encoding="utf-8")
    original = content

    tasks_dir = vault_path / "tasks"

    # Track changes
    changes = []

    # 1. Update docstring
    old_doc = 'Manages tasks stored as structured markdown in ~/Dendron/vault.personal/tasks.*.md.'
    new_doc = 'Manages tasks stored as structured markdown in ~/Obsidian/vault/tasks/.'
    if old_doc in content:
        content = content.replace(old_doc, new_doc)
        changes.append(("docstring", old_doc, new_doc))

    # 2. Update VAULT_DIR
    old_vault = 'VAULT_DIR = pathlib.Path.home() / "Dendron" / "vault.personal"'
    new_vault = f'VAULT_DIR = pathlib.Path.home() / "Obsidian" / "vault" / "tasks"'
    if old_vault in content:
        content = content.replace(old_vault, new_vault)
        changes.append(("VAULT_DIR", old_vault, new_vault))

    # 3. Update task file paths (now just filename, no tasks. prefix)
    path_changes = [
        ('TASKS_INBOX = VAULT_DIR / "tasks.inbox.md"',
         'TASKS_INBOX = VAULT_DIR / "inbox.md"'),
        ('TASKS_SCHEDULED = VAULT_DIR / "tasks.scheduled.md"',
         'TASKS_SCHEDULED = VAULT_DIR / "scheduled.md"'),
        ('TASKS_BACKLOG = VAULT_DIR / "tasks.backlog.md"',
         'TASKS_BACKLOG = VAULT_DIR / "backlog.md"'),
        ('TASKS_RECURRING = VAULT_DIR / "tasks.recurring.md"',
         'TASKS_RECURRING = VAULT_DIR / "recurring.md"'),
        ('TASKS_DONE = VAULT_DIR / "tasks.done.md"',
         'TASKS_DONE = VAULT_DIR / "done.md"'),
    ]

    for old_line, new_line in path_changes:
        if old_line in content:
            content = content.replace(old_line, new_line)
            changes.append(("path", old_line, new_line))

    # 4. Update project prefix (tasks.projects.* → projects-*)
    old_prefix = 'TASKS_PROJECT_PREFIX = "tasks.projects."'
    new_prefix = 'TASKS_PROJECT_PREFIX = "projects-"'
    if old_prefix in content:
        content = content.replace(old_prefix, new_prefix)
        changes.append(("project_prefix", old_prefix, new_prefix))

    # Report
    print(f"\n📝 Script: {script_path}")
    print(f"📂 New tasks dir: {tasks_dir}")
    print(f"✏️  Changes: {len(changes)}")

    for kind, old, new in changes:
        print(f"\n  [{kind}]")
        print(f"  - {old}")
        print(f"  + {new}")

    if not changes:
        print("\n⚠️  No changes needed — paths may already be updated.")
        return {"changes": 0}

    if dry_run:
        print(f"\n🔍 DRY RUN — no files modified.")
    else:
        # Backup original
        backup = script_path.with_suffix(".bak")
        shutil.copy2(script_path, backup)
        print(f"\n💾 Backup: {backup}")

        # Write updated script
        script_path.write_text(content, encoding="utf-8")
        print(f"✅ Updated: {script_path}")

        # Verify it parses
        try:
            compile(content, str(script_path), "exec")
            print("✅ Syntax check passed")
        except SyntaxError as e:
            print(f"❌ Syntax error after update: {e}")
            print("   Restoring backup...")
            shutil.copy2(backup, script_path)
            return {"changes": 0, "error": str(e)}

    return {"changes": len(changes)}


def main():
    parser = argparse.ArgumentParser(
        description="Update tasks CLI paths from Dendron to Obsidian"
    )
    parser.add_argument(
        "--tasks-script", type=pathlib.Path, default=DEFAULT_TASKS_SCRIPT,
        help=f"Path to tasks script (default: {DEFAULT_TASKS_SCRIPT})"
    )
    parser.add_argument(
        "--vault", type=pathlib.Path, default=DEFAULT_OBSIDIAN_VAULT,
        help=f"Obsidian vault root (default: {DEFAULT_OBSIDIAN_VAULT})"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show changes without modifying files"
    )
    args = parser.parse_args()

    update_tasks_script(args.tasks_script, args.vault, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
