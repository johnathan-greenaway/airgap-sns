#!/usr/bin/env python3
"""
Demonstration Chat Application using Airgap SNS

This application demonstrates how to use the Airgap SNS notification system
to create a chat application where users can communicate with both an LLM
and other users, even across different networks.

Features:
- Real-time chat using the Airgap SNS notification system
- LLM integration (only one user needs an API key)
- Simple key authentication
- Chat logging
- Cross-network communication

Usage:
    python chat_app.py --id <client_id> [--host <host_uri>] [--llm-api-key <api_key>] [--auth-key <key>] [--log-file <file>]
"""

import asyncio
import argparse
import logging
import os
import sys
import json
import re
import time
import hashlib
import threading
import socket
from typing import Dict, Any, List, Optional, Set, Tuple
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("airgap-sns-chat")

# Check if required modules are installed
try:
    import openai
    import uvicorn
    from client import NotificationClient
    from burst import parse_burst
except ImportError as e:
    logger.error(f"Required module not found: {e}")
    logger.error("Please install required modules: pip install openai uvicorn")
    sys.exit(1)

# Default settings
DEFAULT_URI = "ws://localhost:9000/ws/"
DEFAULT_CHANNEL = "chat-room"
DEFAULT_MODEL = "gpt-3.5-turbo"
DEFAULT_LOG_FILE = "chat_log.txt"
DEFAULT_AUTH_KEY = "demo-key"  # Default auth key (should be changed in production)
DEFAULT_SERVER_PORT = 9000
DEFAULT_SYSTEM_PROMPT = """
You are a helpful assistant in a group chat. You can see messages from multiple users and respond to them.
Keep your responses concise and helpful. If you're not sure about something, it's okay to say so.
"""

# Message types
MSG_TYPE_CHAT = "chat"
MSG_TYPE_SYSTEM = "system"
MSG_TYPE_LLM_REQUEST = "llm_request"
MSG_TYPE_LLM_RESPONSE = "llm_response"
MSG_TYPE_AUTH = "auth"
MSG_TYPE_AUTH_RESPONSE = "auth_response"

# Server process
server_process = None

class ChatMessage:
    """Represents a chat message"""
    
    def __init__(self, sender: str, content: str, timestamp: Optional[float] = None, is_llm: bool = False):
        """Initialize a chat message"""
        self.sender = sender
        self.content = content
        self.timestamp = timestamp or time.time()
        self.is_llm = is_llm
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "sender": self.sender,
            "content": self.content,
            "timestamp": self.timestamp,
            "is_llm": self.is_llm
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChatMessage':
        """Create from dictionary"""
        return cls(
            sender=data["sender"],
            content=data["content"],
            timestamp=data["timestamp"],
            is_llm=data.get("is_llm", False)
        )
        
    def __str__(self) -> str:
        """String representation"""
        time_str = datetime.fromtimestamp(self.timestamp).strftime("%H:%M:%S")
        sender_display = f"{self.sender} (AI)" if self.is_llm else self.sender
        return f"[{time_str}] {sender_display}: {self.content}"

def is_port_in_use(port: int) -> bool:
    """Check if a port is in use"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def start_server_in_thread(host: str = "0.0.0.0", port: int = DEFAULT_SERVER_PORT) -> None:
    """Start the notification server in a separate thread"""
    global server_process
    
    # Check if port is already in use
    if is_port_in_use(port):
        logger.info(f"Port {port} is already in use. Assuming server is running.")
        return
    
    def run_server():
        """Run the uvicorn server"""
        try:
            import host as host_module
            logger.info(f"Starting notification server on {host}:{port}")
            uvicorn.run(host_module.app, host=host, port=port, log_level="info")
        except Exception as e:
            logger.error(f"Error starting server: {str(e)}")
    
    # Start server in a thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # Wait for server to start
    logger.info("Waiting for server to start...")
    max_attempts = 10
    for attempt in range(max_attempts):
        if is_port_in_use(port):
            logger.info(f"Server started successfully on port {port}")
            return
        time.sleep(1)
    
    logger.warning(f"Server may not have started properly after {max_attempts} seconds")

def wait_for_server(host: str = "localhost", port: int = DEFAULT_SERVER_PORT, timeout: int = 10) -> bool:
    """Wait for the server to be available"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if is_port_in_use(port):
            return True
        time.sleep(0.5)
    return False

