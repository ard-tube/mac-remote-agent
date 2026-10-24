#!/usr/bin/env bash
# Stop MacRemote Agent
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

PID_FILE="$DIR/agent.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "Stopping MacRemote Agent (PID: $PID)..."
        kill "$PID"
        sleep 1
        if ps -p "$PID" > /dev/null 2>&1; then
            kill -9 "$PID"
        fi
        echo "✅ Agent stopped."
    else
        echo "Agent PID $PID was not running."
    fi
    rm -f "$PID_FILE"
else
    # Also find any running python agent.py
    PIDS=$(pgrep -f "mac-remote-agent/agent.py" || true)
    if [ -n "$PIDS" ]; then
        echo "Killing leftover agent processes: $PIDS"
        kill -9 $PIDS
        echo "✅ Agent processes stopped."
    else
        echo "No running MacRemote Agent found."
    fi
fi
