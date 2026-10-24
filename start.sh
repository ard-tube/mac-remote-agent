#!/usr/bin/env bash
# Start MacRemote Agent in background
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

PID_FILE="$DIR/agent.pid"
LOG_FILE="$DIR/agent.log"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "⚠️ MacRemote Agent is already running (PID: $PID)."
        exit 0
    fi
fi

echo "Starting MacRemote Agent in background..."
nohup python3 "$DIR/agent.py" > "$LOG_FILE" 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"
sleep 1

if ps -p "$NEW_PID" > /dev/null 2>&1; then
    echo "✅ MacRemote Agent is running (PID: $NEW_PID)."
    echo "Logs: tail -f $LOG_FILE"
else
    echo "❌ Failed to start. Check $LOG_FILE:"
    cat "$LOG_FILE"
fi
