#!/usr/bin/env python3
"""
RSS Feed Integration Module for Airgap SNS

This module provides functionality to monitor RSS feeds and broadcast updates
through the Airgap SNS notification system. It can monitor multiple feeds
and distribute updates through various channels.

Features:
- Multiple feed monitoring with individual update intervals
- Custom message formatting for each feed
- Support for multiple output channels (burst, bluetooth, audio)
- Content filtering based on keywords
- Deduplication to prevent repeated notifications
- Background monitoring with minimal resource usage
"""

import asyncio
import logging
import time
import json
import re
import os
import argparse
import hashlib
from typing import Dict, List, Set, Optional, Any, Tuple, Callable
from urllib.parse import urlparse
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("airgap-sns-rss")

# Try to import required modules with graceful fallback
try:
    import feedparser
    import aiohttp
    import dateutil.parser
    RSS_AVAILABLE = True
except ImportError:
    logger.warning("RSS functionality not available. Required packages: feedparser, aiohttp, python-dateutil")
    RSS_AVAILABLE = False

# Try to import from the package
try:
    from airgap_sns.client.client import NotificationClient
    from airgap_sns.core.burst import parse_burst
except ImportError:
    try:
        # Fallback to direct import (for backward compatibility)
        from client import NotificationClient
        from burst import parse_burst
    except ImportError:
        logger.error("Could not import airgap_sns modules. Ensure airgap_sns is installed or in PYTHONPATH.")
        NotificationClient = None
        parse_burst = None

# Default settings
DEFAULT_UPDATE_INTERVAL = 300  # 5 minutes in seconds
DEFAULT_MAX_ITEMS = 10
DEFAULT_CHANNEL = "rss-updates"
DEFAULT_URI = "ws://localhost:9000/ws/"
DEFAULT_CLIENT_ID = "rss-monitor"
DEFAULT_FORMAT = "New article: {title} - {link}"

class FeedEntry:
    """Represents a single RSS feed entry with metadata"""
    
    def __init__(self, entry_data: Dict[str, Any], feed_title: str = None):
        """Initialize from feedparser entry"""
        self.id = entry_data.get('id', '')
        if not self.id and 'link' in entry_data:
            self.id = entry_data['link']
        if not self.id:
            # Generate hash-based ID if none exists
            hash_input = json.dumps(entry_data, sort_keys=True).encode()
            self.id = hashlib.md5(hash_input).hexdigest()
            
        self.title = entry_data.get('title', 'Untitled')
        self.link = entry_data.get('link', '')
        self.description = entry_data.get('description', entry_data.get('summary', ''))
        self.content = entry_data.get('content', [{}])[0].get('value', self.description)
        self.author = entry_data.get('author', '')
        self.feed_title = feed_title
        
        # Process published date
        self.published_parsed = None
        if 'published_parsed' in entry_data and entry_data['published_parsed']:
            self.published_parsed = entry_data['published_parsed']
            self.published = time.strftime('%Y-%m-%d %H:%M:%S', self.published_parsed)
        elif 'updated_parsed' in entry_data and entry_data['updated_parsed']:
            self.published_parsed = entry_data['updated_parsed']
            self.published = time.strftime('%Y-%m-%d %H:%M:%S', self.published_parsed)
        else:
            # Use current time as fallback
            self.published = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
        # Extract categories/tags
        self.categories = []
        if 'tags' in entry_data:
            for tag in entry_data['tags']:
                if 'term' in tag:
                    self.categories.append(tag['term'])
        elif 'categories' in entry_data:
            self.categories = entry_data['categories']
            
        # Create a dict representation for easy template formatting
        self.data = {
            'id': self.id,
            'title': self.title,
            'link': self.link,
            'description': self.description,
            'content': self.content,
            'author': self.author,
            'published': self.published,
            'categories': ', '.join(self.categories),
            'feed_title': self.feed_title
        }
    
    def matches_keywords(self, keywords: List[str]) -> bool:
        """Check if entry matches any of the given keywords"""
        if not keywords:
            return True  # No filtering
            
        text = f"{self.title} {self.description} {' '.join(self.categories)}".lower()
        for keyword in keywords:
            if keyword.lower() in text:
                return True
                
        return False
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return self.data
        
    def format(self, template: str) -> str:
        """Format the entry using the template"""
        try:
            return template.format(**self.data)
        except KeyError as e:
            logger.warning(f"Template key error: {e} - using default format")
            return f"New article: {self.title} - {self.link}"
        except Exception as e:
            logger.error(f"Error formatting entry: {e}")
            return f"New article: {self.title} - {self.link}"

