# Email Notification Module for Airgap SNS

This module provides functionality for monitoring email accounts and sending notifications through the Airgap SNS system when new emails arrive.

## Features

- Connect to email servers via IMAP
- Monitor for new emails at configurable intervals
- Filter emails by sender, subject, or date
- Send notifications to Airgap SNS clients
- Support for encrypted notifications
- Customizable notification streams

## Installation

```bash
# Basic installation
pip install airgap_sns

# With email support
pip install airgap_sns[email]
```

## Usage

### Command Line

```bash
# Basic usage
airgap-sns-email --email user@example.com --password mypassword --stream email-notifications

# With filtering
airgap-sns-email --email user@example.com --password mypassword --filter-sender important@example.com

# With encryption
airgap-sns-email --email user@example.com --password mypassword --encrypt --encrypt-password mysecretkey
```

### Demo

The package includes a demo script that starts a server, client, and email notification module:

```bash
# Run the demo
airgap-sns-email-demo --email user@example.com --password mypassword
```

### Python API

```python
import asyncio
from airgap_sns.email.notification import EmailNotificationModule

async def main():
    # Create module
    module = EmailNotificationModule(
        email_address="user@example.com",
        password="mypassword",
        stream_id="email-notifications",
        check_interval=30  # seconds
    )
    
    # Start module
    await module.start()
    
    try:
        # Keep running until interrupted
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("Interrupted by user")
    finally:
        # Stop module
        await module.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

## Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `email` | Email address to monitor | (required) |
| `password` | Email password | (required) |
| `imap-server` | IMAP server hostname | imap.gmail.com |
| `imap-port` | IMAP server port | 993 |
| `interval` | Check interval in seconds | 60 |
| `folder` | Email folder to check | INBOX |
| `filter-sender` | Filter emails by sender | (none) |
| `filter-subject` | Filter emails by subject | (none) |
| `since-days` | Check emails from the last N days | 1 |
| `uri` | Server URI | ws://localhost:9000/ws/ |
| `client-id` | Client ID | email-listener |
| `stream` | Stream ID for notifications | email-notifications |
| `encrypt` | Encrypt notifications | false |
| `encrypt-password` | Password for encryption | (none) |

## Gmail Configuration

For Gmail accounts, you'll need to:

1. Enable IMAP in Gmail settings
2. Allow less secure apps or create an app password:
   - Go to your Google Account > Security
   - Enable 2-Step Verification if not already enabled
   - Go to App passwords
   - Select "Mail" and "Other (Custom name)"
   - Enter a name (e.g., "Airgap SNS")
   - Use the generated password with this module

## Security Considerations

- Store email passwords securely (e.g., in environment variables)
- Use encryption for sensitive email notifications
- Be aware that IMAP connections may transmit credentials in plaintext unless secured with SSL/TLS
- Consider using app-specific passwords rather than your main account password
