#!/usr/bin/env bash
# ==============================================================================
# Clamshell & Sleep Mode Configuration for Apple Silicon M-Series Macs
# Compatible with M1, M2, M3, M4 (MacBook Air, MacBook Pro, Mac mini, Mac Studio)
# Controls whether your Mac stays awake when lid is closed on charger
# ==============================================================================

ACTION="${1:-status}"

case "$ACTION" in
    on|enable)
        echo "Configuring Apple Silicon Mac to STAY AWAKE when connected to charger..."
        echo "This disables idle system sleep when plugged into AC power."
        sudo pmset -c sleep 0
        echo ""
        echo "💡 TIP for Apple Silicon Clamshell (Lid closed without external monitor):"
        echo "If you want to keep your MacBook awake with lid closed even without a display, run:"
        echo "   sudo pmset -a disablesleep 1"
        echo "(To turn back to normal: sudo pmset -a disablesleep 0)"
        echo ""
        echo "✅ Current power settings on AC:"
        pmset -g custom | grep -A 10 "AC Power"
        ;;
    off|disable)
        echo "Restoring default sleep settings..."
        sudo pmset -c sleep 1
        sudo pmset -a disablesleep 0
        echo "✅ Defaults restored."
        ;;
    status)
        echo "=== Current Power Management Settings ==="
        pmset -g batt
        echo ""
        pmset -g custom
        ;;
    *)
        echo "Usage: $0 [enable|disable|status]"
        ;;
esac
