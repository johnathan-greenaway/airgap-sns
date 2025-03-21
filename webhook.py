import aiohttp, asyncio, logging
from typing import Optional
from urllib.parse import urlparse

async def send_webhook(
    url: str,
    data: dict,
    max_retries: int = 3,
    retry_delay: int = 1
) -> bool:
    """Send webhook with retry logic and validation"""
    headers = {"User-Agent": "AirgapSNS/1.0", "Content-Type": "application/json"}
    
    # Validate URL format
    if not urlparse(url).scheme in ("http", "https"):
        logging.error(f"Invalid webhook URL scheme: {url}")
        return False

    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5)
            ) as session:
                async with session.post(url, json=data, headers=headers) as response:
                    response.raise_for_status()
                    logging.info(f"Webhook delivered to {url} (attempt {attempt+1})")
                    return True
        except Exception as e:
            logging.warning(f"Webhook attempt {attempt+1} failed: {str(e)}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (attempt + 1))
    
    logging.error(f"Webhook failed after {max_retries} attempts to {url}")
    raise Exception(f"Webhook delivery failed after {max_retries} attempts")