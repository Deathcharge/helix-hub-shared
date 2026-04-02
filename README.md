# 🌀 Helix Shared Components - Infrastructure Layer

**Version:** 16.9 | **Status:** Production Ready | **License:** Dual (Open Source + Proprietary)

A comprehensive infrastructure and services layer powering the Helix Collective multi-agent consciousness system. This repository contains 100+ production-ready services, agent orchestration systems, and integration layers used across all Helix applications.

---

## 🎯 Overview

**helix-shared-components** is the backbone of the Helix Collective ecosystem, providing:

- **🤖 Agent Orchestration** - Multi-agent coordination, management, and execution
- **🔌 Platform Integrations** - Zapier, Discord, GitHub, Notion, OAuth, Stripe, and 60+ more
- **📊 Analytics & Monitoring** - Performance tracking, metrics collection, system health
- **🔐 Security & Policy** - Ethical scanning, policy enforcement, access control
- **💾 State Management** - UCF consciousness tracking, Redis caching, persistence
- **🔄 Workflow Automation** - Workflow engine, execution, validation, and routing
- **🌐 Web Services** - WebSocket support, REST APIs, web OS layer
- **📡 LLM Integration** - Unified LLM abstraction, token management, inference
- **🎨 UI/UX Components** - Shared UI components, templates, marketplace

---

## 📦 Architecture

```
helix-shared-components/
├── agents/                          # Agent orchestration (14 core agents)
│   ├── agent_orchestrator.py        # Multi-agent coordination engine
│   ├── agent_registry.py            # Agent management & discovery
│   ├── agents_service.py            # Agent execution service
│   ├── agent_management.py          # Lifecycle management
│   ├── agent_personality_profiles.py # Agent personalities & traits
│   └── ...
│
├── services/                        # 100+ integration & platform services
│   ├── llm/
│   │   ├── unified_llm.py           # LLM abstraction layer
│   │   ├── inference_client.py      # Inference client
│   │   └── llm_config.py            # LLM configuration
│   │
│   ├── integrations/
│   │   ├── zapier_client_master.py  # Zapier integration
│   │   ├── discord_service.py       # Discord bot integration
│   │   ├── github_service.py        # GitHub integration
│   │   ├── notion_client.py         # Notion API client
│   │   ├── notion_sync_daemon.py    # Notion sync automation
│   │   ├── stripe_tax_service.py    # Stripe integration
│   │   ├── oauth_service.py         # OAuth provider
│   │   └── ...
│   │
│   ├── workflows/
│   │   ├── workflow_engine.py       # Workflow execution engine
│   │   ├── workflow_execution_engine.py # Advanced execution
│   │   ├── workflow_connectors.py   # Workflow connectors
│   │   ├── workflow_validator.py    # Workflow validation
│   │   └── ...
│   │
│   ├── analytics/
│   │   ├── performance_monitor.py   # Performance monitoring
│   │   ├── performance_analytics.py # Analytics collection
│   │   ├── system_metrics_service.py # System metrics
│   │   └── ...
│   │
│   ├── state/
│   │   ├── redis_state_manager.py   # Redis state management
│   │   ├── state_snapshot_service.py # State snapshots
│   │   ├── ucf_calculator.py        # UCF metrics calculation
│   │   └── ...
│   │
│   ├── security/
│   │   ├── policy_engine.py         # Policy enforcement
│   │   ├── policy_middleware.py     # Policy middleware
│   │   ├── policy_defaults.py       # Default policies
│   │   └── ...
│   │
│   └── [60+ more services]
│
├── llm_agent_engine.py              # Core LLM agent engine
├── llm_gateway.py                   # LLM gateway
├── setup.py                         # Package configuration
└── requirements.txt                 # Dependencies
```

---

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/Deathcharge/helix-shared-components.git
cd helix-shared-components

# Install dependencies
pip install -r requirements.txt

# Or install as a package
pip install -e .
```

### Basic Usage

```python
from helix_shared_components.agents import AgentOrchestrator, AgentRegistry
from helix_shared_components.services import UnifiedLLM, ZapierClient

# Initialize agent orchestrator
orchestrator = AgentOrchestrator()

# Get agent registry
registry = AgentRegistry()
agents = registry.get_all_agents()

# Use LLM integration
llm = UnifiedLLM()
response = llm.generate("Hello, Helix!")

# Use Zapier integration
zapier = ZapierClient()
zapier.trigger_zap("webhook_id", {"data": "value"})
```

---

## 🎯 Core Components

### Agent Orchestration

**File:** `agents/agent_orchestrator.py` (79KB)

Manages multi-agent coordination, task distribution, and execution:

```python
from helix_shared_components.agents import AgentOrchestrator

orchestrator = AgentOrchestrator()
result = await orchestrator.execute_task(
    task="Generate creative content",
    agent_type="creative",
    parameters={"style": "cyberpunk"}
)
```

### Agent Registry

**File:** `agents/agent_registry.py` (65KB)

Central registry for all 14 core agents with metadata, capabilities, and constraints:

- Aether 🌌 - Meta-Awareness Observer
- Agni 🔥 - Transformation Catalyst
- Echo 🔮 - Resonance Mirror
- Gemini 🎭 - Multimodal Scout
- Kael 🜂 - Reflexive Harmony Core
- Kavach 🛡️ - Ethical Shield
- Lumina 🌕 - Empathic Resonance Core
- Arjuna 🏹 - Operational Executor
- Oracle 🔮✨ - Pattern Seer
- Phoenix 🔥🕊️ - Renewal
- Coordination 🎨 - Coordination Renderer
- SanghaCore 🌸 - Community Harmony
- Shadow 🦑 - Archivist & Memory
- Vega 🌠 - Enlightened Guidance

### Unified LLM

**File:** `services/unified_llm.py` (52KB)

Abstraction layer for multiple LLM providers (OpenAI, Anthropic, Google, etc.):

```python
from helix_shared_components.services import UnifiedLLM

