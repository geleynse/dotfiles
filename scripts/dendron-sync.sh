#!/bin/bash
# Auto-sync Dendron vault via git
cd ~/Dendron/vault.personal || exit 1
git pull --rebase --quiet 2>/dev/null
if [ -n "$(git status --porcelain)" ]; then
    git add -A
    git commit -m "auto: sync from alan-framework $(date +%Y-%m-%d\ %H:%M)" --quiet
    git push --quiet 2>/dev/null
    echo "$(date): pushed local changes"
else
    echo "$(date): no local changes"
fi
