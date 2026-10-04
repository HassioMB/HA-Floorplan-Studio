#!/bin/bash

cd "$(dirname "$0")" || exit 1

clear
echo "========================================"
echo "        HA Floorplan Studio v1.0.0"
echo "========================================"
echo

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: Python 3 is not installed."
    echo
    echo "Install Python 3 and run this file again."
    echo
    read -p "Press Enter to close..."
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "First start - creating local environment..."
    python3 -m venv .venv

    if [ $? -ne 0 ]; then
        echo
        echo "ERROR: Could not create Python environment."
        read -p "Press Enter to close..."
        exit 1
    fi
fi

source .venv/bin/activate

echo "Checking dependencies..."
python -m pip install --quiet -r requirements.txt

if [ $? -ne 0 ]; then
    echo
    echo "ERROR: Could not install required Python packages."
    read -p "Press Enter to close..."
    exit 1
fi

echo
echo "Starting HA Floorplan Studio..."
echo "Address: http://127.0.0.1:8088/"
echo
echo "Keep this window open while using the editor."
echo "Press Ctrl+C to stop."
echo

(sleep 2 && open "http://127.0.0.1:8088/") &

PORT=8088 python server.py
