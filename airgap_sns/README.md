# Airgap SNS - Secure Notification System

A secure notification system with audio capabilities, webhooks, and encryption.

## Features

- Real-time notifications via WebSockets
- Audio transmission capabilities using sound waves (via ggwave)
- End-to-end encryption
- Webhook integration
- Chat application with LLM integration
- Secure tunneling for remote connections

## Installation

```bash
# Basic installation
pip install airgap_sns

# With audio support
pip install airgap_sns[audio]

# With chat and LLM support
pip install airgap_sns[chat]

# With secure tunneling support
pip install airgap_sns[tunnel]

# Full installation with all features
pip install airgap_sns[audio,chat,tunnel]
```

## Quick Start

### Running the Host Server

```bash
# Using the command-line script
airgap-sns-host

# Or from Python
from airgap_sns.host import run_server
run_server()
```

### Running a Client

```bash
# Using the command-line script
airgap-sns-client --id client1 --uri ws://localhost:9000/ws/

# Or from Python
from airgap_sns.client import NotificationClient
import asyncio

async def main():
    client = NotificationClient(uri="ws://localhost:9000/ws/", client_id="client1")
    await client.connect()
    # Send and receive messages...
    await client.close()

asyncio.run(main())
```

### Running the Chat Application

```bash
# Using the command-line script
airgap-sns-chat --id user1 --start-server

# Or from Python
from airgap_sns.chat import run_chat_app
run_chat_app()
```

## Modules

- **core**: Core functionality used by both host and client
  - **burst**: Burst message parsing and formatting
  - **crypto**: Encryption and decryption utilities
  - **webhook**: Webhook integration
  - **audio**: Audio transmission and reception
  - **scheduler**: Job scheduling for notifications

- **host**: Server functionality
  - **server**: WebSocket server implementation

- **client**: Client functionality
  - **client**: WebSocket client implementation

- **chat**: Chat application
  - **app**: Chat client implementation with LLM integration

## License

MIT