class RssFeed:
    """Represents a single RSS feed with monitoring configuration"""
    
    def __init__(
        self,
        url: str,
        name: Optional[str] = None,
        update_interval: int = DEFAULT_UPDATE_INTERVAL,
        max_items: int = DEFAULT_MAX_ITEMS,
        format_template: str = DEFAULT_FORMAT,
        channel: str = DEFAULT_CHANNEL,
        keywords: Optional[List[str]] = None,
        output_methods: Optional[List[str]] = None
    ):
        """Initialize RSS feed with monitoring parameters"""
        self.url = url
        self.name = name or urlparse(url).netloc
        self.update_interval = update_interval
        self.max_items = max_items
        self.format_template = format_template
        self.channel = channel
        self.keywords = keywords or []
        self.output_methods = output_methods or ["burst"]  # burst, bluetooth, audio
        
        # Internal state
        self.last_update = 0
        self.known_entries: Set[str] = set()
        self.etag = None
        self.modified = None
        self.error_count = 0
        self.max_errors = 5
    
    async def check_updates(self) -> List[FeedEntry]:
        """Check for updates in the feed"""
        if not RSS_AVAILABLE:
            logger.error("RSS functionality not available")
            return []
            
        current_time = time.time()
        
        # Skip if not time to update yet
        if current_time - self.last_update < self.update_interval:
            return []
            
        logger.info(f"Checking for updates in feed: {self.name}")
        
        try:
            # Modified and ETag for conditional fetch
            kwargs = {}
            if self.modified:
                kwargs['modified'] = self.modified
            if self.etag:
                kwargs['etag'] = self.etag
                
            # Parse feed
            feed = await asyncio.get_event_loop().run_in_executor(
                None, lambda: feedparser.parse(self.url, **kwargs)
            )
            
            # Update feed metadata
            self.etag = feed.get('etag', None)
            self.modified = feed.get('modified', None)
            self.last_update = current_time
            
            # Reset error count on success
            self.error_count = 0
            
            # Check for new entries
            new_entries = []
            feed_title = feed.feed.get('title', self.name)
            
            for entry_data in feed.entries[:self.max_items]:
                entry = FeedEntry(entry_data, feed_title)
                
                # Check if entry is new and matches keywords
                if entry.id not in self.known_entries and entry.matches_keywords(self.keywords):
                    self.known_entries.add(entry.id)
                    new_entries.append(entry)
                    
            if new_entries:
                logger.info(f"Found {len(new_entries)} new entries in feed: {self.name}")
            
            return new_entries
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"Error checking feed {self.name}: {e}")
            
            # If too many errors, increase the update interval
            if self.error_count >= self.max_errors:
                self.update_interval *= 2
                logger.warning(f"Too many errors for feed {self.name}, increasing update interval to {self.update_interval}s")
                self.error_count = 0
                
            return []

class RssFeedMonitor:
    """Monitors multiple RSS feeds and broadcasts updates through the SNS system"""
    
    def __init__(
        self,
        sns_uri: str = DEFAULT_URI,
        client_id: str = DEFAULT_CLIENT_ID,
        output_config: Optional[Dict[str, Any]] = None
    ):
        """Initialize RSS feed monitor"""
        if not RSS_AVAILABLE:
            raise RuntimeError("RSS functionality not available. Required packages: feedparser, aiohttp, python-dateutil")
            
        self.sns_uri = sns_uri
        self.client_id = client_id
        self.output_config = output_config or {
            "burst": {"enabled": True},
            "bluetooth": {"enabled": False, "ttl": 5},
            "audio": {"enabled": False}
        }
        
        # Feeds to monitor
        self.feeds: List[RssFeed] = []
        
        # Client for SNS system
        self.client = None
        
        # Control flags
        self.running = False
        self.feed_check_interval = 60  # How often to check feeds (in seconds)
        
    def add_feed(self, feed: RssFeed) -> None:
        """Add a feed to monitor"""
        self.feeds.append(feed)
        logger.info(f"Added feed: {feed.name} ({feed.url})")
        
    def remove_feed(self, url: str) -> bool:
        """Remove a feed by URL"""
        for i, feed in enumerate(self.feeds):
            if feed.url == url:
                self.feeds.pop(i)
                logger.info(f"Removed feed: {feed.name} ({feed.url})")
                return True
                
        return False
        
    async def start(self) -> None:
        """Start the RSS feed monitor"""
        # Connect to SNS system
        self.client = NotificationClient(
            uri=self.sns_uri,
            client_id=self.client_id
        )
        
        if not await self.client.connect():
            logger.error("Failed to connect to SNS system")
            return
            
        logger.info(f"Connected to SNS system as {self.client_id}")
        
        # Start monitoring loop
        self.running = True
        
        try:
            while self.running:
                await self._check_all_feeds()
                await asyncio.sleep(self.feed_check_interval)
                
        except asyncio.CancelledError:
            logger.info("RSS feed monitor cancelled")
        except Exception as e:
            logger.error(f"Error in RSS feed monitor: {e}")
        finally:
            await self.stop()
            
    async def stop(self) -> None:
        """Stop the RSS feed monitor"""
        self.running = False
        
        if self.client:
            await self.client.close()
            self.client = None
            
        logger.info("RSS feed monitor stopped")
        
    async def _check_all_feeds(self) -> None:
        """Check all feeds for updates"""
        for feed in self.feeds:
            new_entries = await feed.check_updates()
            
            for entry in new_entries:
                await self._broadcast_entry(entry, feed)
                
    async def _broadcast_entry(self, entry: FeedEntry, feed: RssFeed) -> None:
        """Broadcast a feed entry through configured output methods"""
        if not self.client:
            logger.error("Not connected to SNS system")
            return
            
        try:
            # Format the message
            message = entry.format(feed.format_template)
            
            # Prepare parameters for burst message
            burst_params = {"wc": feed.channel}
            
            # Add method-specific parameters based on feed configuration
            if "bluetooth" in feed.output_methods and self.output_config["bluetooth"]["enabled"]:
                burst_params["bluetooth"] = "tx"
                
            if "audio" in feed.output_methods and self.output_config["audio"]["enabled"]:
                burst_params["audio"] = "tx"
                
            # Create and send the burst message
            burst = self.client.create_burst_message(**burst_params)
            full_message = f"{message} {burst}"
            
            await self.client.send_burst(full_message)
            logger.info(f"Broadcast entry: {entry.title} to channel: {feed.channel}")
            
        except Exception as e:
            logger.error(f"Error broadcasting entry: {e}")

