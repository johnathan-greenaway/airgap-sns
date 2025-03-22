#!/bin/bash
# Radio-to-Text Demo for Airgap SNS
# This script demonstrates the radio-to-text module by:
# 1. Starting the Airgap SNS server
# 2. Starting a radio-to-text module
# 3. Starting a client that can interact with the radio monitor

# Default settings
FREQUENCY=102.5
MODE="fm"
GAIN=20.0
ENGINE="simulation"
MONITOR_DURATION=0
ENCRYPT=false
ENCRYPT_PASSWORD=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --frequency|--freq)
      FREQUENCY="$2"
      shift 2
      ;;
    --mode)
      MODE="$2"
      shift 2
      ;;
    --gain)
      GAIN="$2"
      shift 2
      ;;
    --engine)
      ENGINE="$2"
      shift 2
      ;;
    --monitor)
      MONITOR_DURATION="$2"
      shift 2
      ;;
    --encrypt)
      ENCRYPT=true
      shift
      ;;
    --encrypt-password)
      ENCRYPT_PASSWORD="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
  echo "Error: tmux is not installed"
  echo "Please install tmux to run this demo"
  echo "Ubuntu/Debian: sudo apt install tmux"
  echo "macOS: brew install tmux"
  exit 1
fi

# Kill any existing tmux session with the same name
tmux kill-session -t airgap-radio-demo 2>/dev/null

# Create a new tmux session
tmux new-session -d -s airgap-radio-demo -n "server" "python -m uvicorn host:app --host 0.0.0.0 --port 9000; read"

# Wait for server to start
sleep 2

# Build the radio command
RADIO_CMD="python airgap_sns/examples/radio_to_text.py --id radio-monitor --freq $FREQUENCY --mode $MODE --gain $GAIN --engine $ENGINE"

# Add optional arguments
if [ "$MONITOR_DURATION" -gt 0 ]; then
  RADIO_CMD="$RADIO_CMD --monitor $MONITOR_DURATION"
fi

if [ "$ENCRYPT" = true ]; then
  RADIO_CMD="$RADIO_CMD --encrypt"
  
  if [ ! -z "$ENCRYPT_PASSWORD" ]; then
    RADIO_CMD="$RADIO_CMD --encrypt-password \"$ENCRYPT_PASSWORD\""
  fi
fi

# Create windows for radio module and client
tmux new-window -t airgap-radio-demo:1 -n "radio" "eval $RADIO_CMD; read"
tmux new-window -t airgap-radio-demo:2 -n "client" "python client.py --id radio-client --interactive; read"

# Create help window
tmux new-window -t airgap-radio-demo:3 -n "help" "cat << EOF
Radio-to-Text Demo for Airgap SNS

This demo monitors radio broadcasts, converts speech to text, and sends the 
transcriptions through the Airgap SNS notification system.

Windows:
1. Server - The Airgap SNS server
2. Radio - The radio-to-text module (frequency: ${FREQUENCY} MHz, mode: ${MODE})
3. Client - A client for interacting with the radio module
4. Help - This help window

Commands to send from client:
- !tune 102.5  - Tune to a frequency (in MHz)
- !mode fm     - Set mode (fm, am, usb, lsb, wfm)
- !gain 20.0   - Set receiver gain
- !monitor 60  - Start monitoring for 60 seconds
- !stop        - Stop monitoring
- !status      - Show current status
- !help        - Show help information

Important Notes:
- Using ${ENGINE} mode for speech recognition
- In simulation mode, simulated speech is generated every 10 seconds
- With real hardware, an SDR device like RTL-SDR is required

Navigation:
- Ctrl+B N: Next window
- Ctrl+B P: Previous window
- Ctrl+B D: Detach from session (keeps it running in background)

To reattach to a detached session:
tmux attach -t airgap-radio-demo

To kill the session:
tmux kill-session -t airgap-radio-demo
EOF
read"

# Attach to the session
tmux attach-session -t airgap-radio-demo

# Clean up when done
tmux kill-session -t airgap-radio-demo 2>/dev/null