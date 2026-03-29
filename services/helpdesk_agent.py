"""
Help Desk Agent Service
======================

A specialized agent for community support on Discord and Forums.
Uses SanghaCore's community harmony expertise to provide customer support.

Features:
- Auto-respond to common questions
- Create support tickets
- Escalate to human mods
- Knowledge base lookup
- Sentiment analysis

This can be deployed to helix-discord-bot as a new command module.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class TicketPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TicketStatus(str, Enum):
    OPEN = "open"
    PENDING = "pending"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


@dataclass
class HelpDeskTicket:
    """Support ticket structure."""

    ticket_id: str
    user_id: str
    platform: str  # discord, forum
    channel_id: str
    subject: str
    description: str
    priority: TicketPriority
    status: TicketStatus
    created_at: datetime
    messages: list[dict[str, Any]]
    assigned_agent: str | None = None


@dataclass
class FAQEntry:
    """Frequently Asked Question entry."""

    question: str
    answer: str
    keywords: list[str]
    category: str


# ---------------------------------------------------------------------------
# Knowledge base loading (config/helpdesk_kb.json → FAQEntry list)
# ---------------------------------------------------------------------------

# Resolve the config JSON relative to the repository root
_KB_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "config", "helpdesk_kb.json"
)

# Fallback hardcoded entries in case the config file is missing
_FALLBACK_FAQ: list[FAQEntry] = [
    FAQEntry(
        question="How do I get started?",
        answer="Welcome to Helix! Sign up at helixspiral.work, choose a plan, "
        "connect your first integration, and explore the agents.",
        keywords=["start", "begin", "new", "setup", "getting started"],
        category="getting-started",
    ),
]


def _load_knowledge_base(path: str = _KB_CONFIG_PATH) -> list[FAQEntry]:
    """Load FAQ knowledge base from a JSON config file.

    Falls back to a minimal hardcoded list if the file cannot be read.
    """
    resolved = os.path.normpath(path)
    # Also allow override via env var
    env_path = os.environ.get("HELPDESK_KB_PATH")
    if env_path and os.path.isfile(env_path):
        resolved = env_path

    try:
        with open(resolved, encoding="utf-8") as fh:
            data = json.load(fh)
        entries = data.get("entries", [])
        result = [
            FAQEntry(
                question=e["question"],
                answer=e["answer"],
                keywords=e.get("keywords", []),
                category=e.get("category", "general"),
            )
            for e in entries
        ]
        logger.info("Loaded %d FAQ entries from %s", len(result), resolved)
        return result
    except FileNotFoundError:
        logger.warning("Helpdesk KB file not found at %s — using fallback", resolved)
    except (json.JSONDecodeError, KeyError) as exc:
        logger.error("Failed to parse helpdesk KB %s: %s", resolved, exc)

    return list(_FALLBACK_FAQ)


FAQ_KNOWLEDGE_BASE = _load_knowledge_base()


class HelpDeskAgent:
    """
    Help Desk Agent for Discord and Forums.

    Provides automated support using the knowledge base,
    creates tickets for complex issues, and escalates when needed.
    """

    def __init__(self):
        self.faq_db = FAQ_KNOWLEDGE_BASE
        self.active_tickets: dict[str, HelpDeskTicket] = {}
        self.ticket_counter = 0

    async def handle_message(
        self,
        user_id: str,
        message: str,
        platform: str = "discord",
        channel_id: str = "",
    ) -> dict[str, Any]:
        """
        Handle a support message from a user.

        Returns:
            Dict with response and any ticket created
        """
        message_lower = message.lower()

        # Check for commands
        if message_lower.startswith("!ticket") or message_lower.startswith("!support"):
            return await self._create_ticket(user_id, message, platform, channel_id)

        if message_lower in ["!faq", "!help", "!knowledge"]:
            return self._show_faq()

        # Search knowledge base
        faq_match = self._search_knowledge_base(message_lower)
        if faq_match:
            return {"type": "faq", "response": faq_match.answer, "category": faq_match.category, "confidence": 0.9}

        # No match - create ticket or give general help
        if self._needs_human_help(message_lower):
            return await self._create_ticket(
                user_id, f"Auto-created: {message}", platform, channel_id, priority=TicketPriority.MEDIUM
            )

        # Default: suggest FAQ or ticket
        return {
            "type": "suggestion",
            "response": (
                "I couldn't find a specific answer to your question. "
                "Try:\n"
                "• !faq - Browse common questions\n"
                "• !ticket - Create a support ticket\n"
                "• Describe your issue in detail and I'll create a ticket for you"
            ),
            "suggested_actions": ["faq", "ticket"],
        }

    def _search_knowledge_base(self, query: str) -> FAQEntry | None:
        """Search the knowledge base for matching FAQ."""
        best_match = None
        best_score = 0

        for faq in self.faq_db:
            # Check keywords
            for keyword in faq.keywords:
                if keyword in query:
                    score = len(keyword)  # Longer matches = higher score
                    if score > best_score:
                        best_score = score
                        best_match = faq

        return best_match

    def _show_faq(self) -> dict[str, Any]:
        """Show available FAQ categories."""
        categories = {}
        for faq in self.faq_db:
            if faq.category not in categories:
                categories[faq.category] = []
            categories[faq.category].append(faq.question[:50] + "...")

        faq_list = "\n".join([f"**{cat}**: {', '.join(qs[:30])}..." for cat, qs in list(categories.items())[:5]])

        return {
            "type": "faq_list",
            "response": f"📚 Common Questions:\n\n{faq_list}\n\nReply with your question and I'll find the answer!",
            "categories": list(categories.keys()),
        }

    def _needs_human_help(self, query: str) -> bool:
        """Determine if query needs human intervention."""
        urgent_keywords = [
            "hack",
            "breach",
            "security",
            "urgent",
            "asap",
            "critical",
            "emergency",
            "down",
            "not working",
            "bug",
            "refund",
            "cancel",
            "lawyer",
            "legal",
        ]
        return any(kw in query for kw in urgent_keywords)

    async def _create_ticket(
        self,
        user_id: str,
        description: str,
        platform: str,
        channel_id: str,
        priority: TicketPriority = TicketPriority.MEDIUM,
    ) -> dict[str, Any]:
        """Create a support ticket."""
        self.ticket_counter += 1
        ticket_id = f"TICKET-{self.ticket_counter:05d}"

        # Determine priority based on keywords
        if any(kw in description.lower() for kw in ["urgent", "critical", "emergency"]) or any(kw in description.lower() for kw in ["payment", "refund"]):
            priority = TicketPriority.HIGH

        ticket = HelpDeskTicket(
            ticket_id=ticket_id,
            user_id=user_id,
            platform=platform,
            channel_id=channel_id,
            subject=description[:100],
            description=description,
            priority=priority,
            status=TicketStatus.OPEN,
            created_at=datetime.now(UTC),
            messages=[{"type": "user", "content": description, "timestamp": datetime.now(UTC).isoformat()}],
        )

        self.active_tickets[ticket_id] = ticket

        logger.info("Created ticket %s for user %s on %s", ticket_id, user_id, platform)

        return {
            "type": "ticket_created",
            "response": (
                f"✅ **Ticket Created: {ticket_id}**\n\n"
                f"Priority: {priority.value.upper()}\n"
                f"Status: Open\n\n"
                f"Our team will review your ticket shortly. "
                f"You can check status with `!ticket {ticket_id}`"
            ),
            "ticket_id": ticket_id,
            "priority": priority.value,
        }

    async def add_response(self, ticket_id: str, response: str, from_agent: bool = True) -> HelpDeskTicket | None:
        """Add a response to an existing ticket."""
        ticket = self.active_tickets.get(ticket_id)
        if not ticket:
            return None

        ticket.messages.append(
            {
                "type": "agent" if from_agent else "user",
                "content": response,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

        if from_agent:
            ticket.status = TicketStatus.PENDING

        return ticket

    async def resolve_ticket(self, ticket_id: str, resolution: str) -> HelpDeskTicket | None:
        """Mark a ticket as resolved."""
        ticket = self.active_tickets.get(ticket_id)
        if not ticket:
            return None

        ticket.status = TicketStatus.RESOLVED
        ticket.messages.append(
            {
                "type": "system",
                "content": "Resolved: %s" % resolution,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

        return ticket

    async def escalate_ticket(self, ticket_id: str, reason: str) -> HelpDeskTicket | None:
        """Escalate ticket to human moderator."""
        ticket = self.active_tickets.get(ticket_id)
        if not ticket:
            return None

        ticket.status = TicketStatus.ESCALATED
        ticket.priority = TicketPriority.HIGH
        ticket.messages.append(
            {"type": "system", "content": "Escalated: %s" % reason, "timestamp": datetime.now(UTC).isoformat()}
        )

        # In production: notify human moderators via webhook
        logger.warning("TICKET ESCALATED: %s - %s", ticket_id, reason)

        return ticket

    # -----------------------------------------------------------------
    # Public API methods (called from discord_bot_helix.py)
    # -----------------------------------------------------------------

    async def handle_query(
        self,
        user_id: str,
        query: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Public wrapper for ``handle_message`` used by the Discord bot.

        Args:
            user_id: The user identifier.
            query: The question / message text.
            context: Optional dict with extra metadata (discord_id, guild, etc.)
        """
        platform = "discord"
        channel_id = ""
        if context:
            platform = context.get("platform", "discord")
            channel_id = context.get("channel_id", "")
        return await self.handle_message(
            user_id=user_id,
            message=query,
            platform=platform,
            channel_id=channel_id,
        )

    async def get_faq(
        self,
        topic: str | None = None,
    ) -> dict[str, Any]:
        """
        Public wrapper around ``_show_faq`` with optional topic filtering.
        """
        base = self._show_faq()

        if topic:
            # Filter to a specific category if provided
            filtered = [
                {"question": faq.question, "answer": faq.answer}
                for faq in self.faq_db
                if topic.lower() in faq.category.lower() or any(topic.lower() in kw for kw in faq.keywords)
            ]
            if filtered:
                return {
                    "topic": topic,
                    "faqs": filtered,
                    "response": base.get("response", ""),
                }

        # No topic or no match — return all
        all_faqs = [{"question": faq.question, "answer": faq.answer} for faq in self.faq_db]
        return {
            "topic": "General Questions",
            "faqs": all_faqs,
            "response": base.get("response", ""),
        }

    async def create_ticket(
        self,
        user_id: str,
        subject: str,
        description: str,
        source: str = "discord",
    ) -> dict[str, Any]:
        """
        Public wrapper around ``_create_ticket`` used by the Discord bot.
        """
        full_message = "Subject: %s\n\n%s" % (subject, description)
        return await self._create_ticket(
            user_id=user_id,
            description=full_message,
            platform=source,
            channel_id="",
        )


