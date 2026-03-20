#!/bin/bash
# Auto-sync Dendron vault via git
cd ~/Dendron/vault.personal || exit 1

# If a rebase was left broken (e.g. from a previous failed run), clean it up
if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
    git rebase --abort 2>/dev/null
    echo "$(date): aborted stale rebase"
fi

# Pull remote changes; on conflict, abort and retry as merge
if ! git pull --rebase --quiet 2>/dev/null; then
    git rebase --abort 2>/dev/null
    # Fall back to merge — creates a merge commit but never leaves repo broken
    git pull --no-rebase --quiet 2>/dev/null || {
        echo "$(date): pull failed, skipping this cycle"
        exit 0
    }
fi

if [ -n "$(git status --porcelain)" ]; then
    git add -A
    git commit -m "auto: sync from alan-framework $(date +%Y-%m-%d\ %H:%M)" --quiet
    git push --quiet 2>/dev/null || echo "$(date): push failed, will retry next cycle"
    echo "$(date): pushed local changes"
else
    echo "$(date): no local changes"
fi
