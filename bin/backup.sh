#!/bin/bash

# Load credentials
source /home/alan/.config/restic/env

RESTIC_PASSWORD_FILE="/home/alan/.config/restic/password"
RESTIC_EXCLUDES="/home/alan/.config/restic/excludes"

# Save package list
pacman -Qqe > backups/pkglist_$(date +%F).txt

# Backup to Wasabi S3
restic -v -r s3:https://s3.us-west-1.wasabisys.com/framework-backup backup /home/alan \
  --password-file "$RESTIC_PASSWORD_FILE" \
  --exclude-caches \
  --exclude-file "$RESTIC_EXCLUDES"

restic -v -r s3:https://s3.us-west-1.wasabisys.com/framework-backup forget \
  --prune --keep-daily 7 --keep-weekly 5 --keep-monthly 12 --keep-yearly 75 \
  --password-file "$RESTIC_PASSWORD_FILE"

# Backup to local NAS
restic -v -r sftp:alan@192.168.1.3:/export/backups/framework-backup backup /home/alan \
  --password-file "$RESTIC_PASSWORD_FILE" \
  --exclude-caches \
  --exclude-file "$RESTIC_EXCLUDES"

restic -v -r sftp:alan@192.168.1.3:/export/backups/framework-backup forget \
  --prune --keep-daily 7 --keep-weekly 5 --keep-monthly 12 --keep-yearly 75 \
  --password-file "$RESTIC_PASSWORD_FILE"

# Optional: Backup to argon
if [[ "$1" == "--argon" ]]; then
  restic -v -r sftp:trano@argon:/data/backup/geleynse/framework-backup backup /home/alan \
    --password-file "$RESTIC_PASSWORD_FILE" \
    --exclude-caches \
    --exclude-file "$RESTIC_EXCLUDES"

  restic -v -r sftp:trano@argon:/data/backup/geleynse/framework-backup forget \
    --prune --keep-daily 7 --keep-weekly 5 --keep-monthly 12 --keep-yearly 75 \
    --password-file "$RESTIC_PASSWORD_FILE"
fi