class ChatClient:
    """Chat client using Airgap SNS"""
    
    def __init__(
        self,
        client_id: str,
        host_uri: str = DEFAULT_URI,
        channel: str = DEFAULT_CHANNEL,
        llm_api_key: Optional[str] = None,
        llm_model: str = DEFAULT_MODEL,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        auth_key: str = DEFAULT_AUTH_KEY,
        log_file: Optional[str] = None
    ):
        """Initialize the chat client"""
        self.client_id = client_id
        self.host_uri = host_uri
        self.channel = channel
        self.llm_api_key = llm_api_key
        self.llm_model = llm_model
        self.system_prompt = system_prompt
        self.auth_key = auth_key
        self.log_file = log_file
        
        self.notification_client = None
        self.running = False
        self.message_history: List[ChatMessage] = []
        self.participants: Set[str] = set()
        self.authenticated_users: Set[str] = set()
        self.is_authenticated = False
        self.is_llm_provider = llm_api_key is not None
        self.auth_attempts = 0
        self.max_auth_attempts = 3
        
        # Initialize OpenAI client if API key is provided
        if self.is_llm_provider:
            openai.api_key = llm_api_key
            logger.info("LLM provider mode enabled (API key provided)")
        else:
            logger.info("Regular client mode (no API key provided)")
    
    async def connect(self) -> bool:
        """Connect to the notification server"""
        try:
            # Create notification client
            self.notification_client = NotificationClient(
                uri=self.host_uri,
                client_id=self.client_id
            )
            
            # Connect to server
            if not await self.notification_client.connect():
                logger.error("Failed to connect to notification server")
                return False
                
            # Register message handler
            self.notification_client.register_handler("default", self.handle_message)
            
            # Set running flag
            self.running = True
            
            # Add self to participants
            self.participants.add(self.client_id)
            
            # Authenticate with the chat system
            await self.authenticate()
            
            # Wait for authentication response with retry
            auth_timeout = 2  # seconds per attempt
            self.auth_attempts = 0
            
            while not self.is_authenticated and self.auth_attempts < self.max_auth_attempts:
                self.auth_attempts += 1
                logger.info(f"Authentication attempt {self.auth_attempts}/{self.max_auth_attempts}")
                
                # Wait for response
                auth_start_time = time.time()
                while not self.is_authenticated and time.time() - auth_start_time < auth_timeout:
                    await asyncio.sleep(0.1)
                
                if self.is_authenticated:
                    break
                
                # If not authenticated, try again
                if self.auth_attempts < self.max_auth_attempts:
                    logger.info("Authentication timed out, retrying...")
                    await self.authenticate()
                
            if not self.is_authenticated:
                logger.error(f"Authentication failed after {self.max_auth_attempts} attempts")
                return False
                
            # Send join message
            await self.send_system_message(f"{self.client_id} joined the chat")
            
            # Announce if this client is an LLM provider
            if self.is_llm_provider:
                await self.send_system_message(f"{self.client_id} is providing LLM services")
            
            return True
            
        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            return False
    
    async def disconnect(self):
        """Disconnect from the notification server"""
        if self.notification_client:
            # Send leave message
            if self.running:
                await self.send_system_message(f"{self.client_id} left the chat")
                
            # Close connection
            await self.notification_client.close()
            self.notification_client = None
            
        self.running = False
    
    async def run(self):
        """Run the chat client"""
        if not self.notification_client:
            logger.error("Not connected. Call connect() first.")
            return
            
        try:
            # Start listening for messages
            listen_task = asyncio.create_task(self.notification_client.listen())
            
            # Start user input loop
            input_task = asyncio.create_task(self.user_input_loop())
            
            # Wait for tasks to complete
            await asyncio.gather(listen_task, input_task)
            
        except asyncio.CancelledError:
            logger.info("Chat client stopped")
        except Exception as e:
            logger.error(f"Error in chat client: {str(e)}")
        finally:
            await self.disconnect()
    
    async def user_input_loop(self):
        """Handle user input"""
        # Print welcome message
        self.print_welcome()
        
        while self.running:
            try:
                # Get user input
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input("> ")
                )
                
                # Process commands
                if user_input.startswith("/"):
                    await self.process_command(user_input)
                    continue
                    
                # Skip empty messages
                if not user_input.strip():
                    continue
                    
                # Create message
                message = ChatMessage(
                    sender=self.client_id,
                    content=user_input
                )
                
                # Add to history
                self.message_history.append(message)
                
                # Log message
                self.log_message(message)
                
                # Send message
                await self.send_chat_message(message)
                
                # Check if message is directed to LLM
                if ("@ai" in user_input.lower() or "@llm" in user_input.lower()):
                    if self.is_llm_provider:
                        # Generate LLM response directly
                        await self.generate_llm_response(message)
                    else:
                        # Send LLM request to a provider
                        await self.send_llm_request(message)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in user input loop: {str(e)}")
    
    async def process_command(self, command: str):
        """Process a command"""
        cmd_parts = command.split()
        cmd = cmd_parts[0].lower()
        
        if cmd == "/help":
            self.print_help()
        elif cmd == "/exit" or cmd == "/quit":
            self.running = False
            raise asyncio.CancelledError()
        elif cmd == "/users":
            print(f"Participants: {', '.join(sorted(self.participants))}")
        elif cmd == "/history":
            count = 10  # Default
            if len(cmd_parts) > 1 and cmd_parts[1].isdigit():
                count = int(cmd_parts[1])
            self.print_history(count)
        elif cmd == "/clear":
            os.system("cls" if os.name == "nt" else "clear")
        elif cmd == "/ask":
            # Direct question to LLM
            question = " ".join(cmd_parts[1:])
            if not question:
                print("Usage: /ask <question>")
                return
                
            # Create message
            message = ChatMessage(
                sender=self.client_id,
                content=f"@ai {question}"
            )
            
            # Add to history
            self.message_history.append(message)
            
            # Log message
            self.log_message(message)
            
            # Send message
            await self.send_chat_message(message)
            
            # Generate or request LLM response
            if self.is_llm_provider:
                await self.generate_llm_response(message)
            else:
                await self.send_llm_request(message)
        elif cmd == "/auth":
            # Force re-authentication
            print("Attempting to re-authenticate...")
            await self.authenticate()
        else:
            print(f"Unknown command: {cmd}")
            print("Type /help for a list of commands")
    
    async def authenticate(self):
        """Authenticate with the chat system"""
        if not self.notification_client:
            logger.error("Not connected. Call connect() first.")
            return
            
        try:
            # Create auth message
            auth_hash = hashlib.sha256(self.auth_key.encode()).hexdigest()
            
            data = {
                "type": MSG_TYPE_AUTH,
                "client_id": self.client_id,
                "auth_hash": auth_hash,
                "is_llm_provider": self.is_llm_provider
            }
            
            # Create burst message with broadcast to all clients
            burst = self.notification_client.create_burst_message(
                wc=self.channel
            )
            
            # Send auth message
            full_message = f"{json.dumps(data)} {burst}"
            await self.notification_client.send_burst(full_message)
            
            logger.info(f"Sent authentication request (attempt {self.auth_attempts+1})")
            
            # Auto-authenticate if we're the first client
            if not self.authenticated_users:
                self.is_authenticated = True
                self.authenticated_users.add(self.client_id)
                logger.info("Self-authenticated as first client")
            
        except Exception as e:
            logger.error(f"Error sending authentication request: {str(e)}")
    
    async def handle_message(self, message_str: str):
        """Handle incoming messages"""
        try:
            # Parse message
            data = json.loads(message_str)
            
            # Check message type
            if "type" not in data:
                return
                
            message_type = data["type"]
            
            # Handle different message types
            if message_type == MSG_TYPE_CHAT:
                await self.handle_chat_message(data)
            elif message_type == MSG_TYPE_SYSTEM:
                await self.handle_system_message(data)
            elif message_type == MSG_TYPE_LLM_REQUEST and self.is_llm_provider:
                await self.handle_llm_request(data)
            elif message_type == MSG_TYPE_LLM_RESPONSE:
                await self.handle_llm_response(data)
            elif message_type == MSG_TYPE_AUTH:
                await self.handle_auth_request(data)
            elif message_type == MSG_TYPE_AUTH_RESPONSE:
                await self.handle_auth_response(data)
                
        except json.JSONDecodeError:
            logger.warning(f"Received non-JSON message: {message_str}")
        except Exception as e:
            logger.error(f"Error handling message: {str(e)}")
    
    async def handle_chat_message(self, data):
        """Handle a chat message"""
        # Create message
        message = ChatMessage.from_dict(data["message"])
        
        # Skip own messages
        if message.sender == self.client_id:
            return
            
        # Skip messages from unauthenticated users
        if message.sender not in self.authenticated_users and message.sender != "AI":
            logger.warning(f"Received message from unauthenticated user: {message.sender}")
            return
            
        # Add sender to participants
        self.participants.add(message.sender)
        
        # Add to history
        self.message_history.append(message)
        
        # Log message
        self.log_message(message)
        
        # Print message
        print(f"\n{message}")
        print("> ", end="", flush=True)
        
        # Check if message is directed to this client
        if f"@{self.client_id}" in message.content:
            # Highlight mention
            print(f"\n[MENTION] {message.sender} mentioned you!")
            print("> ", end="", flush=True)
            
        # Check if message is directed to LLM and this client is an LLM provider
        if self.is_llm_provider and ("@ai" in message.content.lower() or "@llm" in message.content.lower()):
            # Generate LLM response
            await self.generate_llm_response(message)
    
    async def handle_system_message(self, data):
        """Handle a system message"""
        # Print system message
        print(f"\n[SYSTEM] {data['content']}")
        print("> ", end="", flush=True)
        
        # Check for participant updates
        if "joined" in data["content"]:
            # Extract participant
            match = re.search(r"(\w+) joined", data["content"])
            if match:
                self.participants.add(match.group(1))
        elif "left" in data["content"]:
            # Extract participant
            match = re.search(r"(\w+) left", data["content"])
            if match:
                self.participants.discard(match.group(1))
                
        # Log system message
        self.log_system_message(data["content"])
    
    async def handle_llm_request(self, data):
        """Handle an LLM request (only for LLM providers)"""
        if not self.is_llm_provider:
            return
            
        try:
            # Extract request data
            request_id = data["request_id"]
            user_id = data["user_id"]
            message_content = data["content"]
            message_history = data.get("history", [])
            
            logger.info(f"Received LLM request from {user_id} (ID: {request_id})")
            
            # Prepare conversation history
            messages = [
                {"role": "system", "content": self.system_prompt}
            ]
            
            # Add message history
            for msg in message_history:
                if msg["is_llm"]:
                    messages.append({
                        "role": "assistant",
                        "content": msg["content"]
                    })
                else:
                    messages.append({
                        "role": "user",
                        "content": f"{msg['sender']}: {msg['content']}"
                    })
            
            # Add the current message
            messages.append({
                "role": "user",
                "content": f"{user_id}: {message_content}"
            })
            
            # Call the LLM API
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: openai.ChatCompletion.create(
                    model=self.llm_model,
                    messages=messages
                )
            )
            
            # Extract response text
            response_text = response.choices[0].message.content
            
            # Send LLM response
            await self.send_llm_response(request_id, user_id, response_text)
            
        except Exception as e:
            logger.error(f"Error handling LLM request: {str(e)}")
            
            # Send error response
            await self.send_llm_response(
                data["request_id"],
                data["user_id"],
                f"Sorry, I encountered an error: {str(e)}"
            )
    
    async def handle_llm_response(self, data):
        """Handle an LLM response"""
        # Check if this response is for us
        if data["user_id"] != self.client_id:
            return
            
        # Create message
        message = ChatMessage(
            sender="AI",
            content=data["content"],
            is_llm=True
        )
        
        # Add to history
        self.message_history.append(message)
        
        # Log message
        self.log_message(message)
        
        # Print message
        print(f"\n{message}")
        print("> ", end="", flush=True)
    
    async def handle_auth_request(self, data):
        """Handle an authentication request"""
        # Extract data
        client_id = data["client_id"]
        auth_hash = data["auth_hash"]
        is_llm_provider = data.get("is_llm_provider", False)
        
        # Verify auth hash
        expected_hash = hashlib.sha256(self.auth_key.encode()).hexdigest()
        
        if auth_hash == expected_hash:
            # Add to authenticated users
            self.authenticated_users.add(client_id)
            
            # Auto-authenticate ourselves if we're not already
            if not self.is_authenticated:
                self.is_authenticated = True
                self.authenticated_users.add(self.client_id)
                logger.info("Self-authenticated based on valid auth key")
            
            # Send auth response
            await self.send_auth_response(client_id, True)
            
            logger.info(f"Authenticated user: {client_id} (LLM Provider: {is_llm_provider})")
        else:
            # Send auth failure response
            await self.send_auth_response(client_id, False)
            
            logger.warning(f"Failed authentication attempt from: {client_id}")
    
    async def handle_auth_response(self, data):
        """Handle an authentication response"""
        # Check if this response is for us
        if data["client_id"] != self.client_id:
            return
            
        # Set authentication status
        self.is_authenticated = data["success"]
        
        if self.is_authenticated:
            logger.info("Authentication successful")
            
            # Add authenticated users
            if "authenticated_users" in data:
                for user in data["authenticated_users"]:
                    self.authenticated_users.add(user)
        else:
            logger.error("Authentication failed")
    
    async def send_chat_message(self, message: ChatMessage):
        """Send a chat message"""
        if not self.notification_client:
            logger.error("Not connected. Call connect() first.")
            return
            
        try:
            # Create message data
            data = {
                "type": MSG_TYPE_CHAT,
                "message": message.to_dict()
            }
            
            # Create burst message
            burst = self.notification_client.create_burst_message(
                wc=self.channel
            )
            
            # Send message
            full_message = f"{json.dumps(data)} {burst}"
            await self.notification_client.send_burst(full_message)
            
        except Exception as e:
            logger.error(f"Error sending chat message: {str(e)}")
    
    async def send_system_message(self, content: str):
        """Send a system message"""
        if not self.notification_client:
            logger.error("Not connected. Call connect() first.")
            return
            
        try:
            # Create message data
            data = {
                "type": MSG_TYPE_SYSTEM,
                "content": content
            }
            
            # Create burst message
            burst = self.notification_client.create_burst_message(
                wc=self.channel
            )
            
            # Send message
            full_message = f"{json.dumps(data)} {burst}"
            await self.notification_client.send_burst(full_message)
            
        except Exception as e:
            logger.error(f"Error sending system message: {str(e)}")
    
    async def send_llm_request(self, user_message: ChatMessage):
        """Send a request to an LLM provider"""
        if not self.notification_client:
            logger.error("Not connected. Call connect() first.")
            return
            
        try:
            # Create request ID
            request_id = f"{self.client_id}-{int(time.time())}"
            
            # Create message history (last 10 messages)
            history = []
            for msg in self.message_history[-10:]:
                history.append({
                    "sender": msg.sender,
                    "content": msg.content,
                    "is_llm": msg.is_llm
                })
            
            # Create request data
            data = {
                "type": MSG_TYPE_LLM_REQUEST,
                "request_id": request_id,
                "user_id": self.client_id,
                "content": user_message.content,
                "history": history
            }
            
            # Create burst message
            burst = self.notification_client.create_burst_message(
                wc=self.channel
            )
            
            # Send request
            full_message = f"{json.dumps(data)} {burst}"
            await self.notification_client.send_burst(full_message)
            
            logger.info(f"Sent LLM request (ID: {request_id})")
            
            # If no LLM provider is available, generate a fallback response
            # Wait a bit to see if a provider responds
            await asyncio.sleep(2)
            
            # Check if we received a response (would be in message history)
            found_response = False
            for msg in reversed(self.message_history[-5:]):
                if msg.is_llm and msg.sender == "AI":
                    found_response = True
                    break
            
            if not found_response:
                # No response received, generate a fallback
                logger.warning("No LLM provider responded, generating fallback response")
                
                # Create fallback message
                fallback_message = ChatMessage(
                    sender="AI",
                    content="I'm sorry, but I couldn't process your request. It seems the LLM provider is not available. Please make sure at least one client has the OPENAI_API_KEY set and is running in provider mode.",
                    is_llm=True
                )
                
                # Add to history
                self.message_history.append(fallback_message)
                
                # Log message
                self.log_message(fallback_message)
                
                # Print message
                print(f"\n{fallback_message}")
                print("> ", end="", flush=True)
                
                # Send message to other clients
                await self.send_chat_message(fallback_message)
            
        except Exception as e:
            logger.error(f"Error sending LLM request: {str(e)}")
            
            # Create error message
            error_message = ChatMessage(
                sender="AI",
                content=f"Sorry, I encountered an error while processing your request: {str(e)}",
                is_llm=True
            )
            
            # Add to history
            self.message_history.append(error_message)
            
            # Log message
            self.log_message(error_message)
            
            # Print message
            print(f"\n{error_message}")
            print("> ", end="", flush=True)
    
    async def send_llm_response(self, request_id: str, user_id: str, content: str):
        """Send an LLM response"""
        if not self.notification_client:
            logger.error("Not connected. Call connect() first.")
            return
            
        try:
            # Create response data
            data = {
                "type": MSG_TYPE_LLM_RESPONSE,
                "request_id": request_id,
                "user_id": user_id,
                "content": content
            }
            
            # Create burst message
            burst = self.notification_client.create_burst_message(
                wc=self.channel
            )
            
            # Send response
            full_message = f"{json.dumps(data)} {burst}"
            await self.notification_client.send_burst(full_message)
            
            logger.info(f"Sent LLM response to {user_id} (ID: {request_id})")
            
        except Exception as e:
            logger.error(f"Error sending LLM response: {str(e)}")
    
    async def send_auth_response(self, client_id: str, success: bool):
        """Send an authentication response"""
        if not self.notification_client:
            logger.error("Not connected. Call connect() first.")
            return
            
        try:
            # Create response data
            data = {
                "type": MSG_TYPE_AUTH_RESPONSE,
                "client_id": client_id,
                "success": success
            }
            
            # Add authenticated users if successful
            if success:
                data["authenticated_users"] = list(self.authenticated_users)
            
            # Create burst message
            burst = self.notification_client.create_burst_message(
                wc=self.channel
            )
            
            # Send response
            full_message = f"{json.dumps(data)} {burst}"
            await self.notification_client.send_burst(full_message)
            
            logger.info(f"Sent auth response to {client_id} (Success: {success})")
            
        except Exception as e:
            logger.error(f"Error sending auth response: {str(e)}")
    
    async def generate_llm_response(self, user_message: ChatMessage):
        """Generate a response from the LLM"""
        if not self.is_llm_provider:
            logger.error("Not an LLM provider")
            return
            
        try:
            # Prepare conversation history
            messages = [
                {"role": "system", "content": self.system_prompt}
            ]
            
            # Add recent message history (last 10 messages)
            for msg in self.message_history[-10:]:
                if msg.is_llm:
                    messages.append({
                        "role": "assistant",
                        "content": msg.content
                    })
                else:
                    messages.append({
                        "role": "user",
                        "content": f"{msg.sender}: {msg.content}"
                    })
            
            # Call the LLM API
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: openai.ChatCompletion.create(
                    model=self.llm_model,
                    messages=messages
                )
            )
            
            # Extract response text
            response_text = response.choices[0].message.content
            
            # Create message
            message = ChatMessage(
                sender="AI",
                content=response_text,
                is_llm=True
            )
            
            # Add to history
            self.message_history.append(message)
            
            # Log message
            self.log_message(message)
            
            # Send message
            await self.send_chat_message(message)
            
        except Exception as e:
            logger.error(f"Error generating LLM response: {str(e)}")
            
            # Send error message
            error_message = ChatMessage(
                sender="AI",
                content=f"Sorry, I encountered an error: {str(e)}",
                is_llm=True
            )
            
            # Add to history
            self.message_history.append(error_message)
            
            # Log message
            self.log_message(error_message)
            
            # Send message
            await self.send_chat_message(error_message)
    
    def log_message(self, message: ChatMessage):
        """Log a message to the log file"""
        if not self.log_file:
            return
            
        try:
            with open(self.log_file, "a") as f:
                f.write(f"{message}\n")
        except Exception as e:
            logger.error(f"Error logging message: {str(e)}")
    
    def log_system_message(self, content: str):
        """Log a system message to the log file"""
        if not self.log_file:
            return
            
        try:
            with open(self.log_file, "a") as f:
                time_str = datetime.now().strftime("%H:%M:%S")
                f.write(f"[{time_str}] [SYSTEM] {content}\n")
        except Exception as e:
            logger.error(f"Error logging system message: {str(e)}")
    
    def print_welcome(self):
        """Print welcome message"""
        os.system("cls" if os.name == "nt" else "clear")
        print("=" * 50)
        print(f"Welcome to the Airgap SNS Chat App!")
        print(f"You are connected as: {self.client_id}")
        print(f"Channel: {self.channel}")
        print(f"LLM integration: {'Provider' if self.is_llm_provider else 'Client'}")
        print(f"Chat logging: {'Enabled' if self.log_file else 'Disabled'}")
        print("=" * 50)
        print("Type /help for a list of commands")
        print("=" * 50)
    
    def print_help(self):
        """Print help message"""
        print("\nAvailable commands:")
        print("  /help           - Show this help message")
        print("  /exit, /quit    - Exit the chat")
        print("  /users          - List participants")
        print("  /history [n]    - Show last n messages (default: 10)")
        print("  /clear          - Clear the screen")
        print("  /ask <question> - Ask a question directly to the AI")
        print("  /auth           - Force re-authentication")
        print("\nYou can also mention @ai or @llm in your message to get an AI response")
        print("")
    
    def print_history(self, count: int = 10):
        """Print message history"""
        print(f"\nLast {min(count, len(self.message_history))} messages:")
        for message in self.message_history[-count:]:
            print(message)
        print("")

