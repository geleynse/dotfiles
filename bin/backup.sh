#!/bin/bash

# Restic backup script - backs up /home/alan to Wasabi S3, local NAS, and argon
# Runs daily via systemd timer (backup.timer)
# Usage: backup.sh [backup|prune|status]

set -euo pipefail

# Load credentials
source /home/alan/.config/restic/env

RESTIC_PASSWORD_FILE="/home/alan/.config/restic/password"
RESTIC_EXCLUDES="/home/alan/.config/restic/excludes"

REPOS=(
  "s3:https://s3.us-west-1.wasabisys.com/framework-backup"
  "sftp:alan@192.168.1.3:/export/backups/framework-backup"
  "sftp:trano@argon:/data/backup/geleynse/framework-backup"
)
REPO_NAMES=("wasabi" "nas" "argon")

repo_flags() {
  echo -r "$1" --password-file "$RESTIC_PASSWORD_FILE"
}

status() {
  echo "=== Restic Backup Status ==="
  echo ""

  # Last run info from systemd
  echo "--- Last Run ---"
  systemctl --user show backup.service \
    --property=ActiveState,SubState,ExecMainStartTimestamp,ExecMainExitTimestamp,ExecMainStatus,Result \
    2>/dev/null | while IFS='=' read -r key val; do
    printf "  %-28s %s\n" "$key:" "$val"
  done
  echo ""

  # Next scheduled run
  next=$(systemctl --user show backup.timer --property=NextElapseUSecRealtime 2>/dev/null | cut -d= -f2-)
  echo "  Next run: ${next:-unknown}"
  echo ""

  # Per-repo stats
  for i in "${!REPOS[@]}"; do
    repo="${REPOS[$i]}"
    name="${REPO_NAMES[$i]}"
    echo "--- $name ($repo) ---"

    if ! restic -r "$repo" --password-file "$RESTIC_PASSWORD_FILE" cat config >/dev/null 2>&1; then
      echo "  ERROR: cannot reach repository"
      echo ""
      continue
    fi

    # Latest snapshot
    latest=$(restic -r "$repo" --password-file "$RESTIC_PASSWORD_FILE" snapshots --latest 1 --json 2>/dev/null)
    if [ -n "$latest" ] && [ "$latest" != "null" ] && [ "$latest" != "[]" ]; then
      snap_time=$(echo "$latest" | jq -r '.[0].time // "unknown"' 2>/dev/null)
      snap_id=$(echo "$latest" | jq -r '.[0].short_id // "unknown"' 2>/dev/null)
      echo "  Latest snapshot: $snap_id ($snap_time)"
    else
      echo "  Latest snapshot: none"
    fi

    # Snapshot count
    count=$(restic -r "$repo" --password-file "$RESTIC_PASSWORD_FILE" snapshots --json 2>/dev/null | jq 'length' 2>/dev/null || echo "?")
    echo "  Total snapshots: $count"

    # Check for stale locks
    locks=$(restic -r "$repo" --password-file "$RESTIC_PASSWORD_FILE" list locks 2>/dev/null | wc -l || echo 0)
    if [ "$locks" -gt 0 ]; then
      echo "  WARNING: $locks stale lock(s) found (run: restic -r '$repo' unlock)"
    fi

    # Repo size (stats can be slow, use cache)
    echo "  (run 'backup.sh stats' for repo size - may take a while)"
    echo ""
  done

  # Exclude file summary
  exclude_count=$(grep -c '^[^#]' "$RESTIC_EXCLUDES" 2>/dev/null | grep -oP '\d+' || echo "?")
  echo "--- Excludes ($RESTIC_EXCLUDES) ---"
  echo "  $exclude_count active exclude patterns"
  echo ""

  # Estimated backup size
  echo "--- Current Source ---"
  echo "  Scanning /home/alan (this may take a moment)..."
  file_count=$(restic -r "${REPOS[0]}" --password-file "$RESTIC_PASSWORD_FILE" \
    backup /home/alan --dry-run --exclude-caches --exclude-file "$RESTIC_EXCLUDES" 2>&1 \
    | tail -1 || echo "  scan failed")
  echo "  $file_count"
}

prune() {
  for i in "${!REPOS[@]}"; do
    repo="${REPOS[$i]}"
    name="${REPO_NAMES[$i]}"

    echo "=== Pruning $name ==="
    # Unlock stale locks before pruning
    restic -r "$repo" --password-file "$RESTIC_PASSWORD_FILE" unlock 2>/dev/null || true

    restic -v -r "$repo" forget \
      --prune --keep-daily 7 --keep-weekly 5 --keep-monthly 12 --keep-yearly 75 \
      --password-file "$RESTIC_PASSWORD_FILE"
  done
}

backup() {
  # Save package list
  pacman -Qqe > /home/alan/backups/pkglist_$(date +%F).txt

  for i in "${!REPOS[@]}"; do
    repo="${REPOS[$i]}"
    name="${REPO_NAMES[$i]}"

    echo "=== Backing up to $name ==="
    restic -v -r "$repo" backup /home/alan \
      --password-file "$RESTIC_PASSWORD_FILE" \
      --exclude-caches \
      --exclude-file "$RESTIC_EXCLUDES"
  done

  prune
}

case "${1:-backup}" in
  status)
    status
    ;;
  backup)
    backup
    ;;
  prune)
    prune
    ;;
  *)
    echo "Usage: backup.sh [backup|prune|status]"
    exit 1
    ;;
esac
