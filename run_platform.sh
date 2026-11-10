#!/usr/bin/env bash
set -e

echo "🧹 [0/3] Cleaning up old background processes..."
# Find and kill any zombie process holding port 8000
fuser -k 8000/tcp || true
sleep 1

echo "🚀 [1/3] Starting AquaSentinel-Core FastAPI Backend on Port 8000..."
# Start Uvicorn in the background
uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Give the server 3 seconds to fully boot up before sending data to it
sleep 3

echo "📡 [2/3] Seeding Initial Industrial & Municipal Modbus Telemetry..."
# PYTHONPATH=. forces Python to look in the root folder so it finds 'backend'
PYTHONPATH=. python simulator/modbus_edge_simulator.py

echo "🌐 [3/3] Launching 3D Hydro-Command Center on Port 8501..."
streamlit run frontend/app.py --server.port 8501 --server.address 0.0.0.0

# If you ever press Ctrl+C to stop Streamlit, this line ensures the backend shuts down too
kill $BACKEND_PID