#!/usr/bin/env bash
set -euo pipefail

# Clean up any existing instances
pkill -f qdi_demo_server || true
pkill -f "http.server ${QDI_WEB_PORT:-3000}" || true

# Get workspace root directory
WORKSPACE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$WORKSPACE_DIR"

QDI_API_HOST="${QDI_API_HOST:-0.0.0.0}"
QDI_API_PORT="${QDI_API_PORT:-8000}"
QDI_WEB_HOST="${QDI_WEB_HOST:-0.0.0.0}"
QDI_WEB_PORT="${QDI_WEB_PORT:-3000}"

# Ensure virtualenv exists in the workspace
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Ensure pip is upgraded and dependencies are installed
echo "Verifying Python dependencies..."
.venv/bin/pip install --upgrade pip
.venv/bin/pip install fastapi uvicorn httpx qiskit qiskit-aer qiskit_qasm3_import

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
echo "Starting FastAPI Server on ${QDI_API_HOST}:${QDI_API_PORT}..."
QDI_API_HOST="$QDI_API_HOST" QDI_API_PORT="$QDI_API_PORT" nohup .venv/bin/python qdi-core/python/qdi_demo_server.py < /dev/null > server.log 2>&1 &
API_PID=$!

# Start static web server in background using the explicit virtualenv Python interpreter
echo "Starting Web Console Server on ${QDI_WEB_HOST}:${QDI_WEB_PORT}..."
nohup .venv/bin/python -m http.server --bind "$QDI_WEB_HOST" --directory qdi-core/python "$QDI_WEB_PORT" < /dev/null > web.log 2>&1 &
WEB_PID=$!

wait_for_url() {
    local name="$1"
    local url="$2"
    local log_file="$3"

    for _ in $(seq 1 30); do
        if .venv/bin/python - "$url" >/dev/null 2>&1 <<'PY'
import sys
import urllib.request

urllib.request.urlopen(sys.argv[1], timeout=1).read()
PY
        then
            echo "${name} is ready at ${url}"
            return 0
        fi
        sleep 1
    done

    echo "${name} did not become ready at ${url}" >&2
    echo "--- ${log_file} ---" >&2
    tail -n 80 "$log_file" >&2 || true
    return 1
}

wait_for_url "QDI Backend API" "http://127.0.0.1:${QDI_API_PORT}/health" "server.log"
wait_for_url "QDI Web Console" "http://127.0.0.1:${QDI_WEB_PORT}/index.html" "web.log"

echo "QDI sandbox environment initialized successfully."
echo "Backend PID: ${API_PID}; Web PID: ${WEB_PID}"
