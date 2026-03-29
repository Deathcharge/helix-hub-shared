"""
Code Completion Service for Helix IDE

Uses the UnifiedLLMService to generate inline code completions.
Optimized for low-latency with short max_tokens and low temperature.
"""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Allowed language identifiers — short alphanumeric names, optional +/#
_LANGUAGE_RE = re.compile(r"^[a-zA-Z0-9+#_.\-]{1,30}$")


@dataclass
class CompletionSuggestion:
    """A single inline completion suggestion."""

    text: str
    display_label: str | None = None


@dataclass
class CompletionResult:
    """Result from a completion request."""

    suggestions: list[CompletionSuggestion] = field(default_factory=list)
    model_used: str | None = None
    cached: bool = False


# System prompt optimized for code completion
_COMPLETION_SYSTEM_PROMPT = """You are a code completion engine. Given a code file with a cursor position marked as <CURSOR>, generate the most likely code that should follow.

Rules:
- Return ONLY the completion text, nothing else
- Do not repeat any text before the cursor
- Do not include explanations, markdown, or code fences
- Keep completions concise (1-3 lines preferred)
- Match the code style, indentation, and patterns in the file
- If the cursor is in the middle of a line, complete the rest of that line first
- Consider the file language and standard library conventions"""

# System prompt for code explanation
_EXPLAIN_SYSTEM_PROMPT = """You are a helpful code assistant for the Helix IDE. Explain the given code clearly and concisely.

Rules:
- Be concise but thorough
- Highlight key patterns, potential issues, and improvements
- Use the user's code context to give relevant explanations
- Format with markdown for readability"""


class CodeCompletionService:
    """AI-powered code completion for the Helix IDE."""

    def __init__(self):
        self._llm = None

    def _get_llm(self):
        """Lazy-load the LLM service."""
        if self._llm is None:
            try:
                from apps.backend.services.unified_llm import UnifiedLLMService

                self._llm = UnifiedLLMService()
            except Exception as e:
                logger.error("Failed to initialize UnifiedLLMService: %s", e)
                raise
        return self._llm

    async def complete(
        self,
        file_content: str,
        cursor_line: int,
        cursor_column: int,
        language: str,
        context_files: list[dict[str, str]] | None = None,
        user_id: str | None = None,
    ) -> CompletionResult:
        """
        Generate inline code completions.

        Args:
            file_content: Full content of the file being edited
            cursor_line: 1-based line number of cursor
            cursor_column: 1-based column number of cursor
            language: Programming language (e.g. 'python', 'typescript')
            context_files: Optional list of nearby open files for context
            user_id: User ID for BYOT key lookup

        Returns:
            CompletionResult with suggestions
        """
        try:
            llm = self._get_llm()

            # Sanitise language — it is interpolated into the prompt
            if not _LANGUAGE_RE.match(language):
                language = "plaintext"

            # Build the prompt with cursor marker
            lines = file_content.split("\n")
            line_idx = max(0, cursor_line - 1)
            col_idx = max(0, cursor_column - 1)

            # Insert cursor marker
            if line_idx < len(lines):
                line = lines[line_idx]
                lines[line_idx] = line[:col_idx] + "<CURSOR>" + line[col_idx:]

            # Use a window around cursor to limit prompt size
            start = max(0, line_idx - 50)
            end = min(len(lines), line_idx + 20)
            code_window = "\n".join(lines[start:end])

            # Build context from nearby files
            context_str = ""
            if context_files:
                for cf in context_files[:3]:
                    # Include up to 500 chars from each context file
                    content_preview = cf.get("content", "")[:500]
                    context_str += (
                        f"\n--- {cf.get('path', 'unknown')} ({cf.get('language', '')}) ---\n" f"{content_preview}\n"
                    )

            prompt = f"Language: {language}\n"
            if context_str:
                prompt += f"\nContext from open files:{context_str}\n"
            prompt += f"\nComplete the code at <CURSOR>:\n\n```\n{code_window}\n```"

            response = await llm.chat(
                messages=[
                    {"role": "system", "content": _COMPLETION_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=256,
                temperature=0.2,
                user_id=user_id,
            )

            # Parse the response — strip any accidental markdown fencing
            text = response.strip()
            if text.startswith("```"):
                # Remove code fence wrapper
                lines_resp = text.split("\n")
                if len(lines_resp) > 2:
                    text = "\n".join(lines_resp[1:-1])
                else:
                    text = ""

            if not text:
                return CompletionResult()

            return CompletionResult(
                suggestions=[CompletionSuggestion(text=text)],
            )

        except Exception as e:
            logger.warning("Code completion failed: %s", e)
            return CompletionResult()

    async def complete_from_prefix(
        self,
        prefix: str,
        suffix: str,
        language: str,
        max_tokens: int = 128,
        user_id: str | None = None,
    ) -> CompletionResult:
        """
        Generate code completion from prefix/suffix context (VS Code extension style).

        Args:
            prefix: Code before cursor (truncated to last 30000 chars)
            suffix: Code after cursor (truncated to first 10000 chars)
            language: Programming language
            max_tokens: Max tokens for completion (capped at 512)
            user_id: User ID for BYOT key lookup

        Returns:
            CompletionResult with suggestions
        """
        # Enforce input bounds at service layer (defense in depth)
        prefix = prefix[-30000:] if len(prefix) > 30000 else prefix
        suffix = suffix[:10000] if len(suffix) > 10000 else suffix
        max_tokens = max(1, min(max_tokens, 512))
        try:
            llm = self._get_llm()

            prompt = f"Complete the following code:\n\n{prefix}"
            if suffix.strip():
                prompt += f"\n\n// Code after cursor:\n{suffix}"

            response = await llm.chat(
                messages=[
                    {"role": "system", "content": _COMPLETION_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Language: {language}\n\n{prompt}"},
                ],
                max_tokens=max_tokens,
                temperature=0.2,
                user_id=user_id,
            )

            text = response.strip()
            if text.startswith("```"):
                lines_resp = text.split("\n")
                if len(lines_resp) > 2:
                    text = "\n".join(lines_resp[1:-1])
                else:
                    text = ""

            if not text:
                return CompletionResult()

            return CompletionResult(
                suggestions=[CompletionSuggestion(text=text)],
            )

        except Exception as e:
            logger.warning("Code completion (prefix) failed: %s", e)
            return CompletionResult()

    async def explain(
        self,
        code: str,
        language: str,
        question: str | None = None,
        user_id: str | None = None,
    ) -> str:
        """
        Explain a code selection.

        Args:
            code: The code to explain
            language: Programming language
            question: Optional specific question about the code
            user_id: User ID for BYOT key lookup

        Returns:
            Explanation text
        """
        try:
            llm = self._get_llm()

            # Sanitise language — it is interpolated into the prompt
            if not _LANGUAGE_RE.match(language):
                language = "plaintext"

            prompt = f"Language: {language}\n\n```{language}\n{code[:3000]}\n```"
            if question:
                prompt += f"\n\nSpecific question: {question}"
            else:
                prompt += "\n\nExplain this code."

            response = await llm.chat(
                messages=[
                    {"role": "system", "content": _EXPLAIN_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1024,
                temperature=0.3,
                user_id=user_id,
            )

            return response.strip()

        except Exception as e:
            logger.warning("Code explanation failed: %s", e)
            return "Unable to generate explanation. Please try again."


# Singleton
code_completion_service = CodeCompletionService()
