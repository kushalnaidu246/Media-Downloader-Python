#!/bin/bash
# Double-click to run the downloader. First run sets up a private Python environment.
cd "$(dirname "$0")" || exit 1

if [ ! -x .venv/bin/python ]; then
  echo "First-time setup (one minute)..."
  python3 -m venv .venv || { echo "Python 3 is required: https://www.python.org/downloads/"; read -n1 -p "Press any key to close"; exit 1; }
  .venv/bin/pip install -q -r requirements.txt
else
  # pick up any new dependencies, and keep yt-dlp fresh (YouTube breaks old versions often)
  .venv/bin/pip install -q -r requirements.txt 2>/dev/null
  .venv/bin/pip install -q -U yt-dlp 2>/dev/null
fi

# Launch the GUI and close this Terminal window's focus on it
exec .venv/bin/python ytgui.py
