"""
Email notification module for Airgap SNS.

This module provides functionality for monitoring email accounts and
sending notifications through the Airgap SNS system when new emails arrive.
"""

import asyncio
import logging
import os
import sys
import re
import json
import imaplib
import email
import time
from email.header import decode_header
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("airgap_sns.email")

# Load environment variables from .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
    logger.info("Loaded environment variables from .env file")
except ImportError:
    logger.warning("python-dotenv not installed. Environment variables must be set manually.")

# Import from airgap_sns package
from airgap_sns.client.client import NotificationClient
from airgap_sns.core.burst import parse_burst

# Default settings
DEFAULT_URI = "ws://localhost:9000/ws/"
DEFAULT_CLIENT_ID = "email-listener"
DEFAULT_CHECK_INTERVAL = 60  # seconds
DEFAULT_IMAP_SERVER = "imap.gmail.com"
DEFAULT_IMAP_PORT = 993
DEFAULT_STREAM_ID = "email-notifications"

class EmailListener:
    """Email listener that connects to an IMAP server and monitors for new emails"""
    
    def __init__(
        self,
        email_address: str,
        password: str,
        imap_server: str = DEFAULT_IMAP_SERVER,
        imap_port: int = DEFAULT_IMAP_PORT,
        check_interval: int = DEFAULT_CHECK_INTERVAL,
        folder: str = "INBOX",
        filter_sender: Optional[str] = None,
        filter_subject: Optional[str] = None,
        since_days: int = 1
    ):
        """Initialize the email listener"""
        self.email_address = email_address
        self.password = password
        self.imap_server = imap_server
        self.imap_port = imap_port
        self.check_interval = check_interval
        self.folder = folder
        self.filter_sender = filter_sender
        self.filter_subject = filter_subject
        self.since_days = since_days
        self.last_check_time = datetime.now() - timedelta(days=since_days)
        self.running = False
        self.mail = None
        
    def connect(self) -> bool:
        """Connect to the IMAP server"""
        try:
            # Create an IMAP4 class with SSL
            self.mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            
            # Authenticate
            self.mail.login(self.email_address, self.password)
            
            # Select the mailbox
            self.mail.select(self.folder)
            
            logger.info(f"Connected to {self.imap_server} as {self.email_address}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to email server: {str(e)}")
            return False
    
    def disconnect(self):
        """Disconnect from the IMAP server"""
        if self.mail:
            try:
                self.mail.close()
                self.mail.logout()
                logger.info("Disconnected from email server")
            except Exception as e:
                logger.error(f"Error disconnecting from email server: {str(e)}")
    
    def build_search_criteria(self) -> str:
        """Build the search criteria for finding new emails"""
        criteria = []
        
        # Add date criteria
        date_str = self.last_check_time.strftime("%d-%b-%Y")
        criteria.append(f'(SINCE "{date_str}")')
        
        # Add sender filter if specified
        if self.filter_sender:
            criteria.append(f'(FROM "{self.filter_sender}")')
        
        # Add subject filter if specified
        if self.filter_subject:
            criteria.append(f'(SUBJECT "{self.filter_subject}")')
        
        # Combine all criteria
        return " ".join(criteria)
    
    def check_emails(self) -> List[Dict[str, Any]]:
        """Check for new emails and return them as a list of dictionaries"""
        if not self.mail:
            logger.error("Not connected to email server")
            return []
        
        try:
            # Build search criteria
            search_criteria = self.build_search_criteria()
            
            # Search for emails matching criteria
            status, messages = self.mail.search(None, search_criteria)
            
            if status != "OK":
                logger.error(f"Error searching for emails: {status}")
                return []
            
            # Get list of email IDs
            email_ids = messages[0].split()
            
            # Update last check time
            self.last_check_time = datetime.now()
            
            # If no new emails, return empty list
            if not email_ids:
                logger.info("No new emails found")
                return []
            
            logger.info(f"Found {len(email_ids)} new emails")
            
            # Process each email
            emails = []
            for email_id in email_ids:
                email_data = self.fetch_email(email_id)
                if email_data:
                    emails.append(email_data)
            
            return emails
        except Exception as e:
            logger.error(f"Error checking emails: {str(e)}")
            return []
    
    def fetch_email(self, email_id: bytes) -> Optional[Dict[str, Any]]:
        """Fetch and parse an email by ID"""
        try:
            # Fetch the email
            status, msg_data = self.mail.fetch(email_id, "(RFC822)")
            
            if status != "OK":
                logger.error(f"Error fetching email {email_id}: {status}")
                return None
            
            # Parse the email
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            # Extract email details
            subject = self.decode_email_header(msg["Subject"])
            from_addr = self.decode_email_header(msg["From"])
            date_str = self.decode_email_header(msg["Date"])
            
            # Extract body
            body = ""
            if msg.is_multipart():
                # Handle multipart emails
                for part in msg.walk():
                    content_type = part.get_content_type()
                    content_disposition = str(part.get("Content-Disposition"))
                    
                    # Skip attachments
                    if "attachment" in content_disposition:
                        continue
                    
                    # Get text content
                    if content_type == "text/plain":
                        body_part = part.get_payload(decode=True)
                        if body_part:
                            body += body_part.decode()
            else:
                # Handle single part emails
                body = msg.get_payload(decode=True).decode()
            
            # Create email data dictionary
            email_data = {
                "id": email_id.decode(),
                "subject": subject,
                "from": from_addr,
                "date": date_str,
                "body": body.strip(),
                "raw_email": raw_email.decode()
            }
            
            logger.info(f"Fetched email: {subject} from {from_addr}")
            return email_data
        except Exception as e:
            logger.error(f"Error fetching email {email_id}: {str(e)}")
            return None
    
    def decode_email_header(self, header: Optional[str]) -> str:
        """Decode email header"""
        if not header:
            return ""
        
        try:
            decoded_header = decode_header(header)
            header_parts = []
            
            for part, encoding in decoded_header:
                if isinstance(part, bytes):
                    if encoding:
                        header_parts.append(part.decode(encoding))
                    else:
                        header_parts.append(part.decode())
                else:
                    header_parts.append(part)
            
            return " ".join(header_parts)
        except Exception as e:
            logger.error(f"Error decoding header: {str(e)}")
            return header
    
    async def start(self, callback):
        """Start the email listener"""
        self.running = True
        
        # Connect to the email server
        if not self.connect():
            logger.error("Failed to start email listener")
            return
        
        logger.info(f"Email listener started. Checking every {self.check_interval} seconds")
        
        try:
            while self.running:
                # Check for new emails
                emails = self.check_emails()
                
                # Process each email
                for email_data in emails:
                    await callback(email_data)
                
                # Wait for next check
                await asyncio.sleep(self.check_interval)
        except asyncio.CancelledError:
            logger.info("Email listener task cancelled")
        except Exception as e:
            logger.error(f"Error in email listener: {str(e)}")
        finally:
            self.disconnect()
            self.running = False
    
    def stop(self):
        """Stop the email listener"""
        self.running = False
        logger.info("Email listener stopped")