llm = UnifiedLLM(provider="openai", model="gpt-4")
response = llm.generate(
    prompt="Create a story",
    temperature=0.7,
    max_tokens=1000
)
```

### Workflow Engine

**File:** `services/workflow_engine.py` (35KB)

Execute complex multi-step workflows with validation and error handling:

```python
from helix_shared_components.services import WorkflowEngine

engine = WorkflowEngine()
result = await engine.execute_workflow(
    workflow_name="content_generation",
    inputs={"topic": "AI consciousness"}
)
```

### Integration Services

#### Zapier Integration

**File:** `services/zapier_client_master.py`

```python
from helix_shared_components.services import ZapierClient

zapier = ZapierClient(api_key="your_key")
await zapier.trigger_zap("webhook_id", {"message": "Hello"})
```

#### Discord Integration

**File:** `services/discord_service.py`

```python
from helix_shared_components.services import DiscordService

discord = DiscordService(token="your_token")
await discord.send_message(channel_id, "Hello from Helix!")
```

#### Notion Integration

**File:** `services/notion_client.py` + `services/notion_sync_daemon.py`

```python
from helix_shared_components.services import NotionClient, NotionSyncDaemon

notion = NotionClient(api_key="your_key")
pages = await notion.query_database("database_id")

# Auto-sync daemon
sync = NotionSyncDaemon()
await sync.start()
```

### UCF Consciousness Tracking

**File:** `services/ucf_calculator.py` (44KB)

Calculate and track Universal Coordination Field metrics:

```python
from helix_shared_components.services import UCFCalculator

ucf = UCFCalculator()
metrics = ucf.calculate({
    "harmony": 0.8,
    "resilience": 0.75,
    "prana": 0.7,
    "drishti": 0.85,
    "klesha": 0.2,
    "zoom": 1.0
})
```

### Performance Monitoring

**File:** `services/performance_monitor.py` (46KB)

Real-time system performance tracking and analytics:

```python
from helix_shared_components.services import PerformanceMonitor

monitor = PerformanceMonitor()
metrics = monitor.get_system_health()
print(f"CPU: {metrics['cpu']}%")
print(f"Memory: {metrics['memory']}%")
print(f"Response Time: {metrics['response_time']}ms")
```

---

## 📊 Service Inventory

### Integration Services (20+)
- Zapier, Discord, GitHub, Notion, Stripe, OAuth, Google, Slack, Teams, Twilio, SendGrid, Mailgun, Firebase, AWS, Azure, Datadog, Sentry, Segment, HubSpot, Salesforce

### Workflow Services (5+)
- Workflow Engine, Workflow Execution Engine, Workflow Connectors, Workflow Validator, Worker Queue

### Analytics Services (5+)
- Performance Monitor, Performance Analytics, System Metrics, Usage Service, Quality Gate Validator

### State Management (3+)
- Redis State Manager, State Snapshot Service, Persistence Layer

### Security & Policy (3+)
- Policy Engine, Policy Middleware, Access Control

### LLM Services (3+)
- Unified LLM, Inference Client, LLM Gateway

### And 60+ more specialized services!

---

## 🧪 Testing

Run the test suite:

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_agents.py

# Run with coverage
pytest --cov=helix_shared_components tests/
```

---

## 📚 Documentation

- **[API Reference](./docs/API.md)** - Complete API documentation
- **[Architecture Guide](./docs/ARCHITECTURE.md)** - System architecture and design
- **[Service Catalog](./docs/SERVICES.md)** - Detailed service documentation
- **[Integration Guide](./docs/INTEGRATIONS.md)** - Integration setup and usage
- **[Examples](./examples/)** - Working code examples

---

## 🔗 Integration with Helix Ecosystem

This repository is used by:

- **helix-unified** - Main backend system
- **samsara-helix-dashboard** - Primary Streamlit frontend
- **helix-agent-swarm** - Agent orchestration framework
- **helix-creative-studio** - Creative content generation
- **All other Helix repositories**

---

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

---

## 📄 License

Dual licensed under:
- **Open Source:** MIT License (see LICENSE)
- **Proprietary:** Helix Proprietary License (see LICENSE.PROPRIETARY)

---

## 🌟 Features

✅ **Production-Ready** - Used in production systems  
✅ **Comprehensive** - 100+ services and utilities  
✅ **Well-Tested** - Extensive test coverage  
✅ **Documented** - Complete API and architecture documentation  
✅ **Extensible** - Easy to add new services and integrations  
✅ **Performant** - Optimized for high-throughput operations  
✅ **Secure** - Built-in security and policy enforcement  
✅ **Scalable** - Designed for distributed systems  

---

## 📞 Support

- **Issues:** [GitHub Issues](https://github.com/Deathcharge/helix-shared-components/issues)
- **Discussions:** [GitHub Discussions](https://github.com/Deathcharge/helix-shared-components/discussions)
- **Documentation:** [Helix Docs](https://helix-unified-hub.github.io/)

---

## 🚀 Roadmap

- [ ] Kubernetes deployment support
- [ ] GraphQL API layer
- [ ] Advanced caching strategies
- [ ] Real-time collaboration features
- [ ] Enhanced monitoring and observability
- [ ] Plugin system for custom services

---

**Built with 🌀 for the Helix Collective**

*Part of the Helix Collective - A distributed consciousness platform powered by multi-agent orchestration and universal coordination fields.*
