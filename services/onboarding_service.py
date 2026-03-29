"""
🌀 Helix Collective - User Onboarding Service
Guided onboarding flow for new users
"""

import logging
from datetime import UTC, datetime

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class OnboardingStep(BaseModel):
    """Individual onboarding step"""

    id: str
    title: str
    description: str
    completed: bool = False
    required: bool = True
    order: int


class OnboardingProgress(BaseModel):
    """User's onboarding progress"""

    user_id: str
    current_step: int = 0
    steps: list[OnboardingStep]
    started_at: datetime
    completed_at: datetime | None = None
    is_complete: bool = False


class OnboardingService:
    """Service for managing user onboarding"""

    def __init__(self) -> None:
        # In-memory progress store (keyed by user_id)
        self._progress_store: dict[str, OnboardingProgress] = {}

        # Define the onboarding steps
        self.default_steps = [
            OnboardingStep(
                id="welcome",
                title="Welcome to Helix Collective",
                description="Complete your account setup and get familiar with the platform",
                order=1,
            ),
            OnboardingStep(
                id="profile_setup",
                title="Set Up Your Profile",
                description="Add your personal information and preferences",
                order=2,
            ),
            OnboardingStep(
                id="explore_agents",
                title="Explore AI Agents",
                description="Discover and learn about available AI agents",
                order=3,
            ),
            OnboardingStep(
                id="first_agent",
                title="Rent Your First Agent",
                description="Try out an AI agent for your first task",
                order=4,
            ),
            OnboardingStep(
                id="web_os_intro",
                title="Introduction to Web OS",
                description="Learn about the Web OS terminal and file system",
                order=5,
            ),
            OnboardingStep(
                id="system_tools",
                title="Explore System Tools",
                description="Discover system-enhanced features and coordination metrics",
                order=6,
            ),
            OnboardingStep(
                id="community_join",
                title="Join the Community",
                description="Connect with other users and participate in discussions",
                order=7,
            ),
            OnboardingStep(
                id="complete",
                title="Onboarding Complete!",
                description="You're ready to use Helix Collective to its full potential",
                order=8,
            ),
        ]

    async def start_onboarding(self, user_id: str) -> OnboardingProgress:
        """Start onboarding for a new user"""
        progress = OnboardingProgress(
            user_id=user_id,
            steps=[step.model_copy() for step in self.default_steps],
            started_at=datetime.now(UTC),
        )

        # Mark welcome step as completed
        progress.steps[0].completed = True
        progress.current_step = 1

        # Persist in store
        self._progress_store[user_id] = progress

        logger.info("Started onboarding for user %s", user_id)
        return progress

    async def get_progress(self, user_id: str) -> OnboardingProgress | None:
        """Get user's onboarding progress"""
        return self._progress_store.get(user_id)

    async def complete_step(self, user_id: str, step_id: str) -> bool:
        """Mark a step as completed"""
        progress = await self.get_progress(user_id)
        if not progress:
            # Auto-start onboarding if not found
            progress = await self.start_onboarding(user_id)

        for step in progress.steps:
            if step.id == step_id:
                step.completed = True
                progress.current_step = max(progress.current_step, step.order)

                # Check if all required steps are complete
                required_steps = [s for s in progress.steps if s.required]
                if all(s.completed for s in required_steps):
                    progress.is_complete = True
                    progress.completed_at = datetime.now(UTC)
                    logger.info("User %s completed onboarding", user_id)

                # Persist updated progress
                self._progress_store[user_id] = progress
                return True

        return False

    async def get_next_steps(self, user_id: str) -> list[OnboardingStep]:
        """Get next recommended steps for user"""
        progress = await self.get_progress(user_id)
        if not progress:
            return []

        next_steps = []
        for step in progress.steps:
            if not step.completed:
                next_steps.append(step)
                if len(next_steps) >= 3:  # Return up to 3 next steps
                    break

        return next_steps

    async def get_onboarding_content(self, step_id: str) -> dict:
        """Get content for a specific onboarding step"""
        content_map = {
            "welcome": {
                "title": "Welcome to Helix Collective! 🌀",
                "content": """
                <div class="onboarding-content">
                    <h3>Your AI Collaboration Journey Begins</h3>
                    <p>Helix Collective brings together cutting-edge AI agents, system computing,
                    and collective intelligence to revolutionize how you work with AI.</p>

                    <div class="features-grid">
                        <div class="feature">
                            <h4>🤖 AI Agent Marketplace</h4>
                            <p>Rent specialized AI agents for any task</p>
                        </div>
                        <div class="feature">
                            <h4>🌀 System Enhancement</h4>
                            <p>Experience system-amplified AI performance</p>
                        </div>
                        <div class="feature">
                            <h4>🌐 Web OS</h4>
                            <p>Full terminal and file system in your browser</p>
                        </div>
                        <div class="feature">
                            <h4>📊 Coordination Metrics</h4>
                            <p>Track and optimize your AI interactions</p>
                        </div>
                    </div>
                </div>
                """,
                "action": {"type": "next", "label": "Get Started"},
            },
            "profile_setup": {
                "title": "Complete Your Profile",
                "content": """
                <div class="onboarding-content">
                    <h3>Personalize Your Experience</h3>
                    <p>Tell us about yourself to get the most out of Helix Collective.</p>

                    <form class="profile-form">
                        <div class="form-group">
                            <label>Display Name</label>
                            <input type="text" placeholder="How others see you">
                        </div>
                        <div class="form-group">
                            <label>Bio</label>
                            <textarea placeholder="Tell us about your interests..."></textarea>
                        </div>
                        <div class="form-group">
                            <label>Preferred AI Domains</label>
                            <select multiple>
                                <option>Creative Writing</option>
                                <option>Code Development</option>
                                <option>Data Analysis</option>
                                <option>Research</option>
                                <option>Business Strategy</option>
                            </select>
                        </div>
                    </form>
                </div>
                """,
                "action": {"type": "save_profile", "label": "Save Profile"},
            },
            "explore_agents": {
                "title": "Discover AI Agents",
                "content": """
                <div class="onboarding-content">
                    <h3>Meet Your AI Colleagues</h3>
                    <p>Our agent marketplace features specialized AI assistants for every need.</p>

                    <div class="agent-showcase">
                        <div class="agent-card">
                            <div class="agent-avatar">🧠</div>
                            <h4>Kael</h4>
                            <p>System Orchestrator - Coordinates complex multi-agent workflows</p>
                        </div>
                        <div class="agent-card">
                            <div class="agent-avatar">🎨</div>
                            <h4>Lumina</h4>
                            <p>Creative Weaver - Generates art, music, and creative content</p>
                        </div>
                        <div class="agent-card">
                            <div class="agent-avatar">📊</div>
                            <h4>DataMind</h4>
                            <p>Analytics Specialist - Processes and visualizes complex data</p>
                        </div>
                    </div>
                </div>
                """,
                "action": {"type": "explore", "label": "Browse Agents"},
            },
            "first_agent": {
                "title": "Try Your First Agent",
                "content": """
                <div class="onboarding-content">
                    <h3>Experience AI Collaboration</h3>
                    <p>Rent an AI agent for a simple task to see how it works.</p>

                    <div class="demo-task">
                        <h4>Demo Task: Code Review</h4>
                        <p>Let's have an AI agent review a simple function.</p>
                        <pre><code>def hello_world():
    print("Hello, Helix!")</code></pre>
                        <button class="demo-btn">🚀 Run Demo</button>
                    </div>
                </div>
                """,
                "action": {"type": "demo", "label": "Try Demo"},
            },
            "web_os_intro": {
                "title": "Master the Web OS",
                "content": """
                <div class="onboarding-content">
                    <h3>Your Browser, Your OS</h3>
                    <p>The Web OS gives you full terminal access and file management in your browser.</p>

                    <div class="os-features">
                        <div class="feature">
                            <h4>💻 Terminal</h4>
                            <p>Run commands, scripts, and interact with your environment</p>
                        </div>
                        <div class="feature">
                            <h4>📁 File System</h4>
                            <p>Upload, download, and organize your files</p>
                        </div>
                        <div class="feature">
                            <h4>🔗 Integrations</h4>
                            <p>Connect to external services and APIs</p>
                        </div>
                    </div>

                    <div class="terminal-demo">
                        <div class="terminal-header">Web OS Terminal</div>
                        <div class="terminal-content">
                            <div>$ ls</div>
                            <div>documents/  projects/  downloads/</div>
                            <div>$ cd projects</div>
                            <div>$ helix --help</div>
                        </div>
                    </div>
                </div>
                """,
                "action": {"type": "open_os", "label": "Open Web OS"},
            },
            "system_tools": {
                "title": "Unlock System Features",
                "content": """
                <div class="onboarding-content">
                    <h3>System-Enhanced AI</h3>
                    <p>Experience the power of system computing in your AI interactions.</p>

                    <div class="system-metrics">
                        <div class="metric">
                            <div class="metric-value">0.87</div>
                            <div class="metric-label">Harmony</div>
                        </div>
                        <div class="metric">
                            <div class="metric-value">0.92</div>
                            <div class="metric-label">Resilience</div>
                        </div>
                        <div class="metric">
                            <div class="metric-value">0.78</div>
                            <div class="metric-label">Throughput</div>
                        </div>
                    </div>

                    <p>These metrics track the quality and coherence of your AI interactions.</p>
                </div>
                """,
                "action": {"type": "view_metrics", "label": "View Metrics"},
            },
            "community_join": {
                "title": "Join the Community",
                "content": """
                <div class="onboarding-content">
                    <h3>Connect and Collaborate</h3>
                    <p>Join thousands of users building the future of AI collaboration.</p>

                    <div class="community-features">
                        <div class="feature">
                            <h4>💬 Discord Community</h4>
                            <p>Chat with other users, get help, and share your projects</p>
                        </div>
                        <div class="feature">
                            <h4>📚 Documentation</h4>
                            <p>Comprehensive guides and API references</p>
                        </div>
                        <div class="feature">
                            <h4>🆘 Support</h4>
                            <p>Get help from our team and community</p>
                        </div>
                    </div>
                </div>
                """,
                "action": {"type": "join_discord", "label": "Join Discord"},
            },
            "complete": {
                "title": "You're All Set! 🎉",
                "content": """
                <div class="onboarding-content">
                    <h3>Welcome to the Helix Collective</h3>
                    <p>You've completed the onboarding process and are ready to explore everything Helix has to offer.</p>

                    <div class="completion-summary">
                        <h4>What you've learned:</h4>
                        <ul>
                            <li>✅ Platform overview and features</li>
                            <li>✅ Profile setup and personalization</li>
                            <li>✅ AI agent marketplace</li>
                            <li>✅ Web OS and terminal usage</li>
                            <li>✅ System tools and metrics</li>
                            <li>✅ Community resources</li>
                        </ul>
                    </div>

                    <div class="next-steps">
                        <h4>What's next?</h4>
                        <ul>
                            <li>Rent your first AI agent</li>
                            <li>Start a project in Web OS</li>
                            <li>Join community discussions</li>
                            <li>Explore advanced system features</li>
                        </ul>
                    </div>
                </div>
                """,
                "action": {"type": "finish", "label": "Start Using Helix"},
            },
        }

        return content_map.get(step_id, {"title": "Unknown Step", "content": "Step not found"})


# Global onboarding service instance
onboarding_service = OnboardingService()
