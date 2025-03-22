# Airgap SNS (Secure Notification System)

A complete, fully-functional Python implementation of an extensible, modular notification framework tailored specifically for handling LLM outputs, notifications upon certain triggers, and secure communication between air-gapped devices.

## Features

- **Burst Sequence Parsing**: Detect and parse special notification triggers in text
- **WebSocket Pub/Sub**: Real-time notification delivery via WebSockets
- **Audio Transmission**: Send data between air-gapped devices using sound (via ggwave)
- **Encryption**: Optional AES encryption for secure communication
- **Webhooks**: Integration with external systems via HTTP webhooks
- **Email Notifications**: Monitor email accounts and send notifications for new messages
- **Water-cooler Channels**: Broadcast notifications to groups of subscribers
- **Interactive Client**: Command-line interface for sending and receiving notifications
- **Modular Architecture**: Easily extensible for custom notification types and delivery methods

## Dependencies

```bash
pip install fastapi uvicorn websockets aiohttp python-dotenv cryptography ggwave sounddevice numpy
```

For LLM integration:
```bash
# For OpenAI API
pip install openai

# For Ollama (local LLMs)
pip install httpx
```

For email notification support:
```bash
pip install imaplib2
```

For secure tunnel support (optional):
```bash
pip install zrok
```

Note: 
- `ggwave` and `sounddevice` are optional dependencies for audio transmission features.
- `zrok` is an optional dependency for creating secure tunnels for remote connections.
- `httpx` is required for Ollama integration (local LLMs).
- `imaplib2` is required for email notification features.

## Project Structure

```
.
├── README.md
├── audio.py         # Audio transmission using ggwave
├── burst.py         # Burst sequence parsing
├── client.py        # Notification client
├── crypto.py        # Encryption utilities
├── host.py          # Notification host/server
├── scheduler.py     # Job scheduling
├── webhook.py       # Webhook integration
└── airgap_sns/      # Package structure
    ├── core/        # Core functionality
    ├── client/      # Client implementation
    ├── host/        # Server implementation
    ├── chat/        # Chat application
    ├── email/       # Email notification module
    └── bin/         # Command-line scripts
```

## Burst Sequence Format

Burst sequences are special markers in text that trigger notifications:

```
!!BURST(dest=user123;wc=42;encrypt=yes;webhook=https://example.com/hook;audio=tx;pwd=secret)!!
```

Parameters:
- `dest`: Destination client ID
- `wc`: Water-cooler channel ID
- `encrypt`: Whether to encrypt the message (`yes`/`no`)
- `webhook`: URL to send a webhook notification
- `audio`: Audio transmission (`tx`/`none`)
- `pwd`: Optional password for encryption

## Environment Variables

The system supports configuration via environment variables or a `.env` file. Create a `.env` file in the project root with the following variables:

```
# LLM Provider settings
# Choose between "openai" or "ollama"
LLM_PROVIDER=openai

# OpenAI settings (when LLM_PROVIDER=openai)
OPENAI_API_KEY=your_api_key_here
DEFAULT_MODEL=gpt-3.5-turbo

# Ollama settings (when LLM_PROVIDER=ollama)
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama2
OLLAMA_STREAM=true

# Authentication key for chat clients
AUTH_KEY=demo-key

# Chat channel name
CHANNEL=demo-chat

# Server configuration
HOST=0.0.0.0
PORT=9000

# Enable/disable features
# Set to "true" to enable, anything else to disable
TUNNEL_ENABLED=false
RELOAD_ENABLED=false
```

A sample `.env.sample` file is provided as a template.

## Usage

### Starting the Server

Using the provided script:
```bash
# Make the script executable
chmod +x run_server.sh

# Start the server
./run_server.sh

# Start with secure tunnel for remote connections
./run_server.sh --tunnel-on

# Start with auto-reload for development
./run_server.sh --reload
```

Or manually:
```bash
uvicorn host:app --host 0.0.0.0 --port 9000
```

### Running the Client

Basic usage:
```bash
python client.py --id user123
```

With interactive mode:
```bash
python client.py --id user123 --interactive
```

With password for decryption:
```bash
python client.py --id user123 --password mysecretpassword
```

Disable audio features:
```bash
python client.py --id user123 --no-audio
```

### Interactive Client Commands

- `/quit` - Exit the client
- `/audio <message>` - Send message via audio
- `/burst dest=<id>;wc=<channel>;...` - Send custom burst
- `/help` - Show help

