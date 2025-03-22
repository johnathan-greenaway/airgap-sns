#!/usr/bin/env python3
"""
Email Notification Runner for Airgap SNS

This script provides a command-line interface for the email notification module.
It listens to an email account via IMAP and relays notifications to a designated
data stream using the Airgap SNS notification system.

Usage:
    python -m airgap_sns.bin.run_email --email user@example.com --password mypassword --stream email-notifications
"""

import asyncio
import argparse
import logging
import os
import sys
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("airgap_sns.bin.run_email")

# Load environment variables from .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
    logger.info("Loaded environment variables from .env file")
except ImportError:
    logger.warning("python-dotenv not installed. Environment variables must be set manually.")

# Import from airgap_sns package
from airgap_sns.email.notification import (
    run_module,
    DEFAULT_URI,
    DEFAULT_CLIENT_ID,
    DEFAULT_CHECK_INTERVAL,
    DEFAULT_IMAP_SERVER,
    DEFAULT_IMAP_PORT,
    DEFAULT_STREAM_ID
)

def main():
    """Main entry point"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Email Notification Module for Airgap SNS")
    
    # Email settings
    parser.add_argument("--email", help="Email address", required=True)
    parser.add_argument("--password", help="Email password", required=True)
    parser.add_argument("--imap-server", help=f"IMAP server (default: {DEFAULT_IMAP_SERVER})", default=DEFAULT_IMAP_SERVER)
    parser.add_argument("--imap-port", help=f"IMAP port (default: {DEFAULT_IMAP_PORT})", type=int, default=DEFAULT_IMAP_PORT)
    parser.add_argument("--interval", help=f"Check interval in seconds (default: {DEFAULT_CHECK_INTERVAL})", type=int, default=DEFAULT_CHECK_INTERVAL)
    parser.add_argument("--folder", help="Email folder to check (default: INBOX)", default="INBOX")
    parser.add_argument("--filter-sender", help="Filter emails by sender")
    parser.add_argument("--filter-subject", help="Filter emails by subject")
    parser.add_argument("--since-days", help="Check emails from the last N days (default: 1)", type=int, default=1)
    
    # Notification settings
    parser.add_argument("--uri", help=f"Server URI (default: {DEFAULT_URI})", default=DEFAULT_URI)
    parser.add_argument("--client-id", help=f"Client ID (default: {DEFAULT_CLIENT_ID})", default=DEFAULT_CLIENT_ID)
    parser.add_argument("--stream", help=f"Stream ID (default: {DEFAULT_STREAM_ID})", default=DEFAULT_STREAM_ID)
    parser.add_argument("--encrypt", help="Encrypt notifications", action="store_true")
    parser.add_argument("--encrypt-password", help="Password for encryption")
    
    args = parser.parse_args()
    
    try:
        # Run the module
        asyncio.run(run_module(
            email_address=args.email,
            password=args.password,
            uri=args.uri,
            client_id=args.client_id,
            stream_id=args.stream,
            imap_server=args.imap_server,
            imap_port=args.imap_port,
            check_interval=args.interval,
            folder=args.folder,
            filter_sender=args.filter_sender,
            filter_subject=args.filter_subject,
            since_days=args.since_days,
            encrypt=args.encrypt,
            encryption_password=args.encrypt_password
        ))
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Error running email notification module: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
