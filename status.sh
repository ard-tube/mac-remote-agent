#!/usr/bin/env bash
# Check status of MacRemote Agent
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
if [ -f "$DIR/mra" ]; then
    exec "$DIR/mra" status
else
    PID_FILE="$DIR/agent.pid"
    if [ -f "$PID_FILE" ] && ps -p "$(cat "$PID_FILE")" > /dev/null 2>&1; then
        echo "Status: 🟢 RUNNING (PID: $(cat "$PID_FILE"))"
    else
        echo "Status: 🔴 STOPPED"
    fi
    pmset -g batt
fi
