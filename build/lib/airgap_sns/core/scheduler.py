import asyncio, aiohttp, logging
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("airgap-sns-scheduler")

# Import from the new package structure
from airgap_sns.core.crypto import encrypt
from airgap_sns.core.webhook import send_webhook

# Try to import audio module with graceful fallback
try:
    from airgap_sns.core.audio import async_transmit, AUDIO_AVAILABLE
except ImportError:
    logger.warning("Audio module not available. Audio features disabled.")
    AUDIO_AVAILABLE = False

# Try to import Bluetooth mesh module with graceful fallback
try:
    from airgap_sns.core.bluetooth_mesh import BluetoothMeshTransceiver, BLUETOOTH_AVAILABLE
except ImportError:
    try:
        from bluetooth_mesh import BluetoothMeshTransceiver, BLUETOOTH_AVAILABLE
    except ImportError:
        BLUETOOTH_AVAILABLE = False
        logger.warning("Bluetooth mesh module not available. Bluetooth features disabled.")

async def schedule_job(params: Dict[str, Any], payload: str, pubsub: Any) -> None:
    """
    Orchestrate notification delivery with validation and error handling
    
    Args:
        params: Parsed burst parameters
        payload: The original message payload
        pubsub: The PubSub instance for message delivery
    """
    try:
        # Get password if provided
        password = params.get("pwd")
        
        # Encrypt if required (using password if provided)
        should_encrypt = params.get("encrypt") == "yes" or params.get("encrypt") is True
        if should_encrypt:
            try:
                if password:
                    msg = encrypt(payload, password)
                    logger.info("Message encrypted with provided password")
                else:
                    # Use a default password or environment variable
                    import os
                    default_pwd = os.getenv("AIRGAP_DEFAULT_PWD", "default-secure-password")
                    msg = encrypt(payload, default_pwd)
                    logger.info("Message encrypted with default password")
            except Exception as e:
                logger.error(f"Encryption failed: {str(e)}")
                msg = payload  # Fallback to unencrypted if encryption fails
        else:
            msg = payload
        
        delivery_count = 0
        
        # Send direct notification
        if dest := params.get("dest"):
            success = await pubsub.send(dest, msg)
            if success:
                delivery_count += 1
                logger.info(f"Notification sent to destination: {dest}")
            
        # Broadcast to water-cooler channel
        if wc := params.get("wc"):
            channel = f'wc-{wc}'
            await pubsub.broadcast(channel, msg)
            logger.info(f"Notification broadcast to channel: {channel}")
            delivery_count += 1
            
        # Trigger webhook
        if webhook_url := params.get("webhook"):
            try:
                webhook_data = {
                    'message': msg,
                    'metadata': {
                        'destination': params.get("dest"),
                        'channel': params.get("wc"),
                        'encrypted': should_encrypt,
                        'audio': params.get("audio"),
                        'bluetooth': params.get("bluetooth")
                    }
                }
                
                success = await send_webhook(
                    url=webhook_url,
                    data=webhook_data
                )
                
                if success:
                    delivery_count += 1
                    logger.info(f"Webhook delivered to: {webhook_url}")
            except Exception as e:
                logger.error(f"Webhook delivery failed: {str(e)}")
        
        # Handle audio transmission if requested and not already handled by host
        if params.get("audio") == "tx" and AUDIO_AVAILABLE and hasattr(pubsub, "transmit_audio"):
            # Audio transmission is handled by the host in a background task
            pass
        
        # Handle Bluetooth mesh transmission if requested
        if params.get("bluetooth") == "tx" and BLUETOOTH_AVAILABLE and hasattr(pubsub, "transmit_bluetooth"):
            try:
                await pubsub.transmit_bluetooth(msg, params.get("dest"))
                delivery_count += 1
                logger.info(f"Message transmitted via Bluetooth mesh")
            except Exception as e:
                logger.error(f"Bluetooth mesh transmission failed: {str(e)}")
            
        logger.info(f"Notification job completed with {delivery_count} deliveries")
            
    except Exception as e:
        logger.error(f"Notification job failed: {str(e)}")
        # Don't re-raise to prevent connection termination