#!/bin/bash
# Start from the project directory even when launched from Finder.
set -e
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  echo "The project environment is missing. Run these commands in this folder:"
  echo "python3 -m venv .venv"
  echo ".venv/bin/python -m pip install -r requirements.lock"
  read -r -p "Press Enter to close. "
  exit 1
fi

echo "CheckoutCheck: http://127.0.0.1:8765"
echo "Keep this terminal open while using the app. Press Control-C to stop."
exec .venv/bin/python -m uvicorn checkoutcheck.server:app --host 127.0.0.1 --port 8765
