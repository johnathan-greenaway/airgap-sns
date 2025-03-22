import asyncio, websockets, json, logging, argparse
from typing import Optional, Dict, Any
import os, sys, threading

# Import from the new package structure
from airgap_sns.core.crypto import decrypt
from airgap_sns.core.burst import parse_burst

# Try to import audio module with graceful fallback
try:
    from airgap_sns.core.audio import AudioTransceiver, async_transmit, async_receive, AUDIO_AVAILABLE
except ImportError:
    logging.warning("Audio module not available. Audio features disabled.")
    AUDIO_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("airgap-sns-client")

# Default settings
DEFAULT_AUDIO_PROTOCOL = 1
DEFAULT_AUDIO_VOLUME = 50

# Default connection settings
DEFAULT_URI = "ws://localhost:9000/ws/"

class NotificationClient:
    def __init__(self, 
                 uri: str, 
                 client_id: str, 
                 password: Optional[str] = None,
                 enable_audio: bool = True,
                 audio_protocol: int = DEFAULT_AUDIO_PROTOCOL,
                 audio_volume: int = DEFAULT_AUDIO_VOLUME):
        """Initialize notification client with connection parameters"""
        self.uri = uri
        self.client_id = client_id
        self.password = password
        self.websocket = None
        self.running = False
        self.handlers = {}
        self.audio_enabled = enable_audio and AUDIO_AVAILABLE
        self.audio_protocol = audio_protocol
        self.audio_volume = audio_volume
        self.audio_transceiver = None
        
        # Register default handlers
        self.register_handler("default", self._default_handler)
        
        # Initialize audio if available
        if self.audio_enabled:
            try:
                self.audio_transceiver = AudioTransceiver(
                    protocol=audio_protocol,
                    volume=audio_volume,
                    callback=self._handle_audio_message
                )
                self.audio_transceiver.start_receiver()
                logger.info("Audio transceiver initialized and started")
            except Exception as e:
                logger.error(f"Failed to initialize audio: {str(e)}")
                self.audio_transceiver = None
                self.audio_enabled = False
        
    def register_handler(self, event_type: str, handler_func):
        """Register a handler function for specific notification types"""
        self.handlers[event_type] = handler_func
        return self  # Allow method chaining
        
    def _handle_audio_message(self, message: str):
        """Handle messages received via audio"""
        logger.info(f"Received audio message: {message}")
        
        # Parse burst parameters
        params = parse_burst(message)
        if not params:
            logger.warning(f"Invalid burst format in audio message: {message}")
            return
            
        # Process the message
        asyncio.run_coroutine_threadsafe(
            self._process_message(message, params, source="audio"),
            asyncio.get_event_loop()
        )
    
    async def _process_message(self, message: str, params: Dict[str, Any], source: str = "websocket"):
        """Process a received message with parsed parameters"""
        try:
            # Try to decrypt if needed and password is available
            should_decrypt = params.get("encrypt") == "yes" or params.get("encrypt") is True
            
            if should_decrypt and self.password:
                try:
                    decrypted = decrypt(message, self.password)
                    logger.info(f"Decrypted {source} message: {decrypted}")
                    processed_msg = decrypted
                except Exception as e:
                    logger.warning(f"Decryption failed: {str(e)}")
                    processed_msg = message
            else:
                processed_msg = message
                
            # Determine message type (default to "default")
            msg_type = params.get("type", "default")
            
            # Get appropriate handler (fall back to default)
            handler = self.handlers.get(msg_type, self.handlers.get("default"))
            
            # Process notification with handler
            await handler(processed_msg)
            
        except Exception as e:
            logger.error(f"Error processing {source} message: {str(e)}")
    
    async def _default_handler(self, message: str):
        """Default handler for all notifications"""
        try:
            logger.info(f"Notification: {message}")
        except Exception as e:
            logger.error(f"Error in default handler: {str(e)}")
    
    async def connect(self):
        """Establish WebSocket connection to notification server"""
        try:
            connection_uri = f"{self.uri}{self.client_id}"
            logger.info(f"Connecting to {connection_uri} as {self.client_id}...")
            
            self.websocket = await websockets.connect(connection_uri)
            self.running = True
            logger.info(f"Connected successfully as {self.client_id}")
            
            return True
        except Exception as e:
            logger.error(f"Connection failed: {str(e)}")
            return False
    
    async def listen(self):
        """Listen for incoming notifications via WebSocket"""
        if not self.websocket:
            raise RuntimeError("Not connected. Call connect() first.")
            
        try:
            while self.running:
                try:
                    message = await self.websocket.recv()
                    logger.debug(f"Received WebSocket message: {message}")
                    
                    # Parse burst parameters
                    params = parse_burst(message)
                    if params:
                        # Process the message
                        await self._process_message(message, params)
                    else:
                        # If not a burst message, use default handler
                        await self._default_handler(message)
                    
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("WebSocket connection closed")
                    self.running = False
                    break
                    
        except Exception as e:
            logger.error(f"Error in WebSocket listener: {str(e)}")
        finally:
            self.running = False
            if self.websocket:
                await self.websocket.close()
                self.websocket = None
    
    async def send_burst(self, message: str, use_audio: bool = False):
        """
        Send a burst message to the server
        
        Args:
            message: The burst message to send
            use_audio: Whether to send via audio instead of WebSocket
        """
        # Validate burst format
        params = parse_burst(message)
        if not params:
            logger.error(f"Invalid burst format: {message}")
            return False
            
        # Send via audio if requested and available
        if use_audio and self.audio_enabled and self.audio_transceiver:
            try:
                result = self.audio_transceiver.transmit(message)
                if result:
                    logger.info(f"Sent audio burst message: {message}")
                else:
                    logger.error("Audio transmission failed")
                return result
            except Exception as e:
                logger.error(f"Failed to send audio burst: {str(e)}")
                return False
        
        # Otherwise send via WebSocket
        if not self.websocket:
            raise RuntimeError("Not connected to WebSocket. Call connect() first.")
            
        try:
            await self.websocket.send(message)
            logger.info(f"Sent WebSocket burst message: {message}")
            return True
        except Exception as e:
            logger.error(f"Failed to send WebSocket burst: {str(e)}")
            return False
    
    async def close(self):
        """Close all connections gracefully"""
        # Stop WebSocket
        self.running = False
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
            logger.info("WebSocket connection closed")
            
        # Stop audio receiver
        if self.audio_transceiver:
            self.audio_transceiver.stop_receiver()
            logger.info("Audio receiver stopped")

    def create_burst_message(self, **kwargs):
        """
        Create a properly formatted burst message
        
        Args:
            **kwargs: Key-value pairs for burst parameters
                dest: Destination client ID
                wc: Water-cooler channel
                encrypt: Whether to encrypt (yes/no)
                webhook: Webhook URL
                audio: Audio transmission (tx/none)
                pwd: Optional password
                
        Returns:
            Formatted burst message string
        """
        # Build parameter string
        params = []
        for key, value in kwargs.items():
            if value is not None:
                params.append(f"{key}={value}")
                
        # Create burst message
        return f"!!BURST({';'.join(params)})!!"

