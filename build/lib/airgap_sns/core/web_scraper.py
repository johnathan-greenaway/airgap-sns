import asyncio
import os
import re
import time
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from readability import Document
import httpx
import requests
from dotenv import load_dotenv
from ..client.client import AirgapClient

load_dotenv()

class WebScraperModule(AirgapClient):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.last_request_time = 0
        self.rate_limit = float(kwargs.get('rate_limit', 1.0))
        self.user_agent = kwargs.get('user_agent', 'Mozilla/5.0 (compatible; AirgapSNS/1.0; +https://github.com/airgap-sns)')
        self.timeout = int(kwargs.get('timeout', 30))
        self.max_text_length = int(kwargs.get('max_text_length', 1000))
        self.summary_length = int(kwargs.get('summary_length', 500))
        self.proxy = kwargs.get('proxy')
        self.ignore_robots = kwargs.get('ignore_robots', False)
        
        self.register_command_handler('scrape', self.handle_scrape_command)
        self.register_command_handler('help', self.handle_help_command)
        self.register_command_handler('status', self.handle_status_command)

    async def handle_scrape_command(self, args, sender):
        """Handle !scrape commands with URL"""
        if not args:
            await self.send_message("Usage: !scrape [URL]", sender)
            return
            
        url = args.strip()
        await self.process_url(url, sender)

    async def handle_help_command(self, args, sender):
        """Show help information"""
        help_text = """Web Scraper Commands:
!scrape [URL] - Scrape a webpage
!status - Show scraper status
!help - Show this help"""
        await self.send_message(help_text, sender)

    async def handle_status_command(self, args, sender):
        """Show current scraper status"""
        status = f"""Scraper Status:
- Rate Limit: {self.rate_limit}s
- Requests Count: {self.request_count}
- Proxy: {self.proxy or 'None'}
- User Agent: {self.user_agent}"""
        await self.send_message(status, sender)

    async def process_url(self, url, sender=None):
        """Main processing pipeline for URLs"""
        try:
            # Validate URL format
            if not re.match(r'^https?://', url):
                raise ValueError("Invalid URL format")

            # Rate limiting
            await self.enforce_rate_limit()

            # Robots.txt check
            if not self.ignore_robots and not await self.check_robots_txt(url):
                raise PermissionError("Robots.txt disallows this URL")

            # Fetch page content
            content = await self.fetch_url(url)

            # Parse content
            parsed = self.parse_content(content, url)

            # Generate summary
            summary = self.generate_summary(parsed)

            # Prepare and send notification
            response = f"Scraped: {url}\nTitle: {parsed['title']}\nSummary: {summary}"
            await self.send_message(response, sender or 'system')

        except Exception as e:
            error_msg = f"Error processing {url}: {str(e)}"
            await self.send_message(error_msg, sender or 'system')

    async def enforce_rate_limit(self):
        """Enforce rate limiting between requests"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit:
            await asyncio.sleep(self.rate_limit - elapsed)
        self.last_request_time = time.time()

    async def check_robots_txt(self, url):
        """Check robots.txt for scraping permission"""
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        
        try:
            rp = RobotFileParser()
            rp.set_url(robots_url)
            rp.read()
            return rp.can_fetch(self.user_agent, url)
        except Exception:
            return True  # Allow if robots.txt can't be fetched

    async def fetch_url(self, url):
        """Fetch URL content with retries and proxy support"""
        proxies = {'http': self.proxy, 'https': self.proxy} if self.proxy else None
        
        try:
            async with httpx.AsyncClient(proxies=proxies, timeout=self.timeout) as client:
                headers = {'User-Agent': self.user_agent}
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                return response.text
        except httpx.RequestError:
            # Fallback to requests if httpx fails
            response = requests.get(url, headers=headers, proxies=proxies, timeout=self.timeout)
            response.raise_for_status()
            return response.text

    def parse_content(self, html, url):
        """Parse HTML content with BeautifulSoup and readability"""
        doc = Document(html)
        soup = BeautifulSoup(doc.summary(), 'html.parser')
        
        # Extract main content
        text = soup.get_text(separator='\n', strip=True)
        text = re.sub(r'\n{3,}', '\n\n', text)[:self.max_text_length]
        
        # Extract metadata
        return {
            'title': doc.title(),
            'text': text,
            'url': url,
            'domain': urlparse(url).netloc,
            'images': [img['src'] for img in soup.find_all('img') if img.get('src')],
            'links': [a['href'] for a in soup.find_all('a') if a.get('href')]
        }

    def generate_summary(self, content, max_length=None):
        """Generate concise summary of parsed content"""
        max_len = max_length or self.summary_length
        sentences = re.split(r'(?<=\.)\s+', content['text'])
        summary = []
        length = 0
        
        for sentence in sentences:
            if length + len(sentence) > max_len:
                break
            summary.append(sentence)
            length += len(sentence)
            
        return ' '.join(summary)[:max_len]

    async def on_message_received(self, message, sender):
        """Override base message handler"""
        if message.startswith('!'):
            await super().on_message_received(message, sender)
        else:
            # Treat plain messages as potential URLs
            await self.process_url(message.strip(), sender)