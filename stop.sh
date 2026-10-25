#!/usr/bin/env bash
# Stop MacRemote Agent and all child processes
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
if [ -f "$DIR/mra" ]; then
    exec "$DIR/mra" stop
else
    # Fallback cleanup
    pkill -f "caffeinate -s -i -m" 2>/dev/null || true
    if [ -f "$DIR/agent.pid" ]; then
        PID=$(cat "$DIR/agent.pid" 2>/dev/null || true)
        [ -n "$PID" ] && kill -9 "$PID" 2>/dev/null || true
        rm -f "$DIR/agent.pid"
    fi
    pkill -f "agent\.py" 2>/dev/null || true
    echo "✅ Agent stopped."
fi
