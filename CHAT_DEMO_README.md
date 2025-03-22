# Airgap SNS Chat Demo

This is a demonstration of a secure notification system (SNS) chat application that allows users to communicate across different networks, even with limited connectivity.

## Features

- Real-time chat using WebSocket connections
- LLM integration (AI assistant) using OpenAI API or Ollama
- Cross-network communication
- Simple authentication system
- Chat logging
- Support for multiple clients

## Prerequisites

- Python 3.7+
- tmux (for the demo script)
- Required Python packages:
  - fastapi
  - uvicorn
  - websockets
  - openai (optional, for OpenAI LLM integration)
  - httpx (optional, for Ollama LLM integration)
  - pydantic

For Ollama integration:
- Ollama installed and running (https://ollama.com)
- A downloaded model (e.g., llama2)

## Installation

1. Ensure you have Python 3 installed:
   ```bash
   python3 --version
   ```

2. Install required packages:
   ```bash
   pip3 install fastapi uvicorn websockets pydantic
   
   # For OpenAI integration
   pip3 install openai
   
   # For Ollama integration
   pip3 install httpx
   ```

3. Install tmux if not already installed:
   - Ubuntu/Debian: `sudo apt install tmux`
   - macOS with Homebrew: `brew install tmux`

## Running the Demo

### Quick Start

1. Make the script executable:
   ```bash
   chmod +x run_chat_demo.sh
   ```

2. Configure LLM provider:

   For OpenAI:
   ```bash
   export LLM_PROVIDER=openai
   export OPENAI_API_KEY=your_api_key_here
   export DEFAULT_MODEL=gpt-3.5-turbo
   ```

   For Ollama:
   ```bash
   export LLM_PROVIDER=ollama
   export OLLAMA_MODEL=llama2
   export OLLAMA_URL=http://localhost:11434
   ```

3. Run the demo script:
   ```bash
   ./run_chat_demo.sh
   ```

The script will:
- Start a notification server
- Create multiple chat clients in separate tmux windows
- Provide a help window with usage instructions

### Using the Chat

Once the demo is running:

1. You'll be automatically connected to the `client1` window
2. Type a message and press Enter to send it to all clients
3. Use special commands:
   - Type `@ai` followed by a question to get an AI response (e.g., `@ai what is the weather?`)
   - Type `/help` to see all available commands
   - Type `/users` to see all connected users
   - Type `/history` to see message history
   - Type `/exit` or `/quit` to exit the chat

### Navigating tmux

- `Ctrl+B N`: Next window
- `Ctrl+B P`: Previous window
- `Ctrl+B D`: Detach from session (keeps it running in background)
- `Ctrl+B [`: Enter scroll mode (use arrow keys to scroll, `q` to exit)

To reattach to a detached session:
```bash
tmux attach -t airgap-chat-demo
```

To kill the session:
```bash
tmux kill-session -t airgap-chat-demo
```

## Remote Connection Setup

To connect from a different machine, you have two options:

### Option 1: Using Secure Tunnel (Recommended)

This method creates a secure tunnel that works across different networks without port forwarding:

1. On the host machine, run the demo with the tunnel flag:
   ```bash
   ./run_chat_demo.sh --tunnel-on
   ```
   
   This will create a secure tunnel and save the connection URL to `tunnel_connection.txt`.

2. On the remote machine, run:
   ```bash
   python3 chat_app.py --id remote-user --channel demo-chat --host <TUNNEL_URL> --auth-key demo-key
   ```
   
   Replace `<TUNNEL_URL>` with the URL from `tunnel_connection.txt`.

3. No port forwarding or IP configuration needed!

### Option 2: Direct Connection

This method requires both machines to be on the same network or have proper port forwarding:

1. Start the server on the host machine using one of these methods:
   
   **Option A:** Start a standalone server:
   ```bash
   python3 -m uvicorn host:app --host 0.0.0.0 --port 9000
   ```
   
   **Option B:** Start a client with integrated server:
   ```bash
   python3 chat_app.py --id host-client --channel demo-chat --auth-key demo-key --start-server
   ```

2. On the remote machine, run:
   ```bash
   python3 chat_app.py --id remote-user --channel demo-chat --host ws://HOST_IP:9000/ws/ --auth-key demo-key
   ```
   
   Replace `HOST_IP` with the IP address of the server machine.

3. For multiple networks, ensure port 9000 is accessible (may require port forwarding on your router)

## Troubleshooting

### Connection Issues

1. **Server not starting**: 
   - Ensure port 9000 is not in use by another application
   - Check for Python version compatibility (use Python 3.7+)
   - Verify all dependencies are installed

2. **Clients can't connect**:
   - Ensure the server is running
   - Check that the host address is correct
   - Verify the WebSocket URI format (should be `ws://host:port/ws/`)
   - Ensure the authentication key matches between server and clients

3. **Cross-network issues**:
   - Check that the server's IP is accessible from the client network
   - Ensure port 9000 is open in any firewalls
   - For public networks, you may need to set up port forwarding

### LLM Integration Issues

1. **OpenAI responses not working**:
   - Verify your OpenAI API key is set correctly
   - Ensure at least one client has the API key (provider client)
   - Check the logs for any API errors

2. **Ollama responses not working**:
   - Ensure Ollama is running (`ollama serve`)
   - Verify the model is downloaded (`ollama pull llama2`)
   - Check that OLLAMA_URL is set correctly
   - Verify the OLLAMA_MODEL exists in your Ollama installation

## Advanced Usage

### Secure Tunnel for Remote Access

To enable the secure tunnel for remote connections:

```bash
# When running the demo script
./run_chat_demo.sh --tunnel-on

# When running a standalone client with server
python3 chat_app.py --id host-client --channel demo-chat --auth-key demo-key --start-server --tunnel-on
```

The secure tunnel requires the `zrok` package, which will be automatically installed if missing. You'll need to run `zrok login` to configure your account the first time.

### Custom Authentication

Change the default authentication key:
```bash
AUTH_KEY="your-secure-key" ./run_chat_demo.sh
```

If you experience authentication issues, you can force re-authentication from within the chat client:
```
/auth
```

### Custom Channel

Change the default chat channel:
```bash
CHANNEL="your-channel-name" ./run_chat_demo.sh
```

### Running Individual Components

To run just the server:
```bash
python3 -m uvicorn host:app --host 0.0.0.0 --port 9000
```

To run a client with integrated server:
```bash
python3 chat_app.py --id your-id --channel demo-chat --auth-key demo-key --start-server
```

To run a regular client:
```bash
python3 chat_app.py --id your-id --channel demo-chat --auth-key demo-key
```

## Architecture

The chat demo consists of several components:

1. **Notification Server** (`host.py`): Handles WebSocket connections and message routing
2. **Chat Application** (`chat_app.py`): User interface and message handling
3. **Client Library** (`client.py`): Core client functionality for connecting to the server
4. **Burst Message System** (`burst.py`): Parses and formats special message formats

Messages are sent using a special "burst" format that includes routing information and other metadata.
