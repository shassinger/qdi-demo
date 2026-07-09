#!/bin/bash
# Clean up any existing instances
pkill -f qdi_demo_server || true
pkill -f "http.server 3000" || true

# Compile the QDI C-ABI mock shared library inside the container
echo "Compiling QDI C-ABI mock library..."
clang++ -shared -o qdi-core/libqdi_mock.so -Iqdi-core/include qdi-core/src/qdi_mock.cpp -std=c++17 -fPIC

# Start backend API server in background with fully detached streams
echo "Starting FastAPI Server..."
nohup python3 qdi-core/python/qdi_demo_server.py < /dev/null > server.log 2>&1 &

# Start static web server in background with fully detached streams
echo "Starting Web Console Server..."
nohup python3 -m http.server 3000 --bind 0.0.0.0 --directory qdi-core/python < /dev/null > web.log 2>&1 &

echo "QDI sandbox environment initialized successfully."
