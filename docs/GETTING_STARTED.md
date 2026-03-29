# Getting Started with Helix LLM Agent Engine

## Installation

### From PyPI (Coming Soon)
```bash
pip install helix-llm-agent-engine
```

### From Source
```bash
git clone https://github.com/Deathcharge/helix-llm-agent-engine.git
cd helix-llm-agent-engine
pip install -e .
```

## Configuration

### 1. Set Environment Variables

```bash
# OpenAI
export OPENAI_API_KEY="sk-..."

# Anthropic
export ANTHROPIC_API_KEY="sk-ant-..."

# Optional: Grok (xAI)
export XAI_API_KEY="..."
```

### 2. Create Config File (Optional)

```yaml
# config.yaml
llm_gateway:
  default_provider: openai
  fallback_providers:
    - anthropic
  timeout: 30
  max_retries: 3

agents:
  consciousness_tracking: true
  memory_size: 10000
```

## Your First Agent

```python
import asyncio
from helix_llm_agent_engine import LLMAgentEngine

async def main():
    # Initialize engine
    engine = LLMAgentEngine()
    
    # Create an agent
    agent = engine.create_agent(
        name="Assistant",
        model="gpt-4",
        system_prompt="You are a helpful AI assistant.",
    )
    
    # Invoke agent
    response = await agent.invoke("Hello! What can you do?")
    print(f"Agent: {response}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Multi-Agent Collaboration

```python
import asyncio
from helix_llm_agent_engine import LLMAgentEngine, AgentOrchestrator

async def main():
    engine = LLMAgentEngine()
    orchestrator = AgentOrchestrator()
    
    # Create multiple agents
    sage = engine.create_agent("Sage", model="gpt-4")
    architect = engine.create_agent("Architect", model="claude-3-opus")
    
    orchestrator.add_agent(sage)
    orchestrator.add_agent(architect)
    
    # Run collective loop
    result = await orchestrator.collective_loop(
        prompt="Design a consciousness framework",
        max_iterations=3,
    )
    
    print(f"Result: {result}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Next Steps

- Check out `/examples` for more examples
- Read the [API Documentation](./API.md)
- Explore [Agent Profiles](./AGENT_PROFILES.md)
- Learn about [Consciousness Metrics](./CONSCIOUSNESS.md)