# Singleton instance
_helpdesk_agent: HelpDeskAgent | None = None


def get_helpdesk_agent() -> HelpDeskAgent:
    """Get or create the helpdesk agent singleton."""
    global _helpdesk_agent
    if _helpdesk_agent is None:
        _helpdesk_agent = HelpDeskAgent()
    return _helpdesk_agent


# Discord command handlers (for helix-discord-bot)


async def handle_helpdesk_command(
    user_id: str,
    message: str,
    platform: str = "discord",
    channel_id: str = "",
) -> dict[str, Any]:
    """Main entry point for helpdesk commands."""
    agent = get_helpdesk_agent()
    return await agent.handle_message(user_id, message, platform, channel_id)


async def create_support_ticket(
    user_id: str,
    subject: str,
    description: str,
    platform: str = "discord",
    channel_id: str = "",
) -> dict[str, Any]:
    """Create a support ticket directly."""
    agent = get_helpdesk_agent()
    full_message = f"Subject: {subject}\n\n{description}"
    return await agent._create_ticket(user_id, full_message, platform, channel_id)


# Example Discord command integration

"""
In helix-discord-bot, add this command:

@commands.command(name="helpdesk", aliases=["support", "help"])
async def helpdesk_command(ctx, *, message: str = ""):
    '''Get help from the AI support agent.'''
    user_id = str(ctx.author.id)
    channel_id = str(ctx.channel.id)

    if not message:
        # Show help
        embed = discord.Embed(
            title="🆘 Help Desk",
            description="Get AI-powered support for Helix questions!",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Commands",
            value="• `!helpdesk <question>` - Ask a question\n"
                  "• `!faq` - Browse FAQ\n"
                  "• `!ticket <issue>` - Create support ticket",
            inline=False
        )
        await ctx.send(embed=embed)
        return

    # Process the message
    result = await handle_helpdesk_command(user_id, message, "discord", channel_id)

    # Send response
    await ctx.send(result.get("response", "Processing your request..."))

    # If ticket created, show ticket info
    if result.get("ticket_id"):
        embed = discord.Embed(
            title="📝 Support Ticket",
            description=f"Ticket ID: {result['ticket_id']}\n"
                        f"Priority: {result.get('priority', 'medium').upper()}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
"""
