#!/bin/bash
# Run Demo Script for Airgap SNS
# This script starts all the necessary components for testing the notification system

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    echo "tmux is required for this script. Please install it first."
    echo "On Ubuntu/Debian: sudo apt install tmux"
    echo "On macOS with Homebrew: brew install tmux"
    exit 1
fi

# Create a new tmux session
SESSION_NAME="airgap-sns-demo"
tmux new-session -d -s $SESSION_NAME

# Function to create a new window
create_window() {
    local window_name=$1
    local command=$2
    
    tmux new-window -t $SESSION_NAME -n "$window_name"
    tmux send-keys -t $SESSION_NAME:"$window_name" "$command" C-m
}

# Start the notification server
create_window "server" "echo 'Starting Notification Server...' && uvicorn host:app --host 0.0.0.0 --port 9000"

# Wait for server to start
echo "Waiting for server to start..."
sleep 3

# Start the webhook test server
create_window "webhook" "echo 'Starting Webhook Test Server...' && python webhook_test_server.py --port 8000"

# Start a receiver client
create_window "receiver" "echo 'Starting Receiver Client...' && python client.py --id receiver --interactive"

# Start a sender client
create_window "sender" "echo 'Starting Sender Client...' && python client.py --id sender --interactive"

# Attach to the tmux session
tmux select-window -t $SESSION_NAME:server
tmux attach-session -t $SESSION_NAME

echo "Demo environment is running in tmux session '$SESSION_NAME'"
echo "Use 'tmux attach -t $SESSION_NAME' to reconnect if detached"
echo "Use 'Ctrl+B D' to detach from the session"
echo "Use 'tmux kill-session -t $SESSION_NAME' to stop all components"
