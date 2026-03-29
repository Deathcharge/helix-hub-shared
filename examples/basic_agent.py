#!/usr/bin/env python3
"""
Basic Agent Example - Simple agent creation and invocation
"""

import asyncio
import os
from helix_llm_agent_engine import LLMAgentEngine


async def main():
    """Create and invoke a basic agent"""
    
    # Initialize the LLM Agent Engine
    engine = LLMAgentEngine(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
    )
    
    # Create an agent
    agent = engine.create_agent(
        name="Philosopher",
        model="gpt-4",
        system_prompt="You are a wise philosopher who provides thoughtful insights.",
    )
    
    # Invoke the agent with a prompt
    print("🤔 Invoking Philosopher agent...")
    response = await agent.invoke(
        "What is the nature of consciousness?"
    )
    
    print(f"\n📝 Response:\n{response}\n")
    
    # Check agent metrics
    metrics = agent.get_metrics()
    print(f"📊 Agent Metrics:")
    print(f"  - Tokens Used: {metrics.get('tokens_used', 'N/A')}")
    print(f"  - Latency: {metrics.get('latency_ms', 'N/A')}ms")
    print(f"  - Success: {metrics.get('success', 'N/A')}")


if __name__ == "__main__":
    asyncio.run(main())
