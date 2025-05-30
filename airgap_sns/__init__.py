"""
Airgap SNS - Secure Notification System

A secure notification system with audio capabilities, webhooks, and encryption.
"""

__version__ = "1.0.0"

# Import key modules for easier access
from airgap_sns.core import (
    parse_burst, 
    encrypt, 
    decrypt, 
    send_webhook, 
    schedule_job
)

# Try to import audio module with graceful fallback
try:
    from airgap_sns.core import (
        AudioTransceiver, 
        async_transmit, 
        async_receive, 
        AUDIO_AVAILABLE
    )
except ImportError:
    import logging
    logging.warning("Audio module not available. Audio features disabled.")
    AUDIO_AVAILABLE = False

# Import host module
from airgap_sns.host import app as host_app, run_server, PubSub

# Import client module
from airgap_sns.client import NotificationClient, run_client

# Import chat module with graceful fallback
try:
    from airgap_sns.chat import ChatClient, run_chat_app, ChatMessage
except ImportError:
    import logging
    logging.warning("Chat module not available. Chat features disabled.")
    ChatClient = None
    run_chat_app = None
    ChatMessage = None

# Import bin module (command-line scripts)
import airgap_sns.bin
