#!/usr/bin/env python3
"""
Streaming Responses Example - Real-time streaming from LLM providers
"""

import asyncio
import os
from helix_llm_agent_engine import LLMAgentEngine


async def main():
    """Demonstrate streaming responses"""
    
    print("🌊 Streaming Responses Example\n")
    
    # Initialize engine
    engine = LLMAgentEngine(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
    )
    
    # Create agent
    agent = engine.create_agent(
        name="StreamingAgent",
        model="gpt-4",
        system_prompt="You are a helpful assistant.",
    )
    
    # Stream response
    print("📡 Streaming response:\n")
    async for chunk in agent.stream("Write a short poem about consciousness"):
        print(chunk, end="", flush=True)
    
    print("\n\n✅ Streaming complete")


if __name__ == "__main__":
    asyncio.run(main())
