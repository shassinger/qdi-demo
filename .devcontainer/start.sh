#!/bin/bash
set -Eeuo pipefail

# Clean up any existing instances from a previous Codespace start.
pkill -f qdi_demo_server || true
pkill -f "http.server 3000" || true

# Get workspace root directory.
WORKSPACE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$WORKSPACE_DIR"

# Ensure virtualenv exists in the workspace.
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Ensure pip is upgraded and dependencies are installed.
echo "Verifying Python dependencies..."
.venv/bin/pip install --upgrade pip
.venv/bin/pip install fastapi uvicorn httpx qiskit qiskit-aer

# Find an available compiler (g++, clang++, or c++).
COMPILER=""
if command -v g++ >/dev/null 2>&1; then
    COMPILER="g++"
elif command -v clang++ >/dev/null 2>&1; then
    COMPILER="clang++"
elif command -v c++ >/dev/null 2>&1; then
    COMPILER="c++"
fi

# Fallback: install build-essential if no compiler exists.
if [ -z "$COMPILER" ]; then
    echo "No C++ compiler found. Installing build-essential..."
    sudo apt-get update
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y build-essential
    COMPILER="g++"
fi

# Compile the QDI C-ABI mock shared library.
echo "Compiling QDI C-ABI mock library using $COMPILER..."
"$COMPILER" -shared -o qdi-core/libqdi_mock.so -Iqdi-core/include qdi-core/src/qdi_mock.cpp -std=c++17 -fPIC

wait_for_url() {
    local name="$1"
    local url="$2"
    local pid="$3"
    local log_file="$4"

    echo "Waiting for $name at $url..."
    for _ in $(seq 1 30); do
        if curl -fsS --max-time 2 "$url" >/dev/null; then
            echo "$name is ready."
            return 0
        fi

        if ! kill -0 "$pid" >/dev/null 2>&1; then
            echo "$name process exited before becoming ready. Recent $log_file output:"
            tail -100 "$log_file" || true
            return 1
        fi

        sleep 1
    done

    echo "$name did not become ready in time. Recent $log_file output:"
    tail -100 "$log_file" || true
    return 1
}

set_codespace_port_visibility() {
    if [ -z "${CODESPACE_NAME:-}" ]; then
        echo "Not running in GitHub Codespaces; skipping port visibility setup."
        return 0
    fi

    if ! command -v gh >/dev/null 2>&1; then
        echo "GitHub CLI not found; set ports 3000 and 8000 public manually if needed."
        return 0
    fi

    echo "Setting Codespaces ports 3000 and 8000 to public visibility..."
    if GH_TOKEN="${GITHUB_TOKEN:-}" gh codespace ports visibility 3000:public 8000:public -c "$CODESPACE_NAME"; then
        echo "Codespaces port visibility set to public."
    else
        echo "Unable to set port visibility automatically; set ports 3000 and 8000 public in the Ports tab."
    fi
}

# Start backend API server in background using the explicit virtualenv Python interpreter.
echo "Starting FastAPI Server..."
nohup .venv/bin/python -u qdi-core/python/qdi_demo_server.py < /dev/null > server.log 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" > server.pid

# Start static web server in background using the explicit virtualenv Python interpreter.
echo "Starting Web Console Server..."
nohup .venv/bin/python -u -m http.server 3000 --bind 0.0.0.0 --directory qdi-core/python < /dev/null > web.log 2>&1 &
WEB_PID=$!
echo "$WEB_PID" > web.pid

wait_for_url "QDI Backend API" "http://127.0.0.1:8000/qdi/v1/devices/mock/discover" "$SERVER_PID" "server.log"
wait_for_url "QDI Web Console" "http://127.0.0.1:3000/" "$WEB_PID" "web.log"
set_codespace_port_visibility

echo "QDI sandbox environment initialized successfully."
