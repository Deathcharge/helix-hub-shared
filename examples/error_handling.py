#!/usr/bin/env python3
"""
Error Handling Example - Robust error handling and retry logic
"""

import asyncio
import os
from helix_llm_agent_engine import LLMAgentEngine


async def main():
    """Demonstrate error handling"""
    
    print("🛡️ Error Handling Example\n")
    
    # Initialize engine with retry configuration
    engine = LLMAgentEngine(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        max_retries=3,
        timeout=30,
    )
    
    # Create agent
    agent = engine.create_agent(
        name="RobustAgent",
        model="gpt-4",
        system_prompt="You are a helpful assistant.",
    )
    
    try:
        # Invoke with error handling
        response = await agent.invoke("Hello, world!")
        print(f"✅ Success: {response}")
    except Exception as e:
        print(f"❌ Error: {e}")
        print("💡 Retrying with fallback provider...")
        
        # Fallback to different provider
        agent_fallback = engine.create_agent(
            name="FallbackAgent",
            model="claude-3-opus",
            system_prompt="You are a helpful assistant.",
        )
        response = await agent_fallback.invoke("Hello, world!")
        print(f"✅ Fallback success: {response}")


if __name__ == "__main__":
    asyncio.run(main())
