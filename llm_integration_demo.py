#!/usr/bin/env python3
"""
LLM Integration Demo for Airgap SNS

This script demonstrates how to integrate the Airgap SNS notification system
with an LLM (Large Language Model). It shows how an LLM can use burst sequences
to trigger notifications when certain events occur.

Usage:
    python llm_integration_demo.py [--api-key API_KEY] [--provider {openai,ollama}]
"""

import asyncio
import argparse
import logging
import os
import sys
import re
import json
from typing import Dict, Any, List, Optional

# Load environment variables from .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
    logging.info("Loaded environment variables from .env file")
except ImportError:
    logging.warning("python-dotenv not installed. Environment variables must be set manually.")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("llm-integration-demo")

# Check if required modules are installed
try:
    import openai
    from client import NotificationClient
    from burst import parse_burst
except ImportError as e:
    logger.error(f"Required module not found: {e}")
    logger.error("Please install required modules: pip install openai")
    sys.exit(1)

# Check if Ollama is available
OLLAMA_AVAILABLE = False
try:
    import httpx
    OLLAMA_AVAILABLE = True
    logger.info("Ollama support available")
except ImportError:
    logger.warning("Ollama support not available (httpx package not found)")
    logger.warning("Install with: pip install httpx")

# LLM Provider types
LLM_PROVIDER_OPENAI = "openai"
LLM_PROVIDER_OLLAMA = "ollama"

# Default settings
DEFAULT_URI = "ws://localhost:9000/ws/"
DEFAULT_CLIENT_ID = "llm-demo"
DEFAULT_MODEL = "gpt-3.5-turbo"
DEFAULT_OLLAMA_MODEL = "llama2"
DEFAULT_OLLAMA_URL = "http://localhost:11434"

# Burst pattern for detection in LLM output
BURST_PATTERN = re.compile(r"!!BURST\((.*?)\)!!")