async def interactive_client(client):
    """Interactive mode for sending messages"""
    print("\nInteractive Mode - Enter commands or messages")
    print("Commands:")
    print("  /quit - Exit the client")
    print("  /audio <message> - Send message via audio")
    print("  /burst dest=<id>;wc=<channel>;... - Send custom burst")
    print("  /help - Show this help\n")
    
    while client.running:
        try:
            # Get user input
            user_input = await asyncio.get_event_loop().run_in_executor(
                None, input, "> "
            )
            
            # Process commands
            if user_input.lower() == "/quit":
                break
            elif user_input.lower() == "/help":
                print("Commands:")
                print("  /quit - Exit the client")
                print("  /audio <message> - Send message via audio")
                print("  /burst dest=<id>;wc=<channel>;... - Send custom burst")
                print("  /help - Show this help")
            elif user_input.lower().startswith("/audio "):
                # Send message via audio
                message = user_input[7:]  # Remove "/audio "
                if client.audio_enabled:
                    burst = client.create_burst_message(dest=client.client_id, audio="tx")
                    await client.send_burst(f"{message} {burst}", use_audio=True)
                else:
                    print("Audio not available")
            elif user_input.lower().startswith("/burst "):
                # Send custom burst
                params = user_input[7:]  # Remove "/burst "
                burst = f"!!BURST({params})!!"
                await client.send_burst(burst)
            else:
                # Send regular message with default burst
                burst = client.create_burst_message(dest=client.client_id)
                await client.send_burst(f"{user_input} {burst}")
                
        except Exception as e:
            logger.error(f"Error in interactive mode: {str(e)}")
            
    return

def run_client():
    """Main entry point for the client application"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Airgap SNS Notification Client")
    parser.add_argument("--id", help="Client ID", required=True)
    parser.add_argument("--uri", help=f"Server URI (default: {DEFAULT_URI})", default=DEFAULT_URI)
    parser.add_argument("--password", help="Decryption password", default=None)
    parser.add_argument("--no-audio", help="Disable audio features", action="store_true")
    parser.add_argument("--interactive", help="Enable interactive mode", action="store_true")
    args = parser.parse_args()
    
    async def main():
        # Create client
        client = NotificationClient(
            uri=args.uri,
            client_id=args.id,
            password=args.password,
            enable_audio=not args.no_audio
        )
        
        # Connect to server
        if not await client.connect():
            sys.exit(1)
        
        try:
            # Start tasks
            tasks = [client.listen()]
            
            # Add interactive mode if requested
            if args.interactive:
                tasks.append(interactive_client(client))
                
            # Run all tasks
            await asyncio.gather(*tasks)
            
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            # Ensure connection is closed
            await client.close()
    
    asyncio.run(main())

if __name__ == "__main__":
    run_client()
