#!/bin/bash
# Email Notification Demo for Airgap SNS
# This script demonstrates the email notification module by:
# 1. Starting the Airgap SNS server
# 2. Starting a client that listens to the email notification stream
# 3. Starting the email notification module

# Default settings
EMAIL=""
PASSWORD=""
IMAP_SERVER="imap.gmail.com"
IMAP_PORT=993
CHECK_INTERVAL=30
STREAM_ID="email-notifications"
CLIENT_ID="email-demo"
FILTER_SENDER=""
FILTER_SUBJECT=""
ENCRYPT=false
ENCRYPT_PASSWORD=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --email)
      EMAIL="$2"
      shift 2
      ;;
    --password)
      PASSWORD="$2"
      shift 2
      ;;
    --imap-server)
      IMAP_SERVER="$2"
      shift 2
      ;;
    --imap-port)
      IMAP_PORT="$2"
      shift 2
      ;;
    --interval)
      CHECK_INTERVAL="$2"
      shift 2
      ;;
    --stream)
      STREAM_ID="$2"
      shift 2
      ;;
    --filter-sender)
      FILTER_SENDER="$2"
      shift 2
      ;;
    --filter-subject)
      FILTER_SUBJECT="$2"
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

# Check if required arguments are provided
if [ -z "$EMAIL" ] || [ -z "$PASSWORD" ]; then
  echo "Error: Email and password are required"
  echo "Usage: $0 --email user@example.com --password mypassword [options]"
  echo "Options:"
  echo "  --email EMAIL               Email address to monitor"
  echo "  --password PASSWORD         Email password"
  echo "  --imap-server SERVER        IMAP server (default: imap.gmail.com)"
  echo "  --imap-port PORT            IMAP port (default: 993)"
  echo "  --interval SECONDS          Check interval in seconds (default: 30)"
  echo "  --stream STREAM_ID          Stream ID for notifications (default: email-notifications)"
  echo "  --filter-sender SENDER      Filter emails by sender"
  echo "  --filter-subject SUBJECT    Filter emails by subject"
  echo "  --encrypt                   Encrypt notifications"
  echo "  --encrypt-password PASSWORD Password for encryption"
  exit 1
fi

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
  echo "Error: tmux is not installed"
  echo "Please install tmux to run this demo"
  echo "Ubuntu/Debian: sudo apt install tmux"
  echo "macOS: brew install tmux"
  exit 1
fi

# Kill any existing tmux session with the same name
tmux kill-session -t airgap-email-demo 2>/dev/null

# Create a new tmux session
tmux new-session -d -s airgap-email-demo -n "server" "python -m uvicorn host:app --host 0.0.0.0 --port 9000; read"

# Wait for server to start
sleep 2

# Create a window for the client
tmux new-window -t airgap-email-demo:1 -n "client" "python client.py --id $CLIENT_ID --interactive; read"

# Build the email notification command
EMAIL_CMD="python email_notification.py --email \"$EMAIL\" --password \"$PASSWORD\" --imap-server \"$IMAP_SERVER\" --imap-port $IMAP_PORT --interval $CHECK_INTERVAL --stream \"$STREAM_ID\" --client-id \"$CLIENT_ID\""

# Add optional arguments
if [ ! -z "$FILTER_SENDER" ]; then
  EMAIL_CMD="$EMAIL_CMD --filter-sender \"$FILTER_SENDER\""
fi

if [ ! -z "$FILTER_SUBJECT" ]; then
  EMAIL_CMD="$EMAIL_CMD --filter-subject \"$FILTER_SUBJECT\""
fi

if [ "$ENCRYPT" = true ]; then
  EMAIL_CMD="$EMAIL_CMD --encrypt"
  
  if [ ! -z "$ENCRYPT_PASSWORD" ]; then
    EMAIL_CMD="$EMAIL_CMD --encrypt-password \"$ENCRYPT_PASSWORD\""
  fi
fi

# Create a window for the email notification module
tmux new-window -t airgap-email-demo:2 -n "email" "eval $EMAIL_CMD; read"

# Create a help window
tmux new-window -t airgap-email-demo:3 -n "help" "cat << EOF
Email Notification Demo for Airgap SNS

This demo is running with the following configuration:
- Email: $EMAIL
- IMAP Server: $IMAP_SERVER:$IMAP_PORT
- Check Interval: $CHECK_INTERVAL seconds
- Stream ID: $STREAM_ID
- Client ID: $CLIENT_ID
$([ ! -z "$FILTER_SENDER" ] && echo "- Filter Sender: $FILTER_SENDER")
$([ ! -z "$FILTER_SUBJECT" ] && echo "- Filter Subject: $FILTER_SUBJECT")
$([ "$ENCRYPT" = true ] && echo "- Encryption: Enabled")

Windows:
1. Server - The Airgap SNS server
2. Client - A client listening to the email notification stream
3. Email - The email notification module
4. Help - This help window

Navigation:
- Ctrl+B N: Next window
- Ctrl+B P: Previous window
- Ctrl+B D: Detach from session (keeps it running in background)
- Ctrl+B [: Enter scroll mode (use arrow keys to scroll, q to exit)

To reattach to a detached session:
tmux attach -t airgap-email-demo

To kill the session:
tmux kill-session -t airgap-email-demo

EOF
read"

# Switch to the client window
tmux select-window -t airgap-email-demo:1

# Attach to the session
tmux attach-session -t airgap-email-demo

# Clean up when done
tmux kill-session -t airgap-email-demo 2>/dev/null
