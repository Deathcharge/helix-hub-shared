#!/usr/bin/env python3
"""
Custom LLM Provider Example - Integrate a custom LLM provider
"""

import asyncio
from helix_llm_agent_engine import LLMAgentEngine
from helix_llm_agent_engine.services import BaseLLMProvider


class CustomLLMProvider(BaseLLMProvider):
    """Example custom LLM provider"""
    
    async def invoke(self, messages, model, **kwargs):
        """Custom inference logic"""
        # Implement your custom LLM logic here
        return "Response from custom provider"


async def main():
    """Demonstrate custom LLM provider integration"""
    
    print("🔧 Custom LLM Provider Example\n")
    
    # Initialize engine
    engine = LLMAgentEngine()
    
    # Register custom provider
    custom_provider = CustomLLMProvider()
    engine.register_provider("custom", custom_provider)
    
    # Create agent using custom provider
    agent = engine.create_agent(
        name="CustomAgent",
        model="custom",
        system_prompt="You are powered by a custom LLM provider.",
    )
    
    print("✅ Custom provider registered and agent created")


if __name__ == "__main__":
    asyncio.run(main())
