import asyncio, websockets
from fastapi import FastAPI, WebSocket, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any
from scheduler import schedule_job
from burst import parse_burst
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("airgap-sns-host")

# Try to import audio module with graceful fallback
try:
    from audio import AudioTransceiver, async_transmit, async_receive, AUDIO_AVAILABLE
except ImportError:
    logger.warning("Audio module not available. Audio features disabled.")
    AUDIO_AVAILABLE = False

app = FastAPI(title="Airgap SNS Notification Host", 
              description="Secure Notification System with audio capabilities")

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

if __name__ == "__main__":
    import uvicorn
    
    # Start the server
    logger.info("Starting Airgap SNS Notification Host")
    uvicorn.run("host:app", host="0.0.0.0", port=9000, reload=True)
