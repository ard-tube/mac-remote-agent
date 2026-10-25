#!/usr/bin/env bash
# Start MacRemote Agent in background
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
if [ -f "$DIR/mra" ]; then
    exec "$DIR/mra" start
else
    cd "$DIR"
    nohup python3 "$DIR/agent.py" >> "$DIR/agent.log" 2>&1 &
    echo $! > "$DIR/agent.pid"
    echo "✅ Agent started (PID: $(cat "$DIR/agent.pid"))."
fi
