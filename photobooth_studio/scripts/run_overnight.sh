#!/usr/bin/env bash
# Runs the overnight workflow once. Used by cron (Mac/Linux).
cd "$(dirname "$0")/.." || exit 1
mkdir -p output/logs
PY="${PYTHON:-python3}"
[ -x .venv/bin/python ] && PY=.venv/bin/python
"$PY" -m studio overnight >> "output/logs/overnight-$(date +%Y-%m).log" 2>&1
