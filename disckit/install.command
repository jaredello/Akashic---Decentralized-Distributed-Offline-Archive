#!/bin/bash
# Double-click once to set up DiscKit (creates a private Python environment next to this file).
cd "$(dirname "$0")"
PY=""
for c in /Library/Frameworks/Python.framework/Versions/Current/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c "import tkinter, sys; sys.exit(0 if sys.version_info >= (3, 10) and tkinter.TkVersion >= 8.6 else 1)" >/dev/null 2>&1; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo "DiscKit needs Python 3.10+ with Tk 8.6."
  echo "Install it from https://www.python.org/downloads/macos/ (includes Tk),"
  echo "or with Homebrew:  brew install python python-tk"
  read -n 1 -s -r -p "Press any key to close"; exit 1
fi
echo "Using $($PY --version) at $(command -v $PY)"
"$PY" -m venv .venv && ./.venv/bin/pip install --upgrade pip -q && ./.venv/bin/pip install -r requirements.txt
chmod +x "DiscKit.command" "Read Discs.command"
echo ""
echo "DiscKit is ready. Double-click 'DiscKit.command' to open the app."
read -n 1 -s -r -p "Press any key to close"