async def main():
    """Main entry point"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Airgap SNS Chat App")
    parser.add_argument("--id", help="Client ID", required=True)
    parser.add_argument("--host", help=f"Host URI (default: {DEFAULT_URI})", default=DEFAULT_URI)
    parser.add_argument("--channel", help=f"Chat channel (default: {DEFAULT_CHANNEL})", default=DEFAULT_CHANNEL)
    parser.add_argument("--llm-api-key", help="OpenAI API key for LLM integration")
    parser.add_argument("--llm-model", help=f"LLM model (default: {DEFAULT_MODEL})", default=DEFAULT_MODEL)
    parser.add_argument("--auth-key", help=f"Authentication key (default: {DEFAULT_AUTH_KEY})", default=DEFAULT_AUTH_KEY)
    parser.add_argument("--log-file", help=f"Log file (default: {DEFAULT_LOG_FILE})", default=DEFAULT_LOG_FILE)
    parser.add_argument("--no-log", help="Disable chat logging", action="store_true")
    parser.add_argument("--start-server", help="Start the notification server in the background", action="store_true")
    parser.add_argument("--server-port", help=f"Server port (default: {DEFAULT_SERVER_PORT})", type=int, default=DEFAULT_SERVER_PORT)
    args = parser.parse_args()
    
    # Get API key from environment (preferred) or arguments
    llm_api_key = os.environ.get("OPENAI_API_KEY") or args.llm_api_key
    
    # Determine log file
    log_file = None if args.no_log else args.log_file
    
    # Start server if requested
    if args.start_server:
        # Extract host from URI
        host_match = re.match(r"ws://([^:]+)(?::\d+)?/.*", args.host)
        server_host = "0.0.0.0"  # Default to all interfaces
        
        # Get port from URI or use default
        port_match = re.match(r"ws://[^:]+:(\d+)/.*", args.host)
        server_port = int(port_match.group(1)) if port_match else args.server_port
        
        # Start server
        start_server_in_thread(host=server_host, port=server_port)
        
        # Wait for server to be available
        if not wait_for_server(port=server_port):
            logger.error(f"Server did not start within the timeout period")
            return
    
    # Create chat client
    client = ChatClient(
        client_id=args.id,
        host_uri=args.host,
        channel=args.channel,
        llm_api_key=llm_api_key,
        llm_model=args.llm_model,
        auth_key=args.auth_key,
        log_file=log_file
    )
    
    # Connect to server with retry
    max_retries = 3
    for attempt in range(max_retries):
        if await client.connect():
            break
        if attempt < max_retries - 1:
            logger.info(f"Connection attempt {attempt+1} failed. Retrying in 2 seconds...")
            await asyncio.sleep(2)
    else:
        logger.error(f"Failed to connect to notification server after {max_retries} attempts")
        return
    
    try:
        # Run the chat client
        await client.run()
    except KeyboardInterrupt:
        logger.info("Chat client stopped by user")
    finally:
        # Disconnect
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
