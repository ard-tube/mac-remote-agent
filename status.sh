#!/usr/bin/env bash
# Check status of MacRemote Agent
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

PID_FILE="$DIR/agent.pid"
LOG_FILE="$DIR/agent.log"

echo "=== MacRemote Agent Status ==="
if [ -f "$PID_FILE" ] && ps -p "$(cat "$PID_FILE")" > /dev/null 2>&1; then
    echo "Status: 🟢 RUNNING (PID: $(cat "$PID_FILE"))"
else
    # Check pgrep
    PIDS=$(pgrep -f "mac-remote-agent/agent.py" || true)
    if [ -n "$PIDS" ]; then
        echo "Status: 🟢 RUNNING (PIDs: $PIDS)"
    else
        echo "Status: 🔴 STOPPED"
    fi
fi

echo ""
echo "=== Power / Charger Status ==="
pmset -g batt
echo ""

if [ -f "$LOG_FILE" ]; then
    echo "=== Recent Logs (Last 15 lines) ==="
    tail -n 15 "$LOG_FILE"
fi