## Testing the System

The project includes several test scripts to verify functionality:

### Quick Demo

For a quick demonstration of the system, use the provided shell scripts:

#### Basic Demo
```bash
# Make the script executable (if not already)
chmod +x run_demo.sh

# Run the demo
./run_demo.sh
```

This script uses tmux to start multiple components in separate windows:
- Notification server
- Webhook test server
- Receiver client (interactive mode)
- Sender client (interactive mode)

#### Chat Demo
```bash
# Make the script executable (if not already)
chmod +x run_chat_demo.sh

# Run the chat demo
./run_chat_demo.sh

# Run with secure tunnel for remote connections
./run_chat_demo.sh --tunnel-on
```

This script starts a multi-user chat environment with:
- Notification server
- LLM provider client (if OpenAI API key is set)
- Multiple chat clients
- Help window with instructions

You can then interact with the system by sending messages between clients.

#### Email Notification Demo
```bash
# Using the Python module
python -m airgap_sns.bin.run_email_demo --email user@example.com --password mypassword

# Or using the console script
airgap-sns-email-demo --email user@example.com --password mypassword
```

This script starts:
- Notification server
- Client listening to email notifications
- Email notification module that monitors your inbox

You'll receive notifications in the client window whenever new emails arrive.

### Automated Tests

Run the automated test suite to verify core functionality:

```bash
# Start the server in one terminal
uvicorn host:app --host 0.0.0.0 --port 9000

# Run the tests in another terminal
python test_sns.py

# Include audio tests (requires ggwave and sounddevice)
python test_sns.py --test-audio

# Include webhook tests (requires webhook_test_server.py running)
python test_sns.py --test-webhook
```

### Webhook Testing

To test webhook functionality, run the webhook test server:

```bash
# Start the webhook test server
python webhook_test_server.py --port 8000

# View received webhooks
curl http://localhost:8000/webhooks
```

### LLM Integration Demo

Test integration with LLMs using the demo script:

```bash
# For OpenAI:
export LLM_PROVIDER=openai
export OPENAI_API_KEY=your_api_key_here
export DEFAULT_MODEL=gpt-3.5-turbo

# OR for Ollama (local LLMs):
export LLM_PROVIDER=ollama
export OLLAMA_MODEL=llama2
export OLLAMA_URL=http://localhost:11434

# Run the LLM integration demo
python llm_integration_demo.py
```

For the chat demo with Ollama:
```bash
# Make sure Ollama is running
ollama serve

# Run the chat demo with Ollama
export LLM_PROVIDER=ollama
./run_chat_demo.sh
```

## Integration with LLMs

LLMs can be instructed to include burst sequences in their output to trigger notifications:

```
Here's your answer: The capital of France is Paris.

!!BURST(dest=user123;wc=geography;encrypt=no)!!
```

## Audio Transmission

The system can transmit data between air-gapped devices using sound:

```bash
# Send a message via audio
python client.py --id sender --interactive
> /audio Hello from an air-gapped device!
```

## Secure Tunnel for Remote Connections

The system supports creating secure tunnels for remote connections using zrok:

1. Install zrok:
   ```bash
   pip install zrok
   ```

2. Configure zrok (first time only):
   ```bash
   zrok login
   ```

3. Start the server or chat demo with tunnel enabled:
   ```bash
   ./run_server.sh --tunnel-on
   # or
   ./run_chat_demo.sh --tunnel-on
   ```

4. The tunnel URL will be displayed and saved to `tunnel_connection.txt`

5. On the remote machine, connect using the tunnel URL:
   ```bash
   python client.py --id remote-user --uri <TUNNEL_URL>
   # or for chat demo
   python chat_app.py --id remote-user --channel demo-chat --host <TUNNEL_URL> --auth-key demo-key
   ```

## Security Considerations

- All WebSocket connections should be secured with TLS in production
- Passwords for encryption should be strong and securely managed
- Audio transmission is susceptible to eavesdropping in shared spaces
- When using secure tunnels, ensure you trust the tunnel provider

## Example Use Cases

1. **LLM Notifications**: Get notified when an LLM completes a task or needs input
2. **Air-gapped Communication**: Transfer data between isolated systems
3. **Secure Messaging**: Send encrypted messages to specific recipients
4. **Broadcast Alerts**: Notify groups of users about important events
5. **Webhook Integration**: Trigger external systems based on notifications
6. **Email Monitoring**: Get notified when important emails arrive in your inbox

## License

MIT
