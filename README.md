# Airgap SNS (Secure Notification System)

A complete, fully-functional Python implementation of an extensible, modular notification framework tailored specifically for handling LLM outputs, notifications upon certain triggers, and secure communication between air-gapped devices.

## Features

- **Burst Sequence Parsing**: Detect and parse special notification triggers in text
- **WebSocket Pub/Sub**: Real-time notification delivery via WebSockets
- **Audio Transmission**: Send data between air-gapped devices using sound (via ggwave)
- **Encryption**: Optional AES encryption for secure communication
- **Webhooks**: Integration with external systems via HTTP webhooks
- **Water-cooler Channels**: Broadcast notifications to groups of subscribers
- **Interactive Client**: Command-line interface for sending and receiving notifications
- **Modular Architecture**: Easily extensible for custom notification types and delivery methods

## Dependencies

```bash
pip install fastapi uvicorn websockets aiohttp python-dotenv cryptography ggwave sounddevice numpy
```

Note: `ggwave` and `sounddevice` are optional dependencies for audio transmission features.

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
└── webhook.py       # Webhook integration
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

## Usage

### Starting the Server

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

For a quick demonstration of the system, use the provided shell script:

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

You can then interact with the system by sending messages between clients.

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
# Set your OpenAI API key
export OPENAI_API_KEY=your_api_key_here

# Run the LLM integration demo
python llm_integration_demo.py
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

## Security Considerations

- All WebSocket connections should be secured with TLS in production
- Passwords for encryption should be strong and securely managed
- Audio transmission is susceptible to eavesdropping in shared spaces

## Example Use Cases

1. **LLM Notifications**: Get notified when an LLM completes a task or needs input
2. **Air-gapped Communication**: Transfer data between isolated systems
3. **Secure Messaging**: Send encrypted messages to specific recipients
4. **Broadcast Alerts**: Notify groups of users about important events
5. **Webhook Integration**: Trigger external systems based on notifications

## License

MIT
