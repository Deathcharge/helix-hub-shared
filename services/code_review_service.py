"""
🔍 Helix AI Code Review Service
Backend service for AI-powered code reviews accessible through agent chat.

Provides code review capabilities that can be triggered:
1. Through the GitHub App (webhook-driven)
2. Through agent chat interface (user-initiated)
3. Through the API (programmatic access)

Features:
- Multi-language support (Python, JavaScript, TypeScript, etc.)
- Security vulnerability scanning
- Performance issue detection
- Code quality scoring
- Kael ethical analysis integration
- Shadow security analysis integration

Author: Helix Production Engineering
Version: 21.1.0
"""

import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================


class CodeReviewRequest(BaseModel):
    """Request model for code review."""

    code: str = Field(..., description="Code to review", max_length=50000)
    language: str = Field(default="auto", description="Programming language (auto-detect if not specified)")
    filename: str | None = Field(default=None, description="Optional filename for context")
    context: str | None = Field(default=None, description="Additional context about the code")
    review_type: str = Field(
        default="comprehensive",
        description="Type of review: comprehensive, security, performance, quick",
    )
    agent: str = Field(default="kael", description="Agent to perform the review")


class CodeReviewFinding(BaseModel):
    """A single finding from code review."""

    line: int | None = None
    severity: str  # critical, warning, suggestion, praise, info
    category: str  # security, performance, bug, style, maintainability, etc.
    message: str
    suggestion: str | None = None
    code_snippet: str | None = None


class CodeReviewResponse(BaseModel):
    """Response model for code review."""

    review_id: str
    findings: list[CodeReviewFinding]
    summary: str
    score: float  # 0-100 quality score
    language: str
    lines_reviewed: int
    review_type: str
    agent: str
    timestamp: str
    metadata: dict[str, Any] = {}


# ============================================================================
# PATTERN-BASED ANALYZERS
# ============================================================================

# Security patterns (language-agnostic)
SECURITY_PATTERNS = [
    (r"password\s*=\s*['&quot;][^'&quot;]+['&quot;]", "critical", "Hardcoded password detected. Use environment variables or a secrets manager."),
    (r"api[_-]?key\s*=\s*['&quot;][^'&quot;]+['&quot;]", "critical", "Hardcoded API key detected. Use environment variables."),
    (r"secret\s*=\s*['&quot;][^'&quot;]+['&quot;]", "critical", "Hardcoded secret detected. Use environment variables."),
    (r"eval\s*\(", "critical", "eval() is a security risk. Use safer alternatives."),
    (r"exec\s*\(", "warning", "exec() can execute arbitrary code. Consider safer alternatives."),
    (r"pickle\.loads?\s*\(", "critical", "pickle can execute arbitrary code. Use json or a safe serialization format."),
    (r"subprocess.*shell\s*=\s*True", "critical", "shell=True in subprocess is a command injection risk."),
    (r"os\.system\s*\(", "warning", "os.system() is vulnerable to command injection. Use subprocess.run()."),
    (r"innerHTML\s*=", "warning", "innerHTML can lead to XSS. Use textContent or sanitize input."),
    (r"document\.write\s*\(", "warning", "document.write() can overwrite the page. Use DOM manipulation."),
]

# Python-specific patterns
PYTHON_PATTERNS = [
    (r"except\s*:", "warning", "Bare except clause catches all exceptions. Use specific exception types."),
    (r"import\s+\*", "warning", "Wildcard imports make it unclear which names are in the namespace."),
    (r"print\s*\(", "suggestion", "Consider using logging instead of print() for production code."),
    (r"TODO|FIXME|HACK|XXX", "info", "TODO/FIXME comment found. Consider creating an issue to track this."),
    (r"\.format\s*\(", "suggestion", "Consider using f-strings for better readability (Python 3.6+)."),
    (r"type\s*:\s*ignore", "warning", "Type ignore comment suppresses type checking. Fix the underlying issue."),
    (r"noqa", "info", "Linting suppression found. Ensure this is intentional."),
    (r"global\s+\w+", "warning", "Global variable modification can lead to hard-to-debug issues."),
    (r"time\.sleep\s*\(", "suggestion", "Blocking sleep in async context. Consider asyncio.sleep() if in async code."),
]

# JavaScript/TypeScript patterns
JS_PATTERNS = [
    (r"\bvar\s+", "suggestion", "Use const or let instead of var for better scoping."),
    (r"==(?!=)", "suggestion", "Use === for strict equality comparison."),
    (r"console\.(log|debug|info)\s*\(", "suggestion", "Remove console.log statements before production."),
    (r"any(?:\s|[;,)\]])", "suggestion", "Avoid using `any` type. Use specific types for better type safety."),
    (r"@ts-ignore", "warning", "@ts-ignore suppresses type checking. Fix the underlying type issue."),
    (r"new\s+Promise\s*\(\s*async", "warning", "Async function inside new Promise is an anti-pattern."),
    (r"\.then\s*\(.*\.then\s*\(", "suggestion", "Nested .then() chains. Consider using async/await for readability."),
]


