#!/bin/bash
cd ~/.openclaw/workspace || exit 1
git pull --rebase --quiet 2>/dev/null
if [ -n "$(git status --porcelain)" ]; then
    git add -A
    git commit -m "auto: sync from alan-framework $(date +%Y-%m-%d\ %H:%M)" --quiet
    git push --quiet 2>/dev/null
fi
