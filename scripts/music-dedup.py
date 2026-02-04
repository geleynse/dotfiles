#!/usr/bin/env python3
"""
Music Deduplication Script
Finds and removes duplicate audio files, keeping the highest quality version.
SAFE: Only matches files with very similar names in the same directory.
"""

import os
import sys
import re
import shutil
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# Quality ranking (higher = better)
FORMAT_QUALITY = {
    '.flac': 100,
    '.wav': 95,
    '.m4a': 80,
    '.aac': 80,
    '.ogg': 70,
    '.mp3': 60,
    '.wma': 50,
}

def normalize_name(name):
    """
    Normalize filename for comparison - CONSERVATIVE approach.
    Only normalizes spacing and case, preserves version info.
    """
    # Remove extension
    name = Path(name).stem
    # Lowercase
    name = name.lower()
    # Normalize separators to spaces
    name = re.sub(r'[\-_]+', ' ', name)
    # Collapse whitespace
    name = re.sub(r'\s+', ' ', name)
    return name.strip()

def extract_track_number(name):
    """Extract leading track number if present."""
    match = re.match(r'^(\d+)[\s\-_\.]+', name)
    if match:
        return int(match.group(1))
    return None

def names_are_duplicates(name1, name2):
    """
    Check if two filenames represent the same track.
    Conservative: must be very similar to be considered duplicates.
    """
    norm1 = normalize_name(name1)
    norm2 = normalize_name(name2)

    # Must have same track number (if present)
    track1 = extract_track_number(name1)
    track2 = extract_track_number(name2)
    if track1 is not None and track2 is not None and track1 != track2:
        return False

    # Remove track numbers for comparison
    norm1_notrack = re.sub(r'^\d+\s*', '', norm1)
    norm2_notrack = re.sub(r'^\d+\s*', '', norm2)

    # Must be identical after normalization, OR one contains the other
    if norm1_notrack == norm2_notrack:
        return True

    # Check if one is a subset (e.g., "song" vs "song 1" or "song (copy)")
    # But NOT if they differ by version markers
    version_markers = ['live', 'acoustic', 'remix', 'remaster', 'demo', 'edit', 'version', 'mix', 'radio', 'extended', 'instrumental', 'reprise']
    for marker in version_markers:
        if (marker in norm1_notrack) != (marker in norm2_notrack):
            return False

    # If one name contains the other completely and they're close in length
    if norm1_notrack in norm2_notrack or norm2_notrack in norm1_notrack:
        len_diff = abs(len(norm1_notrack) - len(norm2_notrack))
        if len_diff <= 5:  # Allow small differences like " 1" or "(2)"
            return True

    return False

def get_file_quality(filepath):
    """Get quality score for a file."""
    ext = Path(filepath).suffix.lower()
    base_quality = FORMAT_QUALITY.get(ext, 30)

    try:
        size_mb = os.path.getsize(filepath) / (1024 * 1024)
        # Add up to 20 points for size (caps at 20MB)
        size_bonus = min(size_mb, 20)
    except OSError:
        size_bonus = 0

    return base_quality + size_bonus

