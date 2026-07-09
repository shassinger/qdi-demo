#!/bin/bash
# Clean up any existing instances
pkill -f qdi_demo_server || true
pkill -f "http.server 3000" || true

# Get workspace root directory
WORKSPACE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$WORKSPACE_DIR"

# Ensure virtualenv exists in the workspace
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Ensure pip is upgraded and dependencies are installed
echo "Verifying Python dependencies..."
.venv/bin/pip install --upgrade pip
.venv/bin/pip install fastapi uvicorn httpx qiskit qiskit-aer

# Find an available compiler (g++, clang++, or c++)
COMPILER=""
if command -v g++ >/dev/null 2>&1; then
    COMPILER="g++"
elif command -v clang++ >/dev/null 2>&1; then
    COMPILER="clang++"
elif command -v c++ >/dev/null 2>&1; then
    COMPILER="c++"
fi

# Fallback: install build-essential if no compiler exists
if [ -z "$COMPILER" ]; then
    echo "No C++ compiler found. Installing build-essential..."
    sudo apt-get update && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y build-essential
    COMPILER="g++"
fi

# Compile the QDI C-ABI mock shared library
echo "Compiling QDI C-ABI mock library using $COMPILER..."
$COMPILER -shared -o qdi-core/libqdi_mock.so -Iqdi-core/include qdi-core/src/qdi_mock.cpp -std=c++17 -fPIC

# Start backend API server in background using the explicit virtualenv Python interpreter
echo "Starting FastAPI Server..."
nohup .venv/bin/python qdi-core/python/qdi_demo_server.py < /dev/null > server.log 2>&1 &

# Start static web server in background using the explicit virtualenv Python interpreter
echo "Starting Web Console Server..."
nohup .venv/bin/python -m http.server 3000 --bind 0.0.0.0 --directory qdi-core/python < /dev/null > web.log 2>&1 &

echo "QDI sandbox environment initialized successfully."
