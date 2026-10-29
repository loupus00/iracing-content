#!/bin/sh
# Weekly job for Synology Task Scheduler (or cron): update the lists, then publish if anything changed.
# Needs python3 and git, and a clone of the GitHub repo that can push (see README).
set -eu
cd "$(dirname "$0")/.."
git pull --ff-only
python3 scripts/update.py
if [ -n "$(git status --porcelain)" ]; then
  git add -A
  git commit -m "Update AI content lists ($(date +%F))"
  git push
fi
