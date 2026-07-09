#!/bin/bash
# Clean up any existing instances
pkill -f qdi_demo_server || true
pkill -f "http.server 3000" || true

# Start backend API server in background with fully detached streams
nohup python3 qdi-core/python/qdi_demo_server.py < /dev/null > server.log 2>&1 &

# Start static web server in background with fully detached streams
nohup python3 -m http.server 3000 --bind 0.0.0.0 --directory qdi-core/python < /dev/null > web.log 2>&1 &

echo "QDI servers launched successfully."
