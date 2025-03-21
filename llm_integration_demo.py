#!/usr/bin/env python3
"""
LLM Integration Demo for Airgap SNS

This script demonstrates how to integrate the Airgap SNS notification system
with an LLM (Large Language Model). It shows how an LLM can use burst sequences
to trigger notifications when certain events occur.

Usage:
    python llm_integration_demo.py [--api-key API_KEY]
"""

import asyncio
import argparse
import logging
import os
import sys
import re
from typing import Dict, Any, List, Optional

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

# Default settings
DEFAULT_URI = "ws://localhost:9000/ws/"
DEFAULT_CLIENT_ID = "llm-demo"
DEFAULT_MODEL = "gpt-3.5-turbo"

# Burst pattern for detection in LLM output
BURST_PATTERN = re.compile(r"!!BURST\((.*?)\)!!")

class LlmNotificationDemo:
    """Demo for LLM integration with Airgap SNS"""
    
    def __init__(
        self,
        api_key: str,
        uri: str = DEFAULT_URI,
        client_id: str = DEFAULT_CLIENT_ID,
        model: str = DEFAULT_MODEL
    ):
        """Initialize the demo"""
        self.api_key = api_key
        self.uri = uri
        self.client_id = client_id
        self.model = model
        self.client = None
        
        # Initialize OpenAI client
        openai.api_key = api_key
        
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
            # Call the OpenAI API
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Extract the response text
            text = response.choices[0].message.content
            
            logger.info(f"Received {len(text)} characters from LLM")
            return text
            
        except Exception as e:
            logger.error(f"Error calling LLM API: {str(e)}")
            return f"Error: {str(e)}"
    
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
    parser.add_argument("--api-key", help="OpenAI API key")
    parser.add_argument("--uri", help=f"Server URI (default: {DEFAULT_URI})", default=DEFAULT_URI)
    parser.add_argument("--client-id", help=f"Client ID (default: {DEFAULT_CLIENT_ID})", default=DEFAULT_CLIENT_ID)
    parser.add_argument("--model", help=f"OpenAI model (default: {DEFAULT_MODEL})", default=DEFAULT_MODEL)
    args = parser.parse_args()
    
    # Get API key from arguments or environment
    api_key = args.api_key or os.environ.get("OPENAI_API_KEY")
    
    if not api_key:
        logger.error("OpenAI API key not provided. Use --api-key or set OPENAI_API_KEY environment variable.")
        return
    
    # Create demo instance
    demo = LlmNotificationDemo(
        api_key=api_key,
        uri=args.uri,
        client_id=args.client_id,
        model=args.model
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
