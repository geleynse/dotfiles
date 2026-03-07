#!/usr/bin/env python3
"""
Check media files for corruption/invalid formats.
Uses ffprobe to validate audio and video files.

Usage:
    media-check.py /path/to/media [--audio-only] [--video-only] [--move-invalid DIR] [--delete-invalid] [--output report.txt]
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

AUDIO_EXTENSIONS = {'.mp3', '.flac', '.m4a', '.aac', '.ogg', '.opus', '.wma', '.wav', '.aiff', '.ape', '.wv'}
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.mpeg', '.mpg', '.ts', '.vob'}
ALL_MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS

def check_file(filepath):
    """Check if a file is a valid media file using ffprobe."""
    issues = []

    # Check if file is readable
    if not os.access(filepath, os.R_OK):
        return filepath, ['not readable (permission denied)']

    # Check file size
    try:
        size = os.path.getsize(filepath)
        if size == 0:
            return filepath, ['empty file (0 bytes)']
        if size < 1000:  # Less than 1KB is suspicious for audio
            issues.append(f'suspiciously small ({size} bytes)')
    except OSError as e:
        return filepath, [f'cannot stat: {e}']

    # Use ffprobe to check file validity
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries',
             'format=duration,format_name', '-of', 'default=noprint_wrappers=1',
             str(filepath)],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            error = result.stderr.strip()
            if error:
                # Simplify common errors
                if 'Invalid data' in error:
                    issues.append('invalid/corrupted data')
                elif 'End of file' in error:
                    issues.append('truncated file')
                elif 'Header missing' in error:
                    issues.append('missing header')
                elif 'Could not find codec' in error:
                    issues.append('unknown codec')
                else:
                    # Take first line of error
                    issues.append(error.split('\n')[0][:100])
            else:
                issues.append('ffprobe failed (unknown reason)')
        else:
            # Check duration
            output = result.stdout
            if 'duration=' in output:
                for line in output.split('\n'):
                    if line.startswith('duration='):
                        dur = line.split('=')[1].strip()
                        if dur == 'N/A' or not dur:
                            issues.append('no duration (possibly corrupted)')
                        else:
                            try:
                                duration = float(dur)
                                if duration < 1.0:
                                    issues.append(f'very short duration ({dur}s)')
                            except ValueError:
                                issues.append(f'invalid duration value: {dur}')

    except subprocess.TimeoutExpired:
        issues.append('ffprobe timeout (file may be corrupted)')
    except FileNotFoundError:
        print("Error: ffprobe not found. Install ffmpeg.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        issues.append(f'check failed: {e}')

    return filepath, issues

def scan_directory(path, extensions, workers=4):
    """Scan directory for media files and check each one."""
    media_files = []

    print(f"Scanning {path} for media files...", file=sys.stderr)

    for root, dirs, files in os.walk(path):
        # Skip hidden directories
        dirs[:] = [d for d in dirs if not d.startswith('.')]

        for f in files:
            ext = Path(f).suffix.lower()
            if ext in extensions:
                media_files.append(os.path.join(root, f))

    total = len(media_files)
    print(f"Found {total} media files. Checking...", file=sys.stderr)

    invalid_files = []
    checked = 0
    progress_interval = max(1, total // 20)  # Show ~20 progress updates

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(check_file, f): f for f in media_files}

        for future in as_completed(futures):
            filepath, issues = future.result()
            checked += 1

            if checked % progress_interval == 0 or checked == total:
                pct = (checked * 100) // total
                print(f"  Progress: {checked}/{total} ({pct}%)", file=sys.stderr)

            if issues:
                invalid_files.append((filepath, issues))

    return invalid_files, total

def main():
    parser = argparse.ArgumentParser(description='Check media files for corruption')
    parser.add_argument('path', help='Directory to scan')
    parser.add_argument('--workers', '-j', type=int, default=4, help='Number of parallel workers')
    parser.add_argument('--output', '-o', help='Write report to file')
    parser.add_argument('--delete-invalid', action='store_true', help='Delete invalid files (DANGEROUS)')
    parser.add_argument('--move-invalid', metavar='DIR', help='Move invalid files to directory')
    parser.add_argument('--audio-only', action='store_true', help='Only check audio files')
    parser.add_argument('--video-only', action='store_true', help='Only check video files')
    args = parser.parse_args()

    if not os.path.isdir(args.path):
        print(f"Error: {args.path} is not a directory", file=sys.stderr)
        sys.exit(1)

    # Determine which extensions to check
    if args.audio_only:
        extensions = AUDIO_EXTENSIONS
    elif args.video_only:
        extensions = VIDEO_EXTENSIONS
    else:
        extensions = ALL_MEDIA_EXTENSIONS

    invalid_files, total = scan_directory(args.path, extensions, args.workers)

    # Sort by path
    invalid_files.sort(key=lambda x: x[0])

    # Output results
    output_lines = []
    output_lines.append("Media File Check Report")
    output_lines.append("=" * 50)
    output_lines.append(f"Scanned: {args.path}")
    output_lines.append(f"Total files: {total}")
    output_lines.append(f"Invalid files: {len(invalid_files)}")
    output_lines.append("")

    if invalid_files:
        output_lines.append("Invalid Files:")
        output_lines.append("-" * 50)

        for filepath, issues in invalid_files:
            output_lines.append(f"\n{filepath}")
            for issue in issues:
                output_lines.append(f"  - {issue}")
    else:
        output_lines.append("No invalid files found!")

    report = '\n'.join(output_lines)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(report)
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(report)

    # Handle invalid files
    if invalid_files and args.move_invalid:
        os.makedirs(args.move_invalid, exist_ok=True)
        print(f"\nMoving {len(invalid_files)} invalid files to {args.move_invalid}...", file=sys.stderr)
        for filepath, _ in invalid_files:
            rel_path = os.path.relpath(filepath, args.path)
            dest = os.path.join(args.move_invalid, rel_path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            try:
                shutil.move(filepath, dest)
            except Exception as e:
                print(f"  Failed to move {filepath}: {e}", file=sys.stderr)
        print("Done.", file=sys.stderr)

    if invalid_files and args.delete_invalid:
        confirm = input(f"Delete {len(invalid_files)} files? Type 'yes' to confirm: ")
        if confirm == 'yes':
            for filepath, _ in invalid_files:
                try:
                    os.remove(filepath)
                except Exception as e:
                    print(f"  Failed to delete {filepath}: {e}", file=sys.stderr)
            print(f"Deleted {len(invalid_files)} files.", file=sys.stderr)

    return 0 if not invalid_files else 1

if __name__ == '__main__':
    sys.exit(main())
