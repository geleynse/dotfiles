#!/bin/bash
# Backup pfSense config.xml to local storage and NAS
# Runs daily via cron from alan-framework (192.168.1.25)

set -euo pipefail

PFSENSE_HOST="root@192.168.1.1"
LOCAL_DIR="$HOME/backups/pfsense"
NAS_DIR="/srv/dev-disk-by-uuid-7853de9f-1477-492b-85da-730f15d2aa61/backups/pfsense"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
KEEP_DAYS=30

mkdir -p "$LOCAL_DIR"

# Pull config from pfSense
CONFIG_FILE="$LOCAL_DIR/config-${TIMESTAMP}.xml"
if scp -q "$PFSENSE_HOST:/cf/conf/config.xml" "$CONFIG_FILE"; then
    echo "$(date): Backed up pfSense config ($(wc -c < "$CONFIG_FILE") bytes) to $CONFIG_FILE"
else
    echo "$(date): ERROR: Failed to pull pfSense config" >&2
    exit 1
fi

# Copy to NAS
if scp -q "$CONFIG_FILE" "alan@192.168.1.3:$NAS_DIR/" 2>/dev/null; then
    echo "$(date): Copied to NAS"
else
    echo "$(date): WARNING: Failed to copy to NAS (non-fatal)" >&2
fi

# Prune old local backups
find "$LOCAL_DIR" -name "config-*.xml" -mtime +"$KEEP_DAYS" -delete 2>/dev/null || true

echo "$(date): Done. Local backups: $(ls "$LOCAL_DIR"/config-*.xml 2>/dev/null | wc -l)"
