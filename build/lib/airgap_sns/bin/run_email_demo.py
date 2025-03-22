#!/usr/bin/env python3
"""
Email Notification Demo for Airgap SNS

This script demonstrates the email notification module by:
1. Starting the Airgap SNS server
2. Starting a client that listens to the email notification stream
3. Starting the email notification module

Usage:
    python -m airgap_sns.bin.run_email_demo --email user@example.com --password mypassword
"""

import asyncio
import argparse
import logging
import os
import sys
import subprocess
import time
import signal
import threading
from typing import Optional, List, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("airgap_sns.bin.run_email_demo")

# Load environment variables from .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
    logger.info("Loaded environment variables from .env file")
except ImportError:
    logger.warning("python-dotenv not installed. Environment variables must be set manually.")

# Import from airgap_sns package
from airgap_sns.email.notification import (
    DEFAULT_URI,
    DEFAULT_CLIENT_ID,
    DEFAULT_CHECK_INTERVAL,
    DEFAULT_IMAP_SERVER,
    DEFAULT_IMAP_PORT,
    DEFAULT_STREAM_ID
)

# Default settings
DEFAULT_DEMO_CLIENT_ID = "email-demo"

class ProcessManager:
    """Manages subprocesses for the demo"""
    
    def __init__(self):
        """Initialize the process manager"""
        self.processes = {}
        self.running = True
        
    def start_process(self, name: str, cmd: List[str], env: Optional[Dict[str, str]] = None):
        """Start a subprocess"""
        try:
            # Create environment
            process_env = os.environ.copy()
            if env:
                process_env.update(env)
            
            # Start process
            process = subprocess.Popen(
                cmd,
                env=process_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            
            # Store process
            self.processes[name] = process
            
            # Start output thread
            threading.Thread(
                target=self._process_output,
                args=(name, process),
                daemon=True
            ).start()
            
            logger.info(f"Started {name}: {' '.join(cmd)}")
            return True
        except Exception as e:
            logger.error(f"Failed to start {name}: {str(e)}")
            return False
    
    def _process_output(self, name: str, process: subprocess.Popen):
        """Process output from a subprocess"""
        prefix = f"[{name}] "
        try:
            for line in iter(process.stdout.readline, ""):
                if not self.running:
                    break
                print(f"{prefix}{line.rstrip()}")
        except Exception as e:
            logger.error(f"Error reading output from {name}: {str(e)}")
    
    def stop_all(self):
        """Stop all subprocesses"""
        self.running = False
        
        for name, process in self.processes.items():
            try:
                logger.info(f"Stopping {name}...")
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning(f"{name} did not terminate, killing...")
                process.kill()
            except Exception as e:
                logger.error(f"Error stopping {name}: {str(e)}")
        
        self.processes = {}
        logger.info("All processes stopped")

def run_demo(args):
    """Run the email notification demo"""
    # Create process manager
    manager = ProcessManager()
    
    try:
        # Start server
        server_cmd = [
            sys.executable, "-m", "uvicorn", "host:app",
            "--host", "0.0.0.0", "--port", "9000"
        ]
        if not manager.start_process("server", server_cmd):
            logger.error("Failed to start server")
            return False
        
        # Wait for server to start
        logger.info("Waiting for server to start...")
        time.sleep(2)
        
        # Start client
        client_cmd = [
            sys.executable, "client.py",
            "--id", args.client_id,
            "--interactive"
        ]
        if not manager.start_process("client", client_cmd):
            logger.error("Failed to start client")
            return False
        
        # Start email notification module
        email_cmd = [
            sys.executable, "-m", "airgap_sns.bin.run_email",
            "--email", args.email,
            "--password", args.password,
            "--imap-server", args.imap_server,
            "--imap-port", str(args.imap_port),
            "--interval", str(args.interval),
            "--stream", args.stream,
            "--client-id", args.client_id
        ]
        
        # Add optional arguments
        if args.folder:
            email_cmd.extend(["--folder", args.folder])
        
        if args.filter_sender:
            email_cmd.extend(["--filter-sender", args.filter_sender])
        
        if args.filter_subject:
            email_cmd.extend(["--filter-subject", args.filter_subject])
        
        if args.since_days:
            email_cmd.extend(["--since-days", str(args.since_days)])
        
        if args.encrypt:
            email_cmd.append("--encrypt")
        
        if args.encrypt_password:
            email_cmd.extend(["--encrypt-password", args.encrypt_password])
        
        if not manager.start_process("email", email_cmd):
            logger.error("Failed to start email notification module")
            return False
        
        # Print demo information
        print("\n" + "=" * 60)
        print("Email Notification Demo for Airgap SNS")
        print("=" * 60)
        print(f"\nThis demo is running with the following configuration:")
        print(f"- Email: {args.email}")
        print(f"- IMAP Server: {args.imap_server}:{args.imap_port}")
        print(f"- Check Interval: {args.interval} seconds")
        print(f"- Stream ID: {args.stream}")
        print(f"- Client ID: {args.client_id}")
        if args.filter_sender:
            print(f"- Filter Sender: {args.filter_sender}")
        if args.filter_subject:
            print(f"- Filter Subject: {args.filter_subject}")
        if args.encrypt:
            print(f"- Encryption: Enabled")
        print("\nProcesses:")
        print("1. Server - The Airgap SNS server")
        print("2. Client - A client listening to the email notification stream")
        print("3. Email - The email notification module")
        print("\nPress Ctrl+C to stop the demo")
        print("=" * 60 + "\n")
        
        # Wait for user to stop the demo
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        # Stop all processes
        manager.stop_all()
    
    return True

def main():
    """Main entry point"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Email Notification Demo for Airgap SNS")
    
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
    parser.add_argument("--client-id", help=f"Client ID (default: {DEFAULT_DEMO_CLIENT_ID})", default=DEFAULT_DEMO_CLIENT_ID)
    parser.add_argument("--stream", help=f"Stream ID (default: {DEFAULT_STREAM_ID})", default=DEFAULT_STREAM_ID)
    parser.add_argument("--encrypt", help="Encrypt notifications", action="store_true")
    parser.add_argument("--encrypt-password", help="Password for encryption")
    
    args = parser.parse_args()
    
    # Run the demo
    if not run_demo(args):
        sys.exit(1)

if __name__ == "__main__":
    main()
