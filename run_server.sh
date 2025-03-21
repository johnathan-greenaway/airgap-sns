#!/bin/bash
# Run Server Script for Airgap SNS
# This script starts the notification server with optional secure tunnel

# Process command line arguments
TUNNEL_ENABLED=false
RELOAD_ENABLED=false
PORT=9000
HOST="0.0.0.0"

# Parse arguments
for arg in "$@"; do
    case $arg in
        --tunnel-on)
            TUNNEL_ENABLED=true
            shift # Remove --tunnel-on from processing
            ;;
        --reload)
            RELOAD_ENABLED=true
            shift # Remove --reload from processing
            ;;
        --port=*)
            PORT="${arg#*=}"
            shift # Remove --port=value from processing
            ;;
        --host=*)
            HOST="${arg#*=}"
            shift # Remove --host=value from processing
            ;;
        *)
            # Unknown option
            ;;
    esac
done

# Check if zrok is installed if tunnel is enabled
if [ "$TUNNEL_ENABLED" = true ]; then
    if ! pip3 list | grep -q zrok; then
        echo "Secure tunnel requested but zrok package is not installed."
        echo "Installing zrok package..."
        pip3 install zrok
        
        # Check if installation was successful
        if ! pip3 list | grep -q zrok; then
            echo "Failed to install zrok. Continuing without secure tunnel."
            TUNNEL_ENABLED=false
        else
            echo "zrok installed successfully."
            
            # Check if zrok is configured
            if ! zrok status &>/dev/null; then
                echo "zrok is not configured. Please run 'zrok login' manually."
                echo "Continuing without secure tunnel."
                TUNNEL_ENABLED=false
            fi
        fi
    fi
fi

# Build command
CMD="python3 host.py --host $HOST --port $PORT"

if [ "$TUNNEL_ENABLED" = true ]; then
    CMD="$CMD --tunnel-on"
    echo "Secure tunnel enabled. Remote connections will be possible."
fi

if [ "$RELOAD_ENABLED" = true ]; then
    CMD="$CMD --reload"
    echo "Auto-reload enabled for development."
fi

# Run the server
echo "Starting Airgap SNS Notification Server on $HOST:$PORT"
echo "Press Ctrl+C to stop the server"
echo "========================================"
eval $CMD

# If we get here, the server was stopped
echo "Server stopped"
