#!/usr/bin/env python3
"""
Test script for Airgap SNS (Secure Notification System)

This script demonstrates the key features of the notification system:
- WebSocket notifications
- Audio transmission
- Encryption
- Water-cooler channels
- Webhooks

Usage:
    python test_sns.py [--test-audio] [--test-webhook]
"""

import asyncio
import argparse
import logging
import sys
import os
import time
from typing import Optional, List, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("airgap-sns-test")

# Check if required modules are installed
try:
    import websockets
    from client import NotificationClient
    from burst import parse_burst
except ImportError as e:
    logger.error(f"Required module not found: {e}")
    logger.error("Please install required modules: pip install websockets")
    sys.exit(1)

# Try to import audio module
try:
    from audio import AUDIO_AVAILABLE
except ImportError:
    logger.warning("Audio module not available. Audio tests will be skipped.")
    AUDIO_AVAILABLE = False

# Default settings
DEFAULT_URI = "ws://localhost:9000/ws/"
DEFAULT_PASSWORD = "test-password"
TEST_WEBHOOK_URL = "http://localhost:8000/webhook"  # Simple test webhook

class TestRunner:
    """Test runner for Airgap SNS"""
    
    def __init__(self, uri: str = DEFAULT_URI, test_audio: bool = False, test_webhook: bool = False):
        """Initialize test runner"""
        self.uri = uri
        self.test_audio = test_audio and AUDIO_AVAILABLE
        self.test_webhook = test_webhook
        self.clients = {}
        self.received_messages = {}
        self.test_results = {}
        
    async def setup_clients(self):
        """Set up test clients"""
        # Create sender client
        self.clients["sender"] = NotificationClient(
            uri=self.uri,
            client_id="sender",
            password=DEFAULT_PASSWORD,
            enable_audio=self.test_audio
        )
        
        # Create receiver client
        self.clients["receiver"] = NotificationClient(
            uri=self.uri,
            client_id="receiver",
            password=DEFAULT_PASSWORD,
            enable_audio=self.test_audio
        )
        
        # Create water-cooler client
        self.clients["wc-client"] = NotificationClient(
            uri=self.uri,
            client_id="wc-client",
            password=DEFAULT_PASSWORD,
            enable_audio=self.test_audio
        )
        
        # Connect all clients
        for client_id, client in self.clients.items():
            if await client.connect():
                logger.info(f"Client {client_id} connected")
                # Register custom message handler
                client.register_handler("default", self.create_message_handler(client_id))
            else:
                logger.error(f"Failed to connect client {client_id}")
                return False
                
        return True
    
    def create_message_handler(self, client_id: str):
        """Create a message handler for a specific client"""
        async def handler(message: str):
            logger.info(f"Client {client_id} received: {message}")
            if client_id not in self.received_messages:
                self.received_messages[client_id] = []
            self.received_messages[client_id].append(message)
        return handler
    
    async def run_tests(self):
        """Run all tests"""
        # Set up clients
        if not await self.setup_clients():
            logger.error("Failed to set up clients")
            return False
            
        try:
            # Run tests
            await self.test_direct_message()
            await self.test_encrypted_message()
            await self.test_water_cooler()
            
            if self.test_audio:
                await self.test_audio_transmission()
                
            if self.test_webhook:
                await self.test_webhook_notification()
                
            # Print test results
            self.print_results()
            
            return True
            
        except Exception as e:
            logger.error(f"Test failed: {str(e)}")
            return False
        finally:
            # Close all clients
            for client_id, client in self.clients.items():
                await client.close()
                logger.info(f"Client {client_id} closed")
    
    async def test_direct_message(self):
        """Test direct message delivery"""
        logger.info("=== Testing Direct Message ===")
        
        # Send a direct message from sender to receiver
        message = "Hello, receiver!"
        burst = self.clients["sender"].create_burst_message(dest="receiver")
        full_message = f"{message} {burst}"
        
        # Send the message
        success = await self.clients["sender"].send_burst(full_message)
        
        # Wait for message to be received
        await asyncio.sleep(1)
        
        # Check if message was received
        received = False
        if "receiver" in self.received_messages:
            for msg in self.received_messages["receiver"]:
                if message in msg:
                    received = True
                    break
        
        # Record test result
        self.test_results["direct_message"] = received
        
        if received:
            logger.info("Direct message test passed")
        else:
            logger.error("Direct message test failed")
    
    async def test_encrypted_message(self):
        """Test encrypted message delivery"""
        logger.info("=== Testing Encrypted Message ===")
        
        # Send an encrypted message from sender to receiver
        message = "This is a secret message!"
        burst = self.clients["sender"].create_burst_message(
            dest="receiver",
            encrypt="yes",
            pwd=DEFAULT_PASSWORD
        )
        full_message = f"{message} {burst}"
        
        # Send the message
        success = await self.clients["sender"].send_burst(full_message)
        
        # Wait for message to be received
        await asyncio.sleep(1)
        
        # Check if message was received and decrypted
        received = False
        if "receiver" in self.received_messages:
            for msg in self.received_messages["receiver"]:
                if message in msg:
                    received = True
                    break
        
        # Record test result
        self.test_results["encrypted_message"] = received
        
        if received:
            logger.info("Encrypted message test passed")
        else:
            logger.error("Encrypted message test failed")
    
    async def test_water_cooler(self):
        """Test water-cooler channel broadcast"""
        logger.info("=== Testing Water-Cooler Channel ===")
        
        # Send a message to water-cooler channel
        message = "Broadcast to water-cooler channel"
        burst = self.clients["sender"].create_burst_message(wc="test-channel")
        full_message = f"{message} {burst}"
        
        # Send the message
        success = await self.clients["sender"].send_burst(full_message)
        
        # Wait for message to be received
        await asyncio.sleep(1)
        
        # Check if message was received by all clients
        received_count = 0
        for client_id, messages in self.received_messages.items():
            for msg in messages:
                if message in msg:
                    received_count += 1
                    break
        
        # Record test result (at least one client should receive it)
        self.test_results["water_cooler"] = received_count > 0
        
        if received_count > 0:
            logger.info(f"Water-cooler test passed ({received_count} clients received)")
        else:
            logger.error("Water-cooler test failed")
    
    async def test_audio_transmission(self):
        """Test audio transmission"""
        logger.info("=== Testing Audio Transmission ===")
        
        if not AUDIO_AVAILABLE:
            logger.warning("Audio module not available. Skipping test.")
            self.test_results["audio_transmission"] = None
            return
            
        # Send a message via audio
        message = "Audio transmission test"
        burst = self.clients["sender"].create_burst_message(
            dest="receiver",
            audio="tx"
        )
        full_message = f"{message} {burst}"
        
        # Send the message via audio
        success = await self.clients["sender"].send_burst(full_message, use_audio=True)
        
        # Wait for message to be received
        await asyncio.sleep(3)  # Audio transmission may take longer
        
        # Check if message was received
        received = False
        if "receiver" in self.received_messages:
            for msg in self.received_messages["receiver"]:
                if message in msg:
                    received = True
                    break
        
        # Record test result
        self.test_results["audio_transmission"] = received
        
        if received:
            logger.info("Audio transmission test passed")
        else:
            logger.error("Audio transmission test failed")
    
    async def test_webhook_notification(self):
        """Test webhook notification"""
        logger.info("=== Testing Webhook Notification ===")
        
        # This test requires a webhook server to be running
        # For testing purposes, we'll just check if the message is sent
        
        # Send a message with webhook
        message = "Webhook test message"
        burst = self.clients["sender"].create_burst_message(
            webhook=TEST_WEBHOOK_URL
        )
        full_message = f"{message} {burst}"
        
        # Send the message
        success = await self.clients["sender"].send_burst(full_message)
        
        # Record test result (based on send success, not actual webhook delivery)
        self.test_results["webhook_notification"] = success
        
        if success:
            logger.info("Webhook notification test passed (message sent)")
        else:
            logger.error("Webhook notification test failed")
    
    def print_results(self):
        """Print test results"""
        logger.info("\n=== Test Results ===")
        
        for test_name, result in self.test_results.items():
            status = "PASSED" if result else "FAILED" if result is False else "SKIPPED"
            logger.info(f"{test_name}: {status}")

async def main():
    """Main entry point"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Test Airgap SNS")
    parser.add_argument("--test-audio", action="store_true", help="Test audio transmission")
    parser.add_argument("--test-webhook", action="store_true", help="Test webhook notification")
    parser.add_argument("--uri", help=f"Server URI (default: {DEFAULT_URI})", default=DEFAULT_URI)
    args = parser.parse_args()
    
    # Check if server is running
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(args.uri.replace("/ws/", "")) as response:
                    if response.status == 200:
                        logger.info("Server is running")
                    else:
                        logger.warning(f"Server returned status {response.status}")
            except Exception:
                logger.error("Server not running. Please start the server first.")
                logger.error("Run: uvicorn host:app --host 0.0.0.0 --port 9000")
                return
    except ImportError:
        logger.warning("aiohttp not installed, skipping server check")
    
    # Run tests
    runner = TestRunner(
        uri=args.uri,
        test_audio=args.test_audio,
        test_webhook=args.test_webhook
    )
    
    await runner.run_tests()

if __name__ == "__main__":
    asyncio.run(main())
