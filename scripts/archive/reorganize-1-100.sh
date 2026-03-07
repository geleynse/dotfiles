#!/bin/bash
# Reorganize 1-100 album collection into Artist/Album hierarchy
# Usage: ./reorganize-1-100.sh [--execute]
# Without --execute, runs in dry-run mode (preview only)

set -euo pipefail

MUSIC_DIR="/srv/dev-disk-by-uuid-7853de9f-1477-492b-85da-730f15d2aa61/music"
SOURCE_DIR="$MUSIC_DIR/1-100"
LOG_FILE="/tmp/reorganize-1-100.log"
DRY_RUN=true

if [[ "${1:-}" == "--execute" ]]; then
    DRY_RUN=false
    echo "EXECUTE MODE - changes will be made"
else
    echo "DRY RUN MODE - no changes will be made (use --execute to apply)"
fi

log() {
    echo "$1" | tee -a "$LOG_FILE"
}

log "=== Reorganize started $(date) ==="
log "Source: $SOURCE_DIR"
log "Destination: $MUSIC_DIR"

# Known reversed entries (Album - Artist format instead of Artist - Album)
declare -A reversed_entries=(
    ["King Of The Blues - Robert Johnson"]="Robert Johnson - King Of The Blues"
    ["Bridge Over Troubled Water - Simon and Garfunkel"]="Simon and Garfunkel - Bridge Over Troubled Water"
)

# Known entries with no separator (manual fixes)
declare -A no_separator_fixes=(
    ["Miles Davis Bitches Brew"]="Miles Davis - Bitches Brew"
)

# Track processed albums to avoid duplicates
declare -A processed

# Find all numbered album folders (use process substitution to keep array in main shell)
while read -r folder; do
    name=$(basename "$folder")

    # Skip if we've already processed this album name (duplicates in Part* folders)
    if [[ -n "${processed[$name]:-}" ]]; then
        log "SKIP (duplicate): $name"
        continue
    fi
    processed[$name]=1

    # Remove leading number: "01 - The Beatles - Album" -> "The Beatles - Album"
    without_num="${name#[0-9][0-9] - }"

    # Check for known entries with no separator first
    if [[ -n "${no_separator_fixes[$without_num]:-}" ]]; then
        normalized="${no_separator_fixes[$without_num]}"
        log "NOTE: Fixed missing separator -> $normalized"
    else
        # Normalize separator: " -X" (missing space after dash) -> " - X"
        # Only add space after dash if followed by non-space
        normalized=$(echo "$without_num" | sed 's/ -\([^ ]\)/ - \1/g')
    fi

    # Handle edge cases with no clear separator
    if [[ "$normalized" != *" - "* ]]; then
        log "MANUAL REVIEW: $folder (no ' - ' separator in: $without_num)"
        continue
    fi

    # Check if this is a known reversed entry
    if [[ -n "${reversed_entries[$normalized]:-}" ]]; then
        normalized="${reversed_entries[$normalized]}"
        log "NOTE: Corrected reversed entry -> $normalized"
    fi

    # Split on " - "
    artist="${normalized%% - *}"
    album="${normalized#* - }"

    # Validate we got both parts
    if [[ -z "$artist" || -z "$album" ]]; then
        log "ERROR: Could not parse artist/album from: $name"
        continue
    fi

    # Clean up artist name (trim whitespace)
    artist=$(echo "$artist" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    album=$(echo "$album" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')

    dest_artist="$MUSIC_DIR/$artist"
    dest_album="$dest_artist/$album"

    # Check if destination already exists
    if [[ -d "$dest_album" ]]; then
        log "EXISTS: $dest_album (skipping)"
        continue
    fi

    log "MOVE: $folder"
    log "   -> $dest_album"

    if [[ "$DRY_RUN" == false ]]; then
        # Create artist directory if needed
        if [[ ! -d "$dest_artist" ]]; then
            mkdir -p "$dest_artist" || { log "ERROR: mkdir failed for $dest_artist"; continue; }
        fi

        # Move the album folder
        mv "$folder" "$dest_album" || { log "ERROR: mv failed for $folder"; continue; }
        log "   OK"
    fi
done < <(find "$SOURCE_DIR" -maxdepth 2 -type d -name '[0-9][0-9] -*' | sort)

log "=== Reorganize completed $(date) ==="

# Summary
echo ""
echo "Log written to: $LOG_FILE"
if [[ "$DRY_RUN" == true ]]; then
    echo "Run with --execute to apply changes"
fi
