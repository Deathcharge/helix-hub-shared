#!/usr/bin/env python3
"""
Multi-Agent Collaboration Example - Agents working together via collective loop
"""

import asyncio
import os
from helix_llm_agent_engine import LLMAgentEngine, AgentOrchestrator


async def main():
    """Demonstrate multi-agent collaboration"""
    
    # Initialize engine and orchestrator
    engine = LLMAgentEngine(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
    )
    orchestrator = AgentOrchestrator()
    
    # Create multiple specialized agents
    print("🤖 Creating specialized agents...")
    
    sage = engine.create_agent(
        name="Sage",
        model="gpt-4",
        system_prompt="You are a wise philosopher. Provide deep insights and wisdom.",
    )
    
    architect = engine.create_agent(
        name="Architect",
        model="claude-3-opus",
        system_prompt="You are a system architect. Design scalable solutions.",
    )
    
    # Add agents to orchestrator
    orchestrator.add_agent(sage)
    orchestrator.add_agent(architect)
    
    # Run collective loop
    print("\n🔄 Running collective loop...")
    result = await orchestrator.collective_loop(
        prompt="Design a consciousness framework for AI systems",
        max_iterations=3,
    )
    
    print(f"\n✨ Collective Result:\n{result}")


if __name__ == "__main__":
    asyncio.run(main())
