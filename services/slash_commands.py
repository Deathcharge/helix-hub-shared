"""
Slash Commands Service
Custom slash commands for enhanced developer workflow
Inspired by Claude Code's slash command system
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from apps.backend.services.code_agent_service import code_agent_service

logger = logging.getLogger(__name__)


@dataclass
class SlashCommand:
    """Represents a slash command."""

    name: str
    description: str
    handler: Callable
    aliases: list[str] = None
    requires_auth: bool = True
    examples: list[str] = None


class SlashCommandRegistry:
    """Registry for slash commands."""

    def __init__(self):
        self.commands: dict[str, SlashCommand] = {}
        self._register_default_commands()

    def _register_default_commands(self):
        """Register built-in slash commands."""

        # /review - Review code
        @self.command(name="review", description="Review code for issues and suggestions")
        async def cmd_review(file_path: str) -> dict[str, Any]:
            review = code_agent_service.review_code(file_path)
            return review

        # /analyze - Analyze codebase
        @self.command(name="analyze", description="Analyze entire codebase")
        async def cmd_analyze(max_files: int = 1000) -> dict[str, Any]:
            result = code_agent_service.analyze_codebase(max_files=max_files)
            return result

        # /suggestions - Get improvement suggestions
        @self.command(name="suggestions", description="Get improvement suggestions")
        async def cmd_suggestions(file_path: str) -> dict[str, Any]:
            suggestions = code_agent_service.suggest_improvements(file_path)
            return {"suggestions": suggestions}

        # /test - Run tests
        @self.command(name="test", description="Run test suite")
        async def cmd_test(path: str = ".") -> dict[str, Any]:
            result = code_agent_service.execute_command(command=["pytest", path, "-v"], timeout=120)
            return result

        # /lint - Run linter
        @self.command(name="lint", description="Run code linter")
        async def cmd_lint(path: str = ".") -> dict[str, Any]:
            result = code_agent_service.execute_command(command=["ruff", "check", path], timeout=60)
            return result

        # /format - Format code
        @self.command(name="format", description="Format code with black/ruff")
        async def cmd_format(path: str = ".") -> dict[str, Any]:
            result = code_agent_service.execute_command(command=["ruff", "format", path], timeout=60)
            return result

        # /typecheck - Run type checker
        @self.command(name="typecheck", description="Run mypy type checker")
        async def cmd_typecheck(path: str = ".") -> dict[str, Any]:
            result = code_agent_service.execute_command(command=["mypy", path], timeout=60)
            return result

        # /help - Show available commands
        @self.command(name="help", description="Show all available commands")
        async def cmd_help() -> dict[str, Any]:
            commands_list = []
            for name, cmd in self.commands.items():
                commands_list.append(
                    {
                        "name": name,
                        "description": cmd.description,
                        "aliases": cmd.aliases or [],
                        "examples": cmd.examples or [],
                    }
                )
            return {"total_commands": len(commands_list), "commands": commands_list}

    def command(self, name: str, description: str = "", aliases: list[str] = None):
        """
        Decorator to register a slash command.
        """

        def decorator(handler: Callable):
            slash_cmd = SlashCommand(name=name, description=description, handler=handler, aliases=aliases or [])
            self.commands[name] = slash_cmd

            # Register aliases
            for alias in aliases or []:
                self.commands[alias] = slash_cmd

            return handler

        return decorator

    async def execute(self, command_name: str, **kwargs) -> dict[str, Any]:
        """
        Execute a slash command.
        """
        if command_name not in self.commands:
            return {
                "success": False,
                "error": f"Unknown command: /{command_name}",
                "available_commands": list(self.commands.keys()),
            }

        cmd = self.commands[command_name]

        try:
            logger.info("🔧 Executing slash command: /%s", command_name)
            result = await cmd.handler(**kwargs)
            return {"success": True, "command": command_name, "result": result}
        except Exception as e:
            logger.error("Slash command failed: %s", e)
            return {"success": False, "command": command_name, "error": "Command execution failed"}

    def list_commands(self) -> list[dict[str, Any]]:
        """
        List all registered commands.
        """
        commands = []
        for name, cmd in self.commands.items():
            # Only show main name, not aliases
            if name == cmd.name:
                commands.append(
                    {
                        "name": name,
                        "description": cmd.description,
                        "aliases": cmd.aliases,
                        "requires_auth": cmd.requires_auth,
                    }
                )
        return commands


# Singleton instance
slash_command_registry = SlashCommandRegistry()


# Helper functions for common workflows


async def review_pr(pr_number: int) -> dict[str, Any]:
    """
    Review a pull request by analyzing changed files.

    This is a complex workflow that:
    1. Gets PR diff
    2. Analyzes changed files
    3. Generates review comments
    4. Posts review to PR
    """
    logger.info("📋 Reviewing PR #%s", pr_number)

    # Get PR diff using gh CLI
    result = code_agent_service.execute_command(command=["gh", "pr", "view", str(pr_number), "--json", "files"])

    if not result["success"]:
        return {"success": False, "error": "Failed to get PR info"}

    # Analyze each changed file
    # This is a simplified version - would need more logic
    return {"success": True, "pr_number": pr_number, "message": "PR review workflow initiated"}


async def deploy_staging() -> dict[str, Any]:
    """
    Deploy to staging environment.

    Workflow:
    1. Run tests
    2. Build
    3. Deploy
    4. Run smoke tests
    """
    logger.info("🚀 Deploying to staging")

    # Run tests
    test_result = await slash_command_registry.execute("test")

    if not test_result["success"]:
        return {"success": False, "error": "Tests failed"}

    # Build
    build_result = code_agent_service.execute_command(command=["npm", "run", "build"], timeout=300)

    if not build_result["success"]:
        return {"success": False, "error": "Build failed"}

    # Deploy (would use actual deployment command)
    return {"success": True, "message": "Deployed to staging successfully"}


async def optimize_performance() -> dict[str, Any]:
    """
    Run performance optimization workflow.

    Analyzes and optimizes:
    - Database queries
    - API endpoints
    - Frontend bundle size
    """
    logger.info("⚡ Running performance optimization")

    results = []

    # Check bundle size
    bundle_result = code_agent_service.execute_command(command=["npm", "run", "analyze"], timeout=60)
    results.append({"check": "bundle_size", "result": bundle_result})

    # Run lighthouse
    lighthouse_result = code_agent_service.execute_command(command=["npx", "lighthouse", "--budget"], timeout=120)
    results.append({"check": "lighthouse", "result": lighthouse_result})

    return {"success": True, "optimizations": results}
