#!/usr/bin/env python3
"""
Simple webhook test server for Airgap SNS

This server listens for webhook notifications from the Airgap SNS system
and logs them to the console. It's useful for testing the webhook functionality.

Usage:
    python webhook_test_server.py [--port PORT]
"""

import asyncio
import argparse
import logging
import json
from typing import Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("webhook-test-server")

try:
    from fastapi import FastAPI, Request
    import uvicorn
except ImportError:
    logger.error("Required modules not found. Please install: pip install fastapi uvicorn")
    exit(1)

# Create FastAPI app
app = FastAPI(title="Webhook Test Server", description="Test server for Airgap SNS webhooks")

# Store received webhooks
received_webhooks = []

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "Webhook Test Server",
        "received_count": len(received_webhooks),
        "webhooks": received_webhooks
    }

@app.post("/webhook")
async def webhook(request: Request):
    """Webhook endpoint"""
    try:
        # Get request body
        body = await request.json()
        
        # Log webhook
        logger.info(f"Received webhook: {json.dumps(body, indent=2)}")
        
        # Store webhook
        received_webhooks.append({
            "timestamp": asyncio.get_event_loop().time(),
            "data": body
        })
        
        # Keep only the last 10 webhooks
        if len(received_webhooks) > 10:
            received_webhooks.pop(0)
        
        return {"status": "success", "message": "Webhook received"}
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return {"status": "error", "message": str(e)}

@app.get("/webhooks")
async def list_webhooks():
    """List received webhooks"""
    return {
        "count": len(received_webhooks),
        "webhooks": received_webhooks
    }

@app.delete("/webhooks")
async def clear_webhooks():
    """Clear received webhooks"""
    received_webhooks.clear()
    return {"status": "success", "message": "Webhooks cleared"}

def main():
    """Main entry point"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Webhook Test Server")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    args = parser.parse_args()
    
    # Start server
    logger.info(f"Starting webhook test server on port {args.port}")
    uvicorn.run(app, host="0.0.0.0", port=args.port)

if __name__ == "__main__":
    main()
