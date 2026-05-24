#!/bin/bash
# fix-gpth-dateless.sh — Recover dates for gpth date-unknown files using Google Takeout JSON sidecars
#
# For each file in ALL_PHOTOS/date-unknown/:
#   1. Find its JSON sidecar in the extracted Takeout directory
#   2. Read photoTakenTime.timestamp (falls back to creationTime)
#   3. Write the date into the file's EXIF via exiftool
#   4. Move the file to the correct ALL_PHOTOS/{year}/ folder
#
# Usage: fix-gpth-dateless.sh <gpth-output-dir> <extracted-dir>
# Example: fix-gpth-dateless.sh account1-gpth-output account1-extracted
#
# Run in tmux on the NAS. Logs to fix-dateless-{account}.log in the working directory.
# Requires: exiftool, jq

set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "Usage: $0 <gpth-output-dir> <extracted-dir>"
    echo "Example: $0 account1-gpth-output account1-extracted"
    exit 1
fi

GPTH_OUTPUT="$1"
EXTRACTED="$2"
DATE_UNKNOWN="$GPTH_OUTPUT/ALL_PHOTOS/date-unknown"
LOGFILE="fix-dateless-$(basename "$GPTH_OUTPUT").log"

if [[ ! -d "$DATE_UNKNOWN" ]]; then
    echo "ERROR: $DATE_UNKNOWN does not exist"
    exit 1
fi

if [[ ! -d "$EXTRACTED" ]]; then
    echo "ERROR: $EXTRACTED does not exist"
    exit 1
fi

for cmd in exiftool jq; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "ERROR: $cmd not found"
        exit 1
    fi
done

# Counters (use a temp file to survive subshell if needed)
total=0
fixed=0
no_sidecar=0
no_timestamp=0

# Count total files first
file_count=$(find "$DATE_UNKNOWN" -type f | wc -l)
echo "Processing $file_count files in $DATE_UNKNOWN"
echo "Logging to $LOGFILE"
echo "Started: $(date)" | tee "$LOGFILE"
echo "" >> "$LOGFILE"

# Build a lookup index of all JSON sidecars in extracted dir
echo "Building sidecar index from $EXTRACTED ..."
SIDECAR_INDEX=$(mktemp)
trap 'rm -f "$SIDECAR_INDEX"' EXIT
find "$EXTRACTED" -type f -name '*.json' \
    -not -name 'metadata.json' \
    -not -name 'print-subscriptions.json' \
    -not -name 'shared_album_comments.json' \
    -not -name 'user-generated-memory-titles.json' \
    > "$SIDECAR_INDEX"
sidecar_count=$(wc -l < "$SIDECAR_INDEX")
echo "Found $sidecar_count sidecar JSON files"
echo ""

# Build file list upfront to avoid subshell from pipe
FILE_LIST=$(mktemp)
find "$DATE_UNKNOWN" -type f > "$FILE_LIST"
trap 'rm -f "$SIDECAR_INDEX" "$FILE_LIST"' EXIT

while IFS= read -r filepath; do
    total=$((total + 1))
    filename=$(basename "$filepath")

    # Find matching JSON sidecar via pre-built index
    # Google Takeout patterns: {file}.supplemental-metadata.json, {file}.suppl.json, {file}.json
    sidecar=""
    matches=$(grep -F "/$filename." "$SIDECAR_INDEX" | grep -E '\.json$' || true)

    if [[ -n "$matches" ]]; then
        sidecar=$(echo "$matches" | head -1)
    fi

    if [[ -z "$sidecar" ]]; then
        # Try base name without extension (handles truncated sidecar names)
        basename_no_ext="${filename%.*}"
        if [[ ${#basename_no_ext} -ge 5 ]]; then
            matches=$(grep -F "/$basename_no_ext" "$SIDECAR_INDEX" | grep -E '\.json$' || true)
            if [[ -n "$matches" ]]; then
                sidecar=$(echo "$matches" | head -1)
            fi
        fi
    fi

    if [[ -z "$sidecar" ]]; then
        no_sidecar=$((no_sidecar + 1))
        echo "NO_SIDECAR: $filename" >> "$LOGFILE"
        if (( total % 100 == 0 )); then
            echo "[$total/$file_count] fixed=$fixed no_sidecar=$no_sidecar no_ts=$no_timestamp"
        fi
        continue
    fi

    # Extract photoTakenTime.timestamp, fall back to creationTime
    timestamp=$(jq -r '(.photoTakenTime.timestamp // "0")' "$sidecar" 2>/dev/null || echo "0")

    if [[ "$timestamp" == "0" || "$timestamp" == "null" || -z "$timestamp" ]]; then
        timestamp=$(jq -r '(.creationTime.timestamp // "0")' "$sidecar" 2>/dev/null || echo "0")
    fi

    if [[ "$timestamp" == "0" || "$timestamp" == "null" || -z "$timestamp" ]]; then
        no_timestamp=$((no_timestamp + 1))
        echo "NO_TIMESTAMP: $filename (sidecar: $sidecar)" >> "$LOGFILE"
        if (( total % 100 == 0 )); then
            echo "[$total/$file_count] fixed=$fixed no_sidecar=$no_sidecar no_ts=$no_timestamp"
        fi
        continue
    fi

    # Convert unix timestamp to exiftool date format (YYYY:MM:DD HH:MM:SS)
    exif_date=$(date -d "@$timestamp" '+%Y:%m:%d %H:%M:%S' 2>/dev/null || true)
    year=$(date -d "@$timestamp" '+%Y' 2>/dev/null || true)

    if [[ -z "$exif_date" || -z "$year" ]]; then
        no_timestamp=$((no_timestamp + 1))
        echo "BAD_TIMESTAMP: $filename ts=$timestamp" >> "$LOGFILE"
        continue
    fi

    # Write date into file EXIF (silently fail for formats that don't support it)
    if ! exiftool -overwrite_original -q \
        -DateTimeOriginal="$exif_date" \
        -CreateDate="$exif_date" \
        -ModifyDate="$exif_date" \
        "$filepath" 2>/dev/null; then
        # Formats like MTS, gif, bmp may not support EXIF — that's fine
        true
    fi

    # Always set file modification time to match
    touch -d "@$timestamp" "$filepath" 2>/dev/null || true

    # Move to correct year folder
    year_dir="$GPTH_OUTPUT/ALL_PHOTOS/$year"
    mkdir -p "$year_dir"

    # Handle filename collision in target dir
    target="$year_dir/$filename"
    if [[ -e "$target" ]]; then
        ext="${filename##*.}"
        base="${filename%.*}"
        counter=1
        while [[ -e "$year_dir/${base}_datfix${counter}.${ext}" ]]; do
            counter=$((counter + 1))
        done
        target="$year_dir/${base}_datfix${counter}.${ext}"
    fi

    mv "$filepath" "$target"
    fixed=$((fixed + 1))
    echo "FIXED: $filename -> $year ($exif_date)" >> "$LOGFILE"

    if (( total % 100 == 0 )); then
        echo "[$total/$file_count] fixed=$fixed no_sidecar=$no_sidecar no_ts=$no_timestamp"
    fi
done < "$FILE_LIST"

echo ""
echo "=== Complete ==="
echo "Total: $total"
echo "Fixed: $fixed"
echo "No sidecar: $no_sidecar"
echo "No timestamp: $no_timestamp"
echo ""
echo "Finished: $(date)" | tee -a "$LOGFILE"
echo "Total=$total Fixed=$fixed NoSidecar=$no_sidecar NoTimestamp=$no_timestamp" >> "$LOGFILE"
