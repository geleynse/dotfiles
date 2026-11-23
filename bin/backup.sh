#!/bin/bash

# Restic backup script - backs up /home/alan to Wasabi S3, local NAS, and argon
# Runs daily via systemd timer (backup.timer)
# Usage: backup.sh [backup|prune|status]

set -euo pipefail

# Load credentials
source /home/alan/.config/restic/env

RESTIC_PASSWORD_FILE="/home/alan/.config/restic/password"
RESTIC_EXCLUDES="/home/alan/.config/restic/excludes"

# Hosts with ~/.ssh/backup_ssh_config (alan-laptop) reach the sftp repos with a
# dedicated passphrase-free, sftp-only key and never touch the ssh agent. The
# interactive key's GNOME agent hangs the backup forever when it is still
# locked after a boot (2026-11-23). Hosts without the file use plain ssh.
RESTIC_SSH_CONFIG="${HOME}/.ssh/backup_ssh_config"
restic() {
  if [ -r "$RESTIC_SSH_CONFIG" ]; then
    command restic -o sftp.args="-F ${RESTIC_SSH_CONFIG}" "$@"
  else
    command restic "$@"
  fi
}

REPOS=(
  "s3:https://s3.us-west-1.wasabisys.com/framework-backup"
  "sftp:alan@192.168.1.3:/export/backups/framework-backup"
  "sftp:trano@argon:/data/backup/geleynse/framework-backup"
)
REPO_NAMES=("wasabi" "nas" "argon")

# Collected per-repo failures; reported together at the end by report().
BACKUP_FAILED=()
PRUNE_FAILED=()

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
  # Per-repo retention policies
  # Wasabi (cloud $$$): lean — monthly + yearly only
  # NAS/Argon (local/offsite): more granular recovery points
  # Indexed to match REPO_NAMES; an associative array is avoided deliberately.
  RETENTION=(
    "--keep-monthly 6 --keep-yearly 75"
    "--keep-daily 3 --keep-weekly 2 --keep-monthly 6 --keep-yearly 75"
    "--keep-daily 3 --keep-weekly 2 --keep-monthly 6 --keep-yearly 75"
  )

  for i in "${!REPOS[@]}"; do
    repo="${REPOS[$i]}"
    name="${REPO_NAMES[$i]}"
    policy="${RETENTION[$i]}"

    echo "=== Pruning $name ($policy) ==="
    # Unlock stale locks before pruning
    restic -r "$repo" --password-file "$RESTIC_PASSWORD_FILE" unlock 2>/dev/null || true

    # A failure here must not abort the remaining repos.
    # --retry-lock: two hosts back up into these repos (see BACKUP_PRUNE_HOST),
    # so a lock held by the other host's backup is normal; wait for it.
    if restic -v -r "$repo" forget \
      --retry-lock 30m \
      --prune $policy \
      --password-file "$RESTIC_PASSWORD_FILE"; then
      echo "--- prune $name: OK"
    else
      echo "--- prune $name: FAILED"
      PRUNE_FAILED+=("$name")
    fi
  done
}

backup() {
  # Save package list
  pacman -Qqe > /home/alan/backups/pkglist_$(date +%F).txt

  for i in "${!REPOS[@]}"; do
    repo="${REPOS[$i]}"
    name="${REPO_NAMES[$i]}"

    echo "=== Backing up to $name ==="
    # One unreachable repo must not cost us the others. Before this guard,
    # `set -e` meant an sftp failure on the NAS silently skipped argon
    # entirely — the offsite copy — and skipped prune for every repo.
    # (Seen 2026-08-02: NAS broken pipe, argon never ran.)
    if restic -v -r "$repo" backup /home/alan \
      --retry-lock 30m \
      --password-file "$RESTIC_PASSWORD_FILE" \
      --exclude-caches \
      --exclude-file "$RESTIC_EXCLUDES"; then
      echo "--- backup $name: OK"
    else
      echo "--- backup $name: FAILED (continuing with remaining repos)"
      BACKUP_FAILED+=("$name")
    fi
  done

  # Since the 2026-11 desk/laptop split, alan-framework (always-on desk) and
  # alan-laptop share these repos. Prune takes an exclusive lock, and both
  # hosts pruning at midnight failed one of them almost nightly. forget groups
  # by host, so one host pruning still applies the policy to both hosts'
  # snapshots. `backup.sh prune` still prunes from anywhere.
  if [ "$(hostname -s)" = "${BACKUP_PRUNE_HOST:-alan-framework}" ]; then
    prune
  else
    echo "=== Skipping prune: ${BACKUP_PRUNE_HOST:-alan-framework} prunes these repos ==="
  fi

  report
}

# Print a per-repo verdict and exit non-zero if anything failed, so the
# OnFailure= handler still fires — but only after every repo has been tried.
report() {
  echo ""
  echo "=== Summary ==="
  for name in "${REPO_NAMES[@]}"; do
    b="OK"; p="OK"
    [[ " ${BACKUP_FAILED[*]-} " == *" $name "* ]] && b="FAILED"
    [[ " ${PRUNE_FAILED[*]-} " == *" $name "* ]] && p="FAILED"
    printf "  %-8s backup: %-6s prune: %s\n" "$name" "$b" "$p"
  done

  local nb=${#BACKUP_FAILED[@]} np=${#PRUNE_FAILED[@]}
  if (( nb > 0 || np > 0 )); then
    echo ""
    echo "FAILED: ${nb} backup, ${np} prune. See log above."
    return 1
  fi
  echo ""
  echo "All repos OK."
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
    report
    ;;
  *)
    echo "Usage: backup.sh [backup|prune|status]"
    exit 1
    ;;
esac
