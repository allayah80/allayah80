#!/usr/bin/env bash
cd "$(dirname "$0")/.." || exit 1
PY="${PYTHON:-python3}"; [ -x .venv/bin/python ] && PY=.venv/bin/python
"$PY" -m studio dashboard
