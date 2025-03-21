import asyncio, websockets
import argparse
import os
import sys
import threading
import socket
import atexit
from fastapi import FastAPI, WebSocket, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any, Tuple
from scheduler import schedule_job
from burst import parse_burst
import logging

# Load environment variables from .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
    logging.info("Loaded environment variables from .env file")
except ImportError:
    logging.warning("python-dotenv not installed. Environment variables must be set manually.")
    logging.warning("Install with: pip install python-dotenv")

# Default settings
DEFAULT_PORT = 9000
DEFAULT_TUNNEL_FILE = "tunnel_connection.txt"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("airgap-sns-host")

# Check if zrok is available
TUNNEL_AVAILABLE = False
try:
    import zrok
    from zrok.model import ShareRequest
    TUNNEL_AVAILABLE = True
    logger.info("Secure tunnel support available (zrok package found)")
except ImportError:
    logger.warning("Secure tunnel support not available (zrok package not found)")

# Tunnel variables
tunnel_share = None
tunnel_url = None

# Try to import audio module with graceful fallback
try:
    from audio import AudioTransceiver, async_transmit, async_receive, AUDIO_AVAILABLE
except ImportError:
    logger.warning("Audio module not available. Audio features disabled.")
    AUDIO_AVAILABLE = False

app = FastAPI(title="Airgap SNS Notification Host", 
              description="Secure Notification System with audio capabilities")

def is_port_in_use(port: int) -> bool:
    """Check if a port is in use"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

def create_secure_tunnel(port: int = DEFAULT_PORT) -> Optional[str]:
    """Create a secure tunnel to the server"""
    global tunnel_share, tunnel_url
    
    if not TUNNEL_AVAILABLE:
        logger.warning("Secure tunnel requested but zrok package is not installed")
        logger.warning("Install with: pip install zrok")
        return None
        
    try:
        # Set up tunnel
        logger.info("Creating secure tunnel...")
        root = zrok.environment.root.Load()
        
        # Check if zrok is configured
        if not root or not root.Config:
            logger.warning("Secure tunnel not configured. Please run 'zrok login' first")
            return None
            
        # Create share
        share = zrok.share.CreateShare(
            root=root, 
            request=ShareRequest(
                BackendMode=zrok.model.TCP_TUNNEL_BACKEND_MODE,
                ShareMode=zrok.model.PUBLIC_SHARE_MODE,
                Frontends=['public'],
                Target=f"localhost:{port}"
            )
        )
        
        # Store share for cleanup
        tunnel_share = share
        
        # Get URL
        if share and share.FrontendEndpoints and len(share.FrontendEndpoints) > 0:
            url = share.FrontendEndpoints[0]
            # Convert to WebSocket URL
            if url.startswith("https://"):
                ws_url = url.replace("https://", "wss://")
            else:
                ws_url = url.replace("http://", "ws://")
                
            # Add WebSocket path
            if not ws_url.endswith("/"):
                ws_url += "/"
            ws_url += "ws/"
            
            # Save URL
            tunnel_url = ws_url
            
            # Save to file
            with open(DEFAULT_TUNNEL_FILE, "w") as f:
                f.write(f"Tunnel URL: {ws_url}\n")
                f.write(f"Share this URL with clients to connect remotely\n")
            
            # Print to console in a very visible way
            print("\n" + "=" * 60)
            print(f"SECURE TUNNEL CREATED - CONNECTION URL:")
            print(f"=" * 60)
            print(f"\n{ws_url}\n")
            print(f"Share this URL with clients to connect remotely")
            print(f"This URL is also saved to: {DEFAULT_TUNNEL_FILE}")
            print("=" * 60 + "\n")
                
            # Register cleanup
            def cleanup_tunnel():
                if tunnel_share:
                    try:
                        logger.info("Cleaning up secure tunnel...")
                        zrok.share.DeleteShare(root=root, shr=tunnel_share)
                    except Exception as e:
                        logger.error(f"Error cleaning up tunnel: {str(e)}")
            
            atexit.register(cleanup_tunnel)
            
            logger.info(f"Secure tunnel created successfully")
            return ws_url
            
    except Exception as e:
        logger.error(f"Error creating secure tunnel: {str(e)}")
        
    return None

class PubSub:
    def __init__(self):
        self.channels = {}
        self.clients = {}
        self.audio_transceiver = None
        
        # Initialize audio transceiver if available
        if AUDIO_AVAILABLE:
            try:
                from audio import AudioTransceiver
                self.audio_transceiver = AudioTransceiver(callback=self.handle_audio_message)
                self.audio_transceiver.start_receiver()
                logger.info("Audio transceiver initialized and started")
            except Exception as e:
                logger.error(f"Failed to initialize audio: {str(e)}")
                self.audio_transceiver = None
    
    async def subscribe(self, ws, ch):
        """Subscribe a WebSocket to a channel"""
        self.channels.setdefault(ch, set()).add(ws)
        logger.info(f"Client subscribed to channel: {ch}")
        
    async def unsubscribe(self, ws, ch):
        """Unsubscribe a WebSocket from a channel"""
        if ch in self.channels and ws in self.channels[ch]:
            self.channels[ch].remove(ws)
            logger.info(f"Client unsubscribed from channel: {ch}")
            
    async def broadcast(self, ch, msg):
        """Broadcast a message to all subscribers of a channel"""
        count = 0
        for ws in self.channels.get(ch, []):
            try:
                await ws.send_text(msg)
                count += 1
            except Exception as e:
                logger.error(f"Failed to send to channel {ch}: {str(e)}")
        logger.info(f"Broadcast message to {count} clients on channel {ch}")
        
    async def register(self, ws, uid):
        """Register a WebSocket with a user ID"""
        self.clients[uid] = ws
        logger.info(f"Client registered with ID: {uid}")
        
    async def unregister(self, uid):
        """Unregister a WebSocket by user ID"""
        if uid in self.clients:
            self.clients.pop(uid, None)
            logger.info(f"Client unregistered: {uid}")
            
    async def send(self, uid, msg):
        """Send a message to a specific user ID"""
        ws = self.clients.get(uid)
        if ws:
            try:
                await ws.send_text(msg)
                logger.info(f"Sent message to client: {uid}")
                return True
            except Exception as e:
                logger.error(f"Failed to send to {uid}: {str(e)}")
        else:
            logger.warning(f"Client not found: {uid}")
        return False
    
    async def handle_audio_message(self, message):
        """Handle messages received via audio"""
        logger.info(f"Received audio message: {message}")
        
        # Parse burst parameters
        params = parse_burst(message)
        if params:
            # Schedule the job
            await schedule_job(params, message, self)
    
    async def transmit_audio(self, message):
        """Transmit a message via audio"""
        if not AUDIO_AVAILABLE:
            logger.warning("Audio transmission not available")
            return False
            
        try:
            # Use the async transmit function
            result = await async_transmit(message)
            if result:
                logger.info(f"Audio message transmitted: {message}")
            else:
                logger.error("Audio transmission failed")
            return result
        except Exception as e:
            logger.error(f"Audio transmission error: {str(e)}")
            return False
    
    def cleanup(self):
        """Clean up resources"""
        if self.audio_transceiver:
            self.audio_transceiver.stop_receiver()
            logger.info("Audio receiver stopped")

# Create the PubSub instance
pubsub = PubSub()

# API endpoints
@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "name": "Airgap SNS Notification Host",
        "version": "1.0.0",
        "audio_available": AUDIO_AVAILABLE
    }

@app.websocket("/ws/{uid}")
async def websocket_endpoint(ws: WebSocket, uid: str, background_tasks: BackgroundTasks):
    """WebSocket endpoint for client connections"""
    await ws.accept()
    await pubsub.register(ws, uid)
    
    try:
        while True:
            data = await ws.receive_text()
            logger.debug(f"Received from {uid}: {data}")
            
            # Parse burst parameters
            params = parse_burst(data)
            if params:
                # Handle audio transmission if requested
                if params.get("audio") == "tx" and AUDIO_AVAILABLE:
                    background_tasks.add_task(pubsub.transmit_audio, data)
                
                # Schedule the notification job
                await schedule_job(params, data, pubsub)
            else:
                logger.warning(f"Invalid burst format from {uid}: {data}")
                
    except websockets.exceptions.ConnectionClosed:
        logger.info(f"Connection closed for {uid}")
    except Exception as e:
        logger.error(f"Error in WebSocket handler for {uid}: {str(e)}")
    finally:
        await pubsub.unregister(uid)

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown"""
    pubsub.cleanup()
    logger.info("Server shutting down, resources cleaned up")

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="Airgap SNS Notification Host")
    parser.add_argument("--host", help="Host to bind to", default="0.0.0.0")
    parser.add_argument("--port", help="Port to bind to", type=int, default=DEFAULT_PORT)
    parser.add_argument("--tunnel-on", help="Create a secure tunnel for remote connections", action="store_true")
    parser.add_argument("--reload", help="Enable auto-reload for development", action="store_true")
    return parser.parse_args()