def find_duplicates(music_dir):
    """Find duplicate files in the music directory."""
    # Group files by directory
    dir_files = defaultdict(list)

    extensions = {'.mp3', '.flac', '.m4a', '.ogg', '.wav', '.wma', '.aac'}

    print(f"Scanning {music_dir}...")
    file_count = 0

    for root, dirs, files in os.walk(music_dir):
        # Skip hidden directories and trash folders
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        if '.trash' in root.lower():
            continue

        for filename in files:
            ext = Path(filename).suffix.lower()
            if ext in extensions:
                filepath = os.path.join(root, filename)
                dir_files[root].append((filename, filepath))
                file_count += 1

                if file_count % 1000 == 0:
                    print(f"  Scanned {file_count} files...")

    print(f"Scanned {file_count} total files")

    # Find duplicates within each directory
    duplicates = []
    for directory, files in dir_files.items():
        # Compare all pairs in this directory
        processed = set()

        for i, (name1, path1) in enumerate(files):
            if path1 in processed:
                continue

            group = [(name1, path1)]

            for j, (name2, path2) in enumerate(files[i+1:], i+1):
                if path2 in processed:
                    continue
                if names_are_duplicates(name1, name2):
                    group.append((name2, path2))
                    processed.add(path2)

            if len(group) > 1:
                processed.add(path1)
                # Sort by quality (highest first)
                files_with_quality = [(p, get_file_quality(p)) for n, p in group]
                files_with_quality.sort(key=lambda x: x[1], reverse=True)

                keep = files_with_quality[0][0]
                remove = [f for f, q in files_with_quality[1:]]

                duplicates.append({
                    'keep': keep,
                    'keep_quality': files_with_quality[0][1],
                    'remove': [(f, q) for f, q in files_with_quality[1:]],
                })

    return duplicates

def main():
    if len(sys.argv) < 2:
        print("Usage: music-dedup.py <music_directory> [--delete]")
        print("  Without --delete: dry run (shows what would be deleted)")
        print("  With --delete: move duplicate files to .trash folder")
        sys.exit(1)

    music_dir = sys.argv[1]
    dry_run = '--delete' not in sys.argv

    if not os.path.isdir(music_dir):
        print(f"Error: {music_dir} is not a directory")
        sys.exit(1)

    duplicates = find_duplicates(music_dir)

    if not duplicates:
        print("\nNo duplicates found!")
        return

    total_remove = sum(len(d['remove']) for d in duplicates)
    total_size = 0

    print(f"\nFound {len(duplicates)} duplicate groups ({total_remove} files to remove)")
    print("=" * 60)

    # Create trash directory and log file
    trash_dir = os.path.join(music_dir, '.trash-dedup')
    log_file = os.path.join(music_dir, f'.dedup-log-{datetime.now().strftime("%Y%m%d-%H%M%S")}.txt')

    if not dry_run:
        os.makedirs(trash_dir, exist_ok=True)
        log_handle = open(log_file, 'w')
        log_handle.write(f"Deduplication run: {datetime.now()}\n")
        log_handle.write(f"Music directory: {music_dir}\n\n")

    for dup in duplicates:
        print(f"\nKeeping: {os.path.basename(dup['keep'])}")
        print(f"  Path: {dup['keep']}")
        print(f"  Quality score: {dup['keep_quality']:.1f}")

        for remove_file, quality in dup['remove']:
            try:
                size = os.path.getsize(remove_file)
            except OSError:
                size = 0
            total_size += size
            size_mb = size / (1024 * 1024)
            action = "Would remove" if dry_run else "Moving to trash"
            print(f"  {action}: {os.path.basename(remove_file)} ({size_mb:.1f} MB, score: {quality:.1f})")

            if not dry_run:
                try:
                    # Move to trash instead of delete
                    rel_path = os.path.relpath(remove_file, music_dir)
                    trash_path = os.path.join(trash_dir, rel_path)
                    os.makedirs(os.path.dirname(trash_path), exist_ok=True)
                    shutil.move(remove_file, trash_path)
                    log_handle.write(f"MOVED: {remove_file}\n")
                    log_handle.write(f"  TO: {trash_path}\n")
                    log_handle.write(f"  KEPT: {dup['keep']}\n\n")
                    print(f"    Moved to trash!")
                except Exception as e:
                    print(f"    Error: {e}")
                    log_handle.write(f"ERROR: {remove_file} - {e}\n\n")

    print("=" * 60)
    print(f"Total: {total_remove} duplicate files, {total_size / (1024*1024):.1f} MB")

    if dry_run:
        print("\nThis was a DRY RUN. Run with --delete to move files to trash.")
    else:
        log_handle.close()
        print(f"\nFiles moved to: {trash_dir}")
        print(f"Log saved to: {log_file}")
        print("Review and delete trash folder when satisfied.")

if __name__ == '__main__':
    main()
