#!/usr/bin/env bash
# Lutris pre-launch and post-exit hook for MyWhoosh.
#   mywhoosh-hook.sh start   starts clickbridge in the background
#   mywhoosh-hook.sh stop    stops it again, by PID
# In Lutris: Configure > System options > Pre-launch script: "<path> start"
#            and Post-exit script: "<path> stop".
set -u
STATE="${XDG_STATE_HOME:-$HOME/.local/state}/clickbridge"
PIDFILE="$STATE/clickbridge.pid"
LOG="$STATE/clickbridge.log"
mkdir -p "$STATE"

is_ours() { [ -r "/proc/$1/cmdline" ] && tr '\0' ' ' < "/proc/$1/cmdline" | grep -q 'clickbridge'; }

case "${1:-}" in
start)
    if [ -f "$PIDFILE" ] && is_ours "$(cat "$PIDFILE")"; then exit 0; fi
    # Lutris sets library paths that can break the Python of the tool.
    unset LD_PRELOAD LD_LIBRARY_PATH PYTHONPATH PYTHONHOME
    [ -f "$LOG" ] && mv -f "$LOG" "$LOG.prev"
    setsid nohup clickbridge --backend hyprland >> "$LOG" 2>&1 < /dev/null &
    echo $! > "$PIDFILE"
    ;;
stop)
    if [ -f "$PIDFILE" ]; then
        pid="$(cat "$PIDFILE")"
        is_ours "$pid" && kill "$pid" 2>/dev/null
        rm -f "$PIDFILE"
    fi
    ;;
*)
    echo "usage: $0 start|stop" >&2
    ;;
esac
exit 0