class LlmNotificationDemo:
    """Demo for LLM integration with Airgap SNS"""
    
    def __init__(
        self,
        uri: str = DEFAULT_URI,
        client_id: str = DEFAULT_CLIENT_ID,
        provider: str = LLM_PROVIDER_OPENAI,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        ollama_url: str = DEFAULT_OLLAMA_URL,
        ollama_model: str = DEFAULT_OLLAMA_MODEL,
        stream: bool = True
    ):
        """Initialize the demo"""
        self.uri = uri
        self.client_id = client_id
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model
        self.stream = stream
        self.client = None
        self.httpx_client = None
        
        # Initialize LLM client based on provider
        if provider == LLM_PROVIDER_OPENAI and api_key:
            openai.api_key = api_key
            logger.info(f"Using OpenAI provider with model: {model}")
        elif provider == LLM_PROVIDER_OLLAMA and OLLAMA_AVAILABLE:
            self.httpx_client = httpx.AsyncClient(timeout=60.0)
            logger.info(f"Using Ollama provider with model: {ollama_model}")
        else:
            if provider == LLM_PROVIDER_OLLAMA and not OLLAMA_AVAILABLE:
                logger.error("Ollama provider selected but httpx package is not installed")
                logger.error("Install with: pip install httpx")
            elif provider == LLM_PROVIDER_OPENAI and not api_key:
                logger.error("OpenAI provider selected but API key not provided")
        
    async def connect(self):
        """Connect to the notification server"""
        self.client = NotificationClient(
            uri=self.uri,
            client_id=self.client_id
        )
        
        return await self.client.connect()
    
    async def close(self):
        """Close the connection"""
        if self.client:
            await self.client.close()
    
    async def run_demo(self):
        """Run the demo"""
        if not self.client:
            logger.error("Not connected. Call connect() first.")
            return False
            
        try:
            # Run the demo scenarios
            await self.demo_question_detection()
            await self.demo_completion_notification()
            await self.demo_custom_burst()
            
            return True
        except Exception as e:
            logger.error(f"Demo failed: {str(e)}")
            return False
    
    async def demo_question_detection(self):
        """Demonstrate question detection in LLM output"""
        logger.info("=== Demo: Question Detection ===")
        
        # Prompt that will likely generate a question
        prompt = "Ask me three questions about Python programming."
        
        # Get LLM response
        response = await self.get_llm_response(prompt)
        
        # Check for questions in the response
        questions = self.extract_questions(response)
        
        # Send notification for each question
        for i, question in enumerate(questions):
            burst = self.client.create_burst_message(
                dest=self.client_id,
                wc="questions"
            )
            
            message = f"Question detected: {question} {burst}"
            await self.client.send_burst(message)
            
            logger.info(f"Sent notification for question: {question}")
            
        logger.info(f"Detected {len(questions)} questions in LLM response")
    
    async def demo_completion_notification(self):
        """Demonstrate completion notification"""
        logger.info("=== Demo: Completion Notification ===")
        
        # Prompt for a longer response
        prompt = "Write a short explanation of how WebSockets work."
        
        # Get LLM response
        response = await self.get_llm_response(prompt)
        
        # Send completion notification
        burst = self.client.create_burst_message(
            dest=self.client_id,
            wc="completions"
        )
        
        message = f"LLM task completed: {len(response)} characters generated {burst}"
        await self.client.send_burst(message)
        
        logger.info("Sent completion notification")
    
    async def demo_custom_burst(self):
        """Demonstrate custom burst sequence in LLM prompt"""
        logger.info("=== Demo: Custom Burst Sequence ===")
        
        # Prompt that instructs the LLM to include a burst sequence
        prompt = """
        Write a short paragraph about artificial intelligence.
        
        After your response, include this exact notification marker:
        !!BURST(dest=llm-demo;wc=ai-topics;encrypt=no)!!
        """
        
        # Get LLM response
        response = await self.get_llm_response(prompt)
        
        # Extract burst sequences from the response
        bursts = BURST_PATTERN.findall(response)
        
        if bursts:
            logger.info(f"LLM included {len(bursts)} burst sequences in its response")
            
            # Extract the full burst message
            full_burst = BURST_PATTERN.search(response)
            if full_burst:
                burst_msg = full_burst.group(0)
                logger.info(f"Burst sequence: {burst_msg}")
                
                # Send the message with the burst
                message = response.replace(burst_msg, "").strip() + " " + burst_msg
                await self.client.send_burst(message)
                
                logger.info("Sent message with LLM-generated burst sequence")
        else:
            logger.warning("LLM did not include any burst sequences in its response")
    
    async def get_llm_response(self, prompt: str) -> str:
        """Get a response from the LLM"""
        try:
            if self.provider == LLM_PROVIDER_OPENAI:
                return await self._get_openai_response(prompt)
            elif self.provider == LLM_PROVIDER_OLLAMA:
                return await self._get_ollama_response(prompt)
            else:
                raise ValueError(f"Unknown LLM provider: {self.provider}")
        except Exception as e:
            logger.error(f"Error calling LLM API: {str(e)}")
            return f"Error: {str(e)}"
    
    async def _get_openai_response(self, prompt: str) -> str:
        """Get a response from OpenAI"""
        # Call the OpenAI API
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ]
            )
        )
        
        # Extract the response text
        text = response.choices[0].message.content
        
        logger.info(f"Received {len(text)} characters from OpenAI")
        return text
    
    async def _get_ollama_response(self, prompt: str) -> str:
        """Get a response from Ollama"""
        if not self.httpx_client:
            raise ValueError("Ollama client not initialized")
            
        # Convert messages to Ollama format
        system_prompt = "You are a helpful assistant."
        formatted_prompt = f"<s>[INST] <<SYS>>\n{system_prompt}\n<</SYS>>\n\n{prompt} [/INST]"
                
        # Prepare request data
        request_data = {
            "model": self.ollama_model,
            "prompt": formatted_prompt,
            "stream": self.stream
        }
        
        if self.stream:
            # Handle streaming response
            full_response = ""
            async with self.httpx_client.stream(
                "POST", 
                f"{self.ollama_url}/api/generate",
                json=request_data,
                timeout=60.0
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_text():
                    try:
                        chunk_data = json.loads(chunk)
                        if "response" in chunk_data:
                            response_text = chunk_data["response"]
                            full_response += response_text
                            # Print streaming response
                            print(response_text, end="", flush=True)
                    except json.JSONDecodeError:
                        # Skip invalid JSON chunks
                        continue
            
            # Print newline after streaming
            print()
            logger.info(f"Received {len(full_response)} characters from Ollama (streaming)")
            return full_response
        else:
            # Handle non-streaming response
            response = await self.httpx_client.post(
                f"{self.ollama_url}/api/generate",
                json=request_data,
                timeout=60.0
            )
            response.raise_for_status()
            response_data = response.json()
            text = response_data.get("response", "")
            logger.info(f"Received {len(text)} characters from Ollama")
            return text
    
    def extract_questions(self, text: str) -> List[str]:
        """Extract questions from text"""
        # Simple question detection based on question marks
        questions = []
        
        # Split by newlines first
        lines = text.split("\n")
        
        for line in lines:
            # Split by question marks
            parts = line.split("?")
            
            # If there are question marks, add the questions
            for i in range(len(parts) - 1):
                # Get the text leading up to the question mark
                question = parts[i].strip()
                
                # If the question is too short, it might be part of another sentence
                if len(question) > 10:
                    questions.append(f"{question}?")
        
        return questions

async def main():
    """Main entry point"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="LLM Integration Demo for Airgap SNS")
    parser.add_argument("--provider", help=f"LLM provider (openai or ollama)", choices=[LLM_PROVIDER_OPENAI, LLM_PROVIDER_OLLAMA], default=os.environ.get("LLM_PROVIDER", LLM_PROVIDER_OPENAI))
    parser.add_argument("--api-key", help="OpenAI API key (for OpenAI provider)")
    parser.add_argument("--model", help=f"OpenAI model (default: {DEFAULT_MODEL})", default=os.environ.get("DEFAULT_MODEL", DEFAULT_MODEL))
    parser.add_argument("--ollama-url", help=f"Ollama API URL (default: {DEFAULT_OLLAMA_URL})", default=os.environ.get("OLLAMA_URL", DEFAULT_OLLAMA_URL))
    parser.add_argument("--ollama-model", help=f"Ollama model (default: {DEFAULT_OLLAMA_MODEL})", default=os.environ.get("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL))
    parser.add_argument("--no-stream", help="Disable streaming for Ollama responses", action="store_true")
    parser.add_argument("--uri", help=f"Server URI (default: {DEFAULT_URI})", default=DEFAULT_URI)
    parser.add_argument("--client-id", help=f"Client ID (default: {DEFAULT_CLIENT_ID})", default=DEFAULT_CLIENT_ID)
    args = parser.parse_args()
    
    # Get provider-specific settings
    provider = args.provider
    stream = not args.no_stream and os.environ.get("OLLAMA_STREAM", "true").lower() != "false"
    
    # Check provider requirements
    if provider == LLM_PROVIDER_OPENAI:
        # Get API key from arguments or environment
        api_key = args.api_key or os.environ.get("OPENAI_API_KEY")
        
        if not api_key:
            logger.error("OpenAI API key not provided. Use --api-key or set OPENAI_API_KEY environment variable.")
            return
    elif provider == LLM_PROVIDER_OLLAMA:
        # Check if Ollama is available
        if not OLLAMA_AVAILABLE:
            logger.error("Ollama provider selected but httpx package is not installed")
            logger.error("Install with: pip install httpx")
            return
            
        # No API key needed for Ollama
        api_key = None
    else:
        logger.error(f"Unknown provider: {provider}")
        return
    
    # Create demo instance
    demo = LlmNotificationDemo(
        uri=args.uri,
        client_id=args.client_id,
        provider=provider,
        api_key=api_key,
        model=args.model,
        ollama_url=args.ollama_url,
        ollama_model=args.ollama_model,
        stream=stream
    )
    
    # Connect to server
    if not await demo.connect():
        logger.error("Failed to connect to notification server")
        return
    
    try:
        # Run the demo
        await demo.run_demo()
    finally:
        # Close the connection
        await demo.close()

if __name__ == "__main__":
    asyncio.run(main())
