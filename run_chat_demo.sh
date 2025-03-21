#!/bin/bash
# Run Chat Demo Script for Airgap SNS
# This script starts the notification server and multiple chat clients in separate terminals

# Process command line arguments
TUNNEL_ENABLED=false
for arg in "$@"; do
    case $arg in
        --tunnel-on)
            TUNNEL_ENABLED=true
            shift # Remove --tunnel-on from processing
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

# Check if OpenAI API key is valid
if [ "$LLM_ENABLED" = true ]; then
    echo "Verifying OpenAI API key..."
    if [[ -z "$OPENAI_API_KEY" || "$OPENAI_API_KEY" == "your_api_key_here" ]]; then
        echo "Warning: OPENAI_API_KEY appears to be invalid or not set properly."
        echo "LLM integration will be disabled."
        LLM_ENABLED=false
    else
        echo "OpenAI API key is set and appears valid."
    fi
fi

# Start client 1 with integrated server (LLM provider - only this client needs the API key)
TUNNEL_FLAG=""
if [ "$TUNNEL_ENABLED" = true ]; then
    TUNNEL_FLAG="--tunnel-on"
    echo "Secure tunnel enabled. Remote connections will be possible."
fi

if [ "$LLM_ENABLED" = true ]; then
    # Use environment variable instead of command line argument for API key
    create_window "provider" "echo 'Starting LLM Provider Client with integrated server...' && OPENAI_API_KEY=\"$OPENAI_API_KEY\" python3 chat_app.py --id provider --channel $CHANNEL --auth-key $AUTH_KEY --log-file $LOG_DIR/provider.log --start-server --llm-model gpt-3.5-turbo $TUNNEL_FLAG"
    
    # Print confirmation that LLM is enabled
    echo "LLM provider started with API key. AI responses should work."
else
    create_window "provider" "echo 'Starting Provider Client with integrated server (LLM disabled)...' && python3 chat_app.py --id provider --channel $CHANNEL --auth-key $AUTH_KEY --log-file $LOG_DIR/provider.log --start-server $TUNNEL_FLAG"
    
    # Print warning that LLM is disabled
    echo "Warning: LLM integration is disabled. AI responses will not work."
    echo "To enable LLM integration, set the OPENAI_API_KEY environment variable:"
    echo "export OPENAI_API_KEY=your_api_key_here"
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
if [ "$TUNNEL_ENABLED" = true ]; then
    # Instructions with tunnel info
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
  A secure tunnel has been created for remote connections.
  
  1. Check the tunnel_connection.txt file for the connection URL
  
  2. On the remote machine, run:
     python3 chat_app.py --id remote-user --channel $CHANNEL --host <TUNNEL_URL> --auth-key $AUTH_KEY
     
     Replace <TUNNEL_URL> with the URL from tunnel_connection.txt
     
  3. No port forwarding or IP configuration needed!

TMUX NAVIGATION:
  - Ctrl+B N: Next window
  - Ctrl+B P: Previous window
  - Ctrl+B D: Detach from session
  - Ctrl+B [: Enter scroll mode (use arrow keys to scroll, q to exit)
EOF
echo 'Press Enter to continue...'
read
"
else
    # Standard instructions
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
  
  TIP: Run with --tunnel-on flag to create a secure tunnel for easier remote connections:
      ./run_chat_demo.sh --tunnel-on

TMUX NAVIGATION:
  - Ctrl+B N: Next window
  - Ctrl+B P: Previous window
  - Ctrl+B D: Detach from session
  - Ctrl+B [: Enter scroll mode (use arrow keys to scroll, q to exit)
EOF
echo 'Press Enter to continue...'
read
"
fi

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
