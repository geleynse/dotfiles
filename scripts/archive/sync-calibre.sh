#!/bin/bash
# Sync local Calibre library to NAS for Calibre-Web
# Usage: sync-calibre.sh [--dry-run]

set -euo pipefail

LOCAL="/home/alan/Calibre Library/"
REMOTE="alan@192.168.1.3:/srv/dev-disk-by-uuid-7853de9f-1477-492b-85da-730f15d2aa61/books/Calibre Library/"

DRY_RUN=""
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN="--dry-run"
    echo "=== DRY RUN MODE ==="
fi

echo "Syncing Calibre library to NAS..."
echo "From: $LOCAL"
echo "To:   $REMOTE"
echo ""

rsync -av --delete --progress ${DRY_RUN:+"$DRY_RUN"} "$LOCAL" "$REMOTE"

if [[ -z "$DRY_RUN" ]]; then
    echo ""
    echo "✓ Sync complete!"
    echo "Calibre-Web will see changes immediately."
fi