# ============================================================================
# CODE REVIEW SERVICE
# ============================================================================


class CodeReviewService:
    """
    AI-powered code review service for the Helix platform.

    Can be used standalone or integrated with agent chat.
    """

    def __init__(self):
        self._llm_engine = None

    async def _get_llm_engine(self):
        """Lazy-load the LLM engine."""
        if self._llm_engine is None:
            try:
                from apps.backend.llm_agent_engine import get_llm_engine

                self._llm_engine = get_llm_engine()
            except ImportError:
                logger.warning("LLM engine not available for code review")
        return self._llm_engine

    async def review_code(self, request: CodeReviewRequest) -> CodeReviewResponse:
        """
        Perform a comprehensive code review.

        Args:
            request: CodeReviewRequest with code and options

        Returns:
            CodeReviewResponse with findings and summary
        """
        # Auto-detect language
        language = request.language
        if language == "auto":
            language = self._detect_language(request.code, request.filename)

        lines = request.code.split("\n")
        review_id = hashlib.sha256(
            f"{request.code[:100]}{datetime.now(UTC).isoformat()}".encode()
        ).hexdigest()[:12]

        # Run pattern analysis
        pattern_findings = self._run_pattern_analysis(request.code, language)

        # Run LLM analysis if available
        llm_findings = []
        llm_summary = ""
        if request.review_type != "quick":
            llm_findings, llm_summary = await self._run_llm_analysis(
                request.code, language, request.context, request.review_type
            )

        # Combine findings
        all_findings = self._deduplicate_findings(pattern_findings + llm_findings)

        # Calculate quality score
        score = self._calculate_quality_score(all_findings, len(lines))

        # Generate summary
        summary = self._generate_summary(all_findings, score, language, len(lines), llm_summary)

        return CodeReviewResponse(
            review_id=review_id,
            findings=[CodeReviewFinding(**f) for f in all_findings],
            summary=summary,
            score=score,
            language=language,
            lines_reviewed=len(lines),
            review_type=request.review_type,
            agent=request.agent,
            timestamp=datetime.now(UTC).isoformat(),
            metadata={
                "pattern_findings": len(pattern_findings),
                "llm_findings": len(llm_findings),
                "total_findings": len(all_findings),
            },
        )

    def _detect_language(self, code: str, filename: str | None = None) -> str:
        """Auto-detect programming language from code content or filename."""
        if filename:
            ext_map = {
                ".py": "python", ".js": "javascript", ".ts": "typescript",
                ".tsx": "typescript", ".jsx": "javascript", ".rb": "ruby",
                ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin",
                ".swift": "swift", ".cs": "csharp", ".cpp": "cpp", ".c": "c",
                ".php": "php", ".sql": "sql", ".sh": "shell", ".bash": "shell",
            }
            for ext, lang in ext_map.items():
                if filename.endswith(ext):
                    return lang

        # Heuristic detection from code content
        if "def " in code and "import " in code:
            return "python"
        if "function " in code or "const " in code or "=>" in code:
            return "javascript"
        if "interface " in code and (":" in code) and ("import " in code):
            return "typescript"
        if "func " in code and "package " in code:
            return "go"
        if "fn " in code and "let mut " in code:
            return "rust"

        return "unknown"

    def _run_pattern_analysis(self, code: str, language: str) -> list[dict]:
        """Run static pattern analysis on code."""
        findings = []
        lines = code.split("\n")

        # Always run security patterns
        patterns = list(SECURITY_PATTERNS)

        # Add language-specific patterns
        if language == "python":
            patterns.extend(PYTHON_PATTERNS)
        elif language in ("javascript", "typescript"):
            patterns.extend(JS_PATTERNS)

        for line_num, line in enumerate(lines, 1):
            for pattern, severity, message in patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    findings.append({
                        "line": line_num,
                        "severity": severity,
                        "category": "security" if severity == "critical" else "style",
                        "message": message,
                        "code_snippet": line.strip()[:200],
                    })

        return findings

    async def _run_llm_analysis(
        self,
        code: str,
        language: str,
        context: str | None,
        review_type: str,
    ) -> tuple[list[dict], str]:
        """Run LLM-powered deep analysis."""
        engine = await self._get_llm_engine()
        if not engine:
            return [], ""

        # Build review prompt
        focus_areas = {
            "comprehensive": "bugs, security, performance, error handling, maintainability, and testing",
            "security": "security vulnerabilities, injection risks, authentication issues, and data exposure",
            "performance": "performance bottlenecks, memory leaks, N+1 queries, and optimization opportunities",
        }.get(review_type, "general code quality")

        prompt = f"""You are an expert code reviewer. Review this {language} code focusing on {focus_areas}.

```{language}
{code[:8000]}
```

{f"Context: {context}" if context else ""}

Provide your review as JSON:
{{
  "findings": [
    {{
      "line": <line_number>,
      "severity": "critical|warning|suggestion",
      "category": "security|performance|bug|style|maintainability|error_handling",
      "message": "Clear description",
      "suggestion": "Optional fix"
    }}
  ],
  "summary": "Brief overall assessment"
}}

Be specific. Only report genuine issues."""

        try:
            response = await engine.generate(prompt, max_tokens=2048)
            return self._parse_llm_response(response)
        except Exception as e:
            logger.error("LLM code review failed: %s", e)
            return [], ""

    def _parse_llm_response(self, response: str) -> tuple[list[dict], str]:
        """Parse LLM response into findings."""
        try:
            # Extract JSON from response
            json_match = re.search(r"```json\s*([\s\S]*?)\s*```", response)
            if not json_match:
                json_match = re.search(r"\{[\s\S]*&quot;findings&quot;[\s\S]*\}", response)

            if not json_match:
                return [], ""

            json_str = json_match.group(1) if json_match.lastindex else json_match.group(0)
            parsed = json.loads(json_str)

            findings = []
            for f in parsed.get("findings", []):
                if f.get("message"):
                    findings.append({
                        "line": f.get("line"),
                        "severity": f.get("severity", "suggestion"),
                        "category": f.get("category", "maintainability"),
                        "message": f["message"],
                        "suggestion": f.get("suggestion"),
                        "code_snippet": None,
                    })

            return findings, parsed.get("summary", "")

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("Failed to parse LLM review response: %s", e)
            return [], ""

    def _deduplicate_findings(self, findings: list[dict]) -> list[dict]:
        """Remove duplicate findings."""
        seen = set()
        unique = []
        for f in findings:
            key = f"{f.get('line', 0)}:{f.get('category', '')}:{f.get('message', '')[:50]}"
            if key not in seen:
                seen.add(key)
                unique.append(f)

        # Sort by severity
        severity_order = {"critical": 0, "warning": 1, "suggestion": 2, "info": 3, "praise": 4}
        unique.sort(key=lambda f: severity_order.get(f.get("severity", "info"), 3))

        return unique

    def _calculate_quality_score(self, findings: list[dict], total_lines: int) -> float:
        """Calculate a quality score from 0-100."""
        if total_lines == 0:
            return 100.0

        # Penalty weights
        penalties = {
            "critical": 15,
            "warning": 5,
            "suggestion": 1,
            "info": 0,
            "praise": -2,  # Bonus for good patterns
        }

        total_penalty = sum(
            penalties.get(f.get("severity", "info"), 0)
            for f in findings
        )

        # Normalize by code size (larger code gets more lenient scoring)
        size_factor = max(1, total_lines / 50)
        normalized_penalty = total_penalty / size_factor

        score = max(0, min(100, 100 - normalized_penalty))
        return round(score, 1)

    def _generate_summary(
        self,
        findings: list[dict],
        score: float,
        language: str,
        lines: int,
        llm_summary: str,
    ) -> str:
        """Generate a human-readable review summary."""
        critical = sum(1 for f in findings if f.get("severity") == "critical")
        warnings = sum(1 for f in findings if f.get("severity") == "warning")
        suggestions = sum(1 for f in findings if f.get("severity") == "suggestion")

        # Score emoji
        if score >= 90:
            emoji = "✅"
            verdict = "Excellent"
        elif score >= 75:
            emoji = "🟢"
            verdict = "Good"
        elif score >= 60:
            emoji = "🟡"
            verdict = "Needs Improvement"
        else:
            emoji = "🔴"
            verdict = "Significant Issues"

        summary = f"{emoji} **Code Quality: {score}/100 ({verdict})**\n\n"
        summary += f"Reviewed {lines} lines of {language} code.\n\n"

        if critical > 0:
            summary += f"🔴 **{critical} critical issue(s)** must be fixed.\n"
        if warnings > 0:
            summary += f"🟡 **{warnings} warning(s)** should be addressed.\n"
        if suggestions > 0:
            summary += f"💡 **{suggestions} suggestion(s)** for improvement.\n"

        if llm_summary:
            summary += f"\n{llm_summary}\n"

        if not findings:
            summary += "\n✨ No issues found. Code looks clean!"

        return summary


# Singleton instance
code_review_service = CodeReviewService()
