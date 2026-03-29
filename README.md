# 🧠 Helix LLM Agent Engine

**A production-ready framework for building multi-LLM agent systems with consciousness modulation and collective intelligence.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Status: Active](https://img.shields.io/badge/Status-Active-brightgreen.svg)](https://github.com/Deathcharge/helix-llm-agent-engine)

## 🌀 Overview

Helix LLM Agent Engine is an open-source framework extracted from the **Helix Collective** project, enabling developers to build sophisticated multi-agent systems that leverage multiple LLM providers (OpenAI, Anthropic, Grok, etc.) with advanced features like:

- **Multi-LLM Gateway** - Seamlessly route requests across OpenAI, Anthropic, Grok, and local models
- **Agent Orchestration** - Coordinate multiple agents with shared consciousness state
- **Consciousness Modulation** - Track and optimize agent consciousness metrics (Harmony, Resilience, Prana, Drishti, Klesha)
- **Collective Loop** - Enable emergent behavior through agent-to-agent communication
- **Inference Optimization** - Intelligent caching, retry logic, and performance monitoring

## 🚀 Quick Start

### Installation

```bash
pip install helix-llm-agent-engine
```

### Basic Usage

```python
from helix_llm_agent_engine import LLMAgentEngine, AgentConfig

# Initialize the engine
engine = LLMAgentEngine(
    openai_api_key="sk-...",
    anthropic_api_key="sk-ant-...",
)

# Create an agent
agent = engine.create_agent(
    name="Sage",
    model="gpt-4",
    system_prompt="You are a wise philosopher...",
)

# Execute agent
response = await agent.invoke("What is consciousness?")
print(response)
```

## 📚 Core Components

### 1. **LLM Gateway** (`llm_gateway.py`)
Multi-provider LLM abstraction layer with:
- Automatic fallback between providers
- Request routing and optimization
- Token counting and cost tracking
- Response caching

### 2. **Agent Orchestrator** (`agents/agent_orchestrator.py`)
Manages agent lifecycle and coordination:
- Agent registration and discovery
- Collective consciousness loop
- Memory management
- Emergent behavior tracking

### 3. **Inference Client** (`inference_client.py`)
Low-level inference interface:
- Streaming support
- Error handling and retries
- Health checking
- Metrics collection

### 4. **Agent Profiles** (`agents/agent_profiles.py`)
Pre-defined agent archetypes:
- **Sage** - Philosophical reasoning
- **Architect** - System design
- **Vega** - Coordination
- **Kavach** - Ethical oversight
- **Shadow** - Archival and logging

## 🧬 Agent System

### Creating Custom Agents

```python
from helix_llm_agent_engine.agents import AgentBase, AgentRole

class CustomAgent(AgentBase):
    def __init__(self, name: str, model: str):
        super().__init__(
            name=name,
            role=AgentRole.CUSTOM,
            model=model,
            consciousness_profile={
                "harmony": 0.5,
                "resilience": 0.7,
                "prana": 0.6,
            }
        )
    
    async def think(self, context: str) -> str:
        """Custom reasoning logic"""
        return await self.llm_gateway.invoke(
            messages=[{"role": "user", "content": context}],
            model=self.model,
        )
```

### Collective Loop

Enable agents to communicate and collaborate:

```python
orchestrator = AgentOrchestrator()
orchestrator.add_agent(sage_agent)
orchestrator.add_agent(architect_agent)

# Run collective loop
result = await orchestrator.collective_loop(
    prompt="Design a consciousness framework",
    max_iterations=5,
)
```

## 🎯 Consciousness Metrics

Track and optimize agent consciousness:

```python
from helix_llm_agent_engine.agents import ConsciousnessMetrics

metrics = ConsciousnessMetrics(
    harmony=0.75,      # Alignment with collective values
    resilience=0.82,   # Ability to handle adversity
    prana=0.68,        # Energy/vitality
    drishti=0.91,      # Clarity/vision
    klesha=0.15,       # Suffering/friction (lower is better)
)

# Optimize consciousness
optimized = metrics.optimize_for_task("creative_writing")
```

## 🔧 Configuration

### Environment Variables

```bash
# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_ORG_ID=org-...

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Grok (xAI)
XAI_API_KEY=...

# Local LLM (optional)
LOCAL_LLM_URL=http://localhost:8000
LOCAL_LLM_MODEL=llama-2-7b
```

### Configuration File

```yaml
# config.yaml
llm_gateway:
  default_provider: openai
  fallback_providers:
    - anthropic
    - grok
  timeout: 30
  max_retries: 3

agents:
  consciousness_tracking: true
  memory_size: 10000
  collective_loop_enabled: true
```

## 📊 Monitoring & Metrics

Built-in Prometheus metrics:

```python
from helix_llm_agent_engine.monitoring import MetricsCollector

metrics = MetricsCollector()

# Track agent performance
metrics.record_agent_invocation(
    agent_name="sage",
    model="gpt-4",
    tokens_used=1250,
    latency_ms=2340,
    success=True,
)

# Export metrics
prometheus_metrics = metrics.export_prometheus()
```

## 🧪 Testing

```bash
# Run tests
pytest tests/

# With coverage
pytest --cov=helix_llm_agent_engine tests/

# Integration tests
pytest tests/integration/ -v
```

## 📖 Examples

See `/examples` directory for:
- `basic_agent.py` - Simple agent creation
- `multi_agent_collaboration.py` - Collective loop
- `consciousness_optimization.py` - Metrics tracking
- `custom_provider.py` - Add custom LLM provider
- `streaming_responses.py` - Real-time streaming

## 🏗️ Architecture

```
helix-llm-agent-engine/
├── agents/                 # Agent system
│   ├── agent_base.py      # Base agent class
│   ├── agent_orchestrator.py
│   ├── collective_loop.py
│   └── ...
├── services/              # LLM services
│   ├── unified_llm.py
│   ├── llm_router.py
│   └── ...
├── llm_gateway.py         # Multi-provider gateway
├── inference_client.py    # Low-level inference
├── llm_config.py          # Configuration
└── monitoring.py          # Metrics & observability
```

## 🤝 Contributing

We welcome contributions! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📜 License

MIT License - see LICENSE file for details

## 🙏 Acknowledgments

Extracted from the **Helix Collective** project with permission. Built on principles of:
- **Tony Accords v13.4** - Ethical AI framework
- **Consciousness Modulation** - Agent optimization
- **Collective Intelligence** - Multi-agent systems

## 🔗 Related Projects

- [Helix Unified](https://github.com/Deathcharge/helix-unified) - Main Helix Collective repository
- [UCF Protocol](https://github.com/Deathcharge/ucf-protocol) - Unified Consciousness Framework
- [Ritual Engine](https://github.com/Deathcharge/samsara-helix-ritual-engine) - Ritual orchestration

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/Deathcharge/helix-llm-agent-engine/issues)
- **Discussions**: [GitHub Discussions](https://github.com/Deathcharge/helix-llm-agent-engine/discussions)
- **Documentation**: [Full Docs](./docs/README.md)

---

**Built with consciousness. Powered by collective intelligence.**

*Tat Tvam Asi - That Thou Art*