if __name__ == "__main__":
    import uvicorn
    
    # Parse command line arguments
    args = parse_args()
    
    # Get values from environment variables or arguments
    host = args.host or os.environ.get("HOST", "0.0.0.0")
    port = args.port or int(os.environ.get("PORT", DEFAULT_PORT))
    tunnel_on = args.tunnel_on or os.environ.get("TUNNEL_ENABLED", "").lower() == "true"
    reload_enabled = args.reload or os.environ.get("RELOAD_ENABLED", "").lower() == "true"
    
    # Check for tunnel option
    if tunnel_on:
        if not TUNNEL_AVAILABLE:
            logger.warning("Secure tunnel requested but zrok package is not installed")
            print("\nWARNING: Secure tunnel requested but zrok package is not installed")
            print("To enable secure tunneling, install zrok: pip install zrok")
            print("Then run 'zrok login' to configure your account\n")
            
            # Ask if user wants to continue without tunnel
            response = input("Continue without secure tunnel? (y/n): ")
            if response.lower() != 'y':
                sys.exit(1)
        else:
            # Create tunnel
            tunnel_url = create_secure_tunnel(port)
            if not tunnel_url:
                logger.warning("Failed to create secure tunnel")
                
                # Ask if user wants to continue without tunnel
                response = input("Continue without secure tunnel? (y/n): ")
                if response.lower() != 'y':
                    sys.exit(1)
    
    # Start the server
    logger.info(f"Starting Airgap SNS Notification Host on {host}:{port}")
    uvicorn.run("host:app", host=host, port=port, reload=reload_enabled)