def load_feeds_from_config(config_file: str) -> List[RssFeed]:
    """Load feeds from a configuration file"""
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
            
        feeds = []
        for feed_config in config.get('feeds', []):
            feed = RssFeed(
                url=feed_config['url'],
                name=feed_config.get('name'),
                update_interval=feed_config.get('update_interval', DEFAULT_UPDATE_INTERVAL),
                max_items=feed_config.get('max_items', DEFAULT_MAX_ITEMS),
                format_template=feed_config.get('format', DEFAULT_FORMAT),
                channel=feed_config.get('channel', DEFAULT_CHANNEL),
                keywords=feed_config.get('keywords', []),
                output_methods=feed_config.get('output_methods', ["burst"])
            )
            feeds.append(feed)
            
        return feeds
    except Exception as e:
        logger.error(f"Error loading feeds from config file: {e}")
        return []

async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="RSS Feed Monitor for Airgap SNS")
    parser.add_argument("--config", help="Path to configuration file", default="rss_config.json")
    parser.add_argument("--uri", help=f"SNS URI (default: {DEFAULT_URI})", default=DEFAULT_URI)
    parser.add_argument("--client-id", help=f"Client ID (default: {DEFAULT_CLIENT_ID})", default=DEFAULT_CLIENT_ID)
    parser.add_argument("--url", help="Add a single feed URL", default=None)
    parser.add_argument("--interval", help="Update interval in seconds", type=int, default=DEFAULT_UPDATE_INTERVAL)
    parser.add_argument("--channel", help=f"Channel for notifications (default: {DEFAULT_CHANNEL})", default=DEFAULT_CHANNEL)
    args = parser.parse_args()
    
    if not RSS_AVAILABLE:
        print("Error: RSS functionality not available. Required packages:")
        print("  pip install feedparser aiohttp python-dateutil")
        return
        
    # Configure output methods
    output_config = {
        "burst": {"enabled": True},
        "bluetooth": {"enabled": True, "ttl": 5},
        "audio": {"enabled": True}
    }
    
    # Create monitor
    monitor = RssFeedMonitor(
        sns_uri=args.uri,
        client_id=args.client_id,
        output_config=output_config
    )
    
    # Load feeds from config if specified
    if os.path.exists(args.config):
        feeds = load_feeds_from_config(args.config)
        for feed in feeds:
            monitor.add_feed(feed)
    elif not args.url:
        print("No configuration file found and no URL specified.")
        print("Please either:")
        print("  1. Create a configuration file (see rss_config.json.sample)")
        print("  2. Specify a feed URL with --url")
        return
        
    # Add single feed if specified
    if args.url:
        feed = RssFeed(
            url=args.url,
            update_interval=args.interval,
            channel=args.channel
        )
        monitor.add_feed(feed)
        
    if not monitor.feeds:
        print("No feeds configured.")
        return
        
    print(f"Starting RSS monitor with {len(monitor.feeds)} feeds")
    for i, feed in enumerate(monitor.feeds):
        print(f"{i+1}. {feed.name} ({feed.url})")
        print(f"   Checking every {feed.update_interval} seconds")
        print(f"   Broadcasting to channel: {feed.channel}")
        if feed.keywords:
            print(f"   Keywords: {', '.join(feed.keywords)}")
        print()
        
    try:
        await monitor.start()
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        await monitor.stop()

if __name__ == "__main__":
    asyncio.run(main())