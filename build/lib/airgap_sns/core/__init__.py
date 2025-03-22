"""
Core functionality for the Airgap SNS package.

This module contains the core components used by both the host and client.
"""

from airgap_sns.core.burst import parse_burst, BurstParams
from airgap_sns.core.crypto import encrypt, decrypt
from airgap_sns.core.webhook import send_webhook
from airgap_sns.core.scheduler import schedule_job

# Try to import audio module with graceful fallback
try:
    from airgap_sns.core.audio import (
        AudioTransceiver, 
        async_transmit, 
        async_receive, 
        AUDIO_AVAILABLE
    )
except ImportError:
    import logging
    logging.warning("Audio module not available. Audio features disabled.")
    AUDIO_AVAILABLE = False
