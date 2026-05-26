#!/bin/bash
set -e

echo "=== APIWatcher Development Environment Setup ==="
echo ""

# Get the directory where this script lives
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
echo "✓ Dependencies installed"

# Create database directory if needed
mkdir -p data
echo "✓ Database directory ready"

# Stop any existing services on ports 8000 and 8501
echo "Checking for existing services..."
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "Stopping existing FastAPI service on port 8000..."
    kill $(lsof -t -i:8000) 2>/dev/null || true
fi

if lsof -Pi :8501 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "Stopping existing Streamlit service on port 8501..."
    kill $(lsof -t -i:8501) 2>/dev/null || true
fi

sleep 2

# Start FastAPI service in background
echo ""
echo "Starting FastAPI service on port 8000..."
nohup uvicorn watcher.api:app --host 0.0.0.0 --port 8000 --reload > logs/fastapi.log 2>&1 &
FASTAPI_PID=$!
echo "FastAPI PID: $FASTAPI_PID"

# Start Streamlit dashboard in background
echo "Starting Streamlit dashboard on port 8501..."
mkdir -p logs
nohup streamlit run watcher/dashboard.py --server.port 8501 --server.headless true > logs/streamlit.log 2>&1 &
STREAMLIT_PID=$!
echo "Streamlit PID: $STREAMLIT_PID"

# Wait for services to be ready
echo ""
echo "Waiting for services to start..."
sleep 5

# Check FastAPI health
echo "Checking FastAPI health..."
for i in {1..10}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "✓ FastAPI is ready"
        break
    fi
    if [ $i -eq 10 ]; then
        echo "⚠ FastAPI health check failed after 10 attempts"
    fi
    sleep 1
done

# Check Streamlit
echo "Checking Streamlit..."
for i in {1..10}; do
    if curl -s http://localhost:8501 > /dev/null 2>&1; then
        echo "✓ Streamlit is ready"
        break
    fi
    if [ $i -eq 10 ]; then
        echo "⚠ Streamlit health check failed after 10 attempts"
    fi
    sleep 1
done

echo ""
echo "=== APIWatcher is running! ==="
echo ""
echo "Services:"
echo "  • FastAPI service:  http://localhost:8000"
echo "  • FastAPI docs:     http://localhost:8000/docs"
echo "  • Streamlit dashboard: http://localhost:8501"
echo ""
echo "Logs:"
echo "  • FastAPI:  tail -f logs/fastapi.log"
echo "  • Streamlit: tail -f logs/streamlit.log"
echo ""
echo "Process IDs:"
echo "  • FastAPI:  $FASTAPI_PID"
echo "  • Streamlit: $STREAMLIT_PID"
echo ""
echo "To stop services:"
echo "  kill $FASTAPI_PID $STREAMLIT_PID"
echo ""
