#!/bin/bash
# Run Chat Demo Script for Airgap SNS
# This script starts the notification server and multiple chat clients in separate terminals

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    echo "tmux is required for this script. Please install it first."
    echo "On Ubuntu/Debian: sudo apt install tmux"
    echo "On macOS with Homebrew: brew install tmux"
    exit 1
fi

# Check for OpenAI API key
if [ -z "$OPENAI_API_KEY" ]; then
    echo "Warning: OPENAI_API_KEY environment variable is not set."
    echo "LLM integration will be disabled. Set it to enable LLM features:"
    echo "export OPENAI_API_KEY=your_api_key_here"
    LLM_ENABLED=false
else
    LLM_ENABLED=true
    echo "LLM integration is enabled (OPENAI_API_KEY is set)"
fi

# Kill any existing tmux session with the same name
if tmux has-session -t "airgap-chat-demo" 2>/dev/null; then
    echo "Killing existing tmux session..."
    tmux kill-session -t "airgap-chat-demo"
    sleep 1
fi

# Create a new tmux session with the server window
SESSION_NAME="airgap-chat-demo"
echo "Creating tmux session: $SESSION_NAME"
tmux new-session -d -s $SESSION_NAME -n "server"

# Function to create a new window
create_window() {
    local window_name=$1
    local command=$2
    
    echo "Creating window: $window_name"
    tmux new-window -t $SESSION_NAME -n "$window_name"
    tmux send-keys -t $SESSION_NAME:"$window_name" "$command" C-m
}

# Authentication key for all clients
AUTH_KEY="demo-key"

# Chat channel
CHANNEL="demo-chat"

# Log files
LOG_DIR="logs"
mkdir -p $LOG_DIR

# Start client 1 with integrated server (LLM provider - only this client needs the API key)
if [ "$LLM_ENABLED" = true ]; then
    # Use environment variable instead of command line argument for API key
    create_window "provider" "echo 'Starting LLM Provider Client with integrated server...' && OPENAI_API_KEY=\"$OPENAI_API_KEY\" python3 chat_app.py --id provider --channel $CHANNEL --auth-key $AUTH_KEY --log-file $LOG_DIR/provider.log --start-server"
else
    create_window "provider" "echo 'Starting Provider Client with integrated server (LLM disabled)...' && python3 chat_app.py --id provider --channel $CHANNEL --auth-key $AUTH_KEY --log-file $LOG_DIR/provider.log --start-server"
fi

# Keep the server window for logs
echo "Setting up server log window..."
tmux send-keys -t $SESSION_NAME:server "echo 'Server is running in the provider client. This window shows logs from previous runs:' && echo '' && tail -f $LOG_DIR/*.log" C-m

# Wait for provider to initialize
sleep 3  # Increased wait time

# Start client 2 (regular client - no API key needed)
create_window "client1" "echo 'Starting Chat Client 1...' && python3 chat_app.py --id client1 --channel $CHANNEL --auth-key $AUTH_KEY --log-file $LOG_DIR/client1.log"

# Start client 3 (simulating different network by using a different host URI)
# In a real scenario, this would be running on a different machine with the actual host IP
create_window "client2" "echo 'Starting Chat Client 2 (different network)...' && python3 chat_app.py --id client2 --channel $CHANNEL --host ws://localhost:9000/ws/ --auth-key $AUTH_KEY --log-file $LOG_DIR/client2.log"

# Start a spectator client (third party that can observe and participate)
create_window "spectator" "echo 'Starting Spectator Client...' && python3 chat_app.py --id spectator --channel $CHANNEL --auth-key $AUTH_KEY --log-file $LOG_DIR/spectator.log"

# Display usage instructions in a separate window
create_window "help" "cat << 'EOF'
=== AIRGAP SNS CHAT DEMO INSTRUCTIONS ===

CHAT COMMANDS:
  - Type a message and press Enter to send it to all clients
  - Type @ai followed by a question to get an AI response (e.g., '@ai what is the weather?')
  - Type /help to see all available commands
  - Type /users to see all connected users
  - Type /history to see message history
  - Type /exit or /quit to exit the chat

REMOTE CONNECTION SETUP:
  To connect from a different machine:
  1. Start the server on the host machine:
     python3 -m uvicorn host:app --host 0.0.0.0 --port 9000
  
  2. On the remote machine, run:
     python3 chat_app.py --id remote-user --channel $CHANNEL --host ws://HOST_IP:9000/ws/ --auth-key $AUTH_KEY
     
     Replace HOST_IP with the IP address of the server machine.
     
  3. For multiple networks, ensure port 9000 is accessible (may require port forwarding)

TMUX NAVIGATION:
  - Ctrl+B N: Next window
  - Ctrl+B P: Previous window
  - Ctrl+B D: Detach from session
  - Ctrl+B [: Enter scroll mode (use arrow keys to scroll, q to exit)

EOF
echo 'Press Enter to continue...'
read"

# Attach to the tmux session - select client1 window if it exists, otherwise server
echo "Attaching to tmux session..."
if tmux list-windows -t $SESSION_NAME | grep -q client1; then
    tmux select-window -t $SESSION_NAME:client1
else
    tmux select-window -t $SESSION_NAME:server
fi

# Attach to the session
tmux attach-session -t $SESSION_NAME

# If we get here, the session was detached
echo "Session detached"

echo "Chat demo environment is running in tmux session '$SESSION_NAME'"
echo "Use 'tmux attach -t $SESSION_NAME' to reconnect if detached"
echo "Use 'Ctrl+B D' to detach from the session"
echo "Use 'tmux kill-session -t $SESSION_NAME' to stop all components"
