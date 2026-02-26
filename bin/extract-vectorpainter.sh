#!/bin/bash

DOWNLOADS_DIR="$HOME/Downloads"
DEST_DIR="$HOME/projects/cad/2d/vectorpainter"

mkdir -p "$DEST_DIR"

# Collect files: VectorPainter zips in Downloads plus any command line args
# Matches both old format (p-*.zip) and new format (0NNN-*.zip)
files=()
for f in "$DOWNLOADS_DIR"/p-*.zip; do
    [[ -f "$f" ]] && files+=("$f")
done
for f in "$DOWNLOADS_DIR"/0[0-9][0-9][0-9]-*.zip; do
    [[ -f "$f" ]] && files+=("$f")
done
for f in "$@"; do
    [[ -f "$f" ]] && files+=("$f")
done

if [[ ${#files[@]} -eq 0 ]]; then
    echo "No files to process"
    exit 0
fi

for zipfile in "${files[@]}"; do
    name=$(basename "$zipfile" .zip)
    destdir="$DEST_DIR/$name"

    if [[ -d "$destdir" ]]; then
        echo "Skipping $zipfile - directory already exists"
        continue
    fi

    echo "Extracting $zipfile -> $destdir"
    mkdir -p "$destdir"
    if unzip -q "$zipfile" -d "$destdir"; then
        rm "$zipfile"
    else
        echo "ERROR: Failed to extract $zipfile - keeping original"
        rm -rf "$destdir"
    fi
done

echo "Done. Files extracted to $DEST_DIR"
