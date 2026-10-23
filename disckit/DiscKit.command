#!/bin/bash
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { echo "Run install.command first."; read -n 1 -s; exit 1; }
exec ./.venv/bin/python -m disckit gui