class EmailNotificationModule:
    """Module that listens to email and relays notifications to a data stream"""
    
    def __init__(
        self,
        email_address: str,
        password: str,
        uri: str = DEFAULT_URI,
        client_id: str = DEFAULT_CLIENT_ID,
        stream_id: str = DEFAULT_STREAM_ID,
        imap_server: str = DEFAULT_IMAP_SERVER,
        imap_port: int = DEFAULT_IMAP_PORT,
        check_interval: int = DEFAULT_CHECK_INTERVAL,
        folder: str = "INBOX",
        filter_sender: Optional[str] = None,
        filter_subject: Optional[str] = None,
        since_days: int = 1,
        encrypt: bool = False,
        encryption_password: Optional[str] = None
    ):
        """Initialize the email notification module"""
        self.email_address = email_address
        self.password = password
        self.uri = uri
        self.client_id = client_id
        self.stream_id = stream_id
        self.encrypt = encrypt
        self.encryption_password = encryption_password
        
        # Create email listener
        self.email_listener = EmailListener(
            email_address=email_address,
            password=password,
            imap_server=imap_server,
            imap_port=imap_port,
            check_interval=check_interval,
            folder=folder,
            filter_sender=filter_sender,
            filter_subject=filter_subject,
            since_days=since_days
        )
        
        # Create notification client
        self.notification_client = None
        self.task = None
    
    async def connect(self) -> bool:
        """Connect to the notification server"""
        try:
            # Create notification client
            self.notification_client = NotificationClient(
                uri=self.uri,
                client_id=self.client_id,
                password=self.encryption_password
            )
            
            # Connect to server
            return await self.notification_client.connect()
        except Exception as e:
            logger.error(f"Failed to connect to notification server: {str(e)}")
            return False
    
    async def process_email(self, email_data: Dict[str, Any]):
        """Process an email and send a notification"""
        if not self.notification_client:
            logger.error("Not connected to notification server")
            return
        
        try:
            # Create notification message
            subject = email_data["subject"]
            sender = email_data["from"]
            
            # Create message content
            message = f"New email from {sender}: {subject}"
            
            # Create burst parameters
            burst_params = {
                "dest": self.client_id,
                "wc": self.stream_id
            }
            
            # Add encryption if enabled
            if self.encrypt and self.encryption_password:
                burst_params["encrypt"] = "yes"
                burst_params["pwd"] = self.encryption_password
            
            # Create burst message
            burst = self.notification_client.create_burst_message(**burst_params)
            
            # Send notification
            full_message = f"{message} {burst}"
            await self.notification_client.send_burst(full_message)
            
            logger.info(f"Sent notification for email: {subject}")
        except Exception as e:
            logger.error(f"Error processing email: {str(e)}")
    
    async def start(self):
        """Start the email notification module"""
        # Connect to notification server
        if not await self.connect():
            logger.error("Failed to start email notification module")
            return
        
        # Start email listener
        self.task = asyncio.create_task(
            self.email_listener.start(self.process_email)
        )
        
        logger.info("Email notification module started")
    
    async def stop(self):
        """Stop the email notification module"""
        # Stop email listener
        self.email_listener.stop()
        
        # Cancel task
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        # Close notification client
        if self.notification_client:
            await self.notification_client.close()
        
        logger.info("Email notification module stopped")

async def run_module(
    email_address: str,
    password: str,
    uri: str = DEFAULT_URI,
    client_id: str = DEFAULT_CLIENT_ID,
    stream_id: str = DEFAULT_STREAM_ID,
    imap_server: str = DEFAULT_IMAP_SERVER,
    imap_port: int = DEFAULT_IMAP_PORT,
    check_interval: int = DEFAULT_CHECK_INTERVAL,
    folder: str = "INBOX",
    filter_sender: Optional[str] = None,
    filter_subject: Optional[str] = None,
    since_days: int = 1,
    encrypt: bool = False,
    encryption_password: Optional[str] = None
):
    """Run the email notification module"""
    # Create module
    module = EmailNotificationModule(
        email_address=email_address,
        password=password,
        uri=uri,
        client_id=client_id,
        stream_id=stream_id,
        imap_server=imap_server,
        imap_port=imap_port,
        check_interval=check_interval,
        folder=folder,
        filter_sender=filter_sender,
        filter_subject=filter_subject,
        since_days=since_days,
        encrypt=encrypt,
        encryption_password=encryption_password
    )
    
    # Start module
    await module.start()
    
    try:
        # Keep running until interrupted
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        # Stop module
        await module.stop()
