"""
🤖 Agentic Coding Service - Claude Code-style autonomous coding
Helix Collective v18.0

Provides autonomous coding capabilities:
- Task understanding and planning
- File search and context gathering
- Diff-based code editing
- Validation and iteration
- Git operations

Copyright (c) 2025 Andrew John Ward. All Rights Reserved.
"""

import asyncio
import difflib
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Status of an agentic coding task."""

    PENDING = "pending"
    ANALYZING = "analyzing"
    EDITING = "editing"
    VALIDATING = "validating"
    COMPLETE = "complete"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class CodeEdit:
    """Represents a single code edit operation."""

    file_path: str
    old_content: str
    new_content: str
    description: str
    line_start: int | None = None
    line_end: int | None = None


@dataclass
class TaskContext:
    """Context for an agentic coding task."""

    task_id: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    working_directory: str = "."
    relevant_files: list[str] = field(default_factory=list)
    edits_made: list[CodeEdit] = field(default_factory=list)
    validation_results: list[dict] = field(default_factory=list)
    iteration_count: int = 0
    max_iterations: int = 10
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None
    error: str | None = None


class DiffEditor:
    """
    Diff-based file editor for surgical code changes.
    Like Claude Code's replace_string_in_file but smarter.
    """

    # Directories that should never be read or written by the agentic coder
    _BLOCKED_PREFIXES = ("/etc", "/var", "/proc", "/sys", "/dev", "/tmp")

    @staticmethod
    def _validate_path(file_path: str) -> Path:
        """Validate that file_path is a safe, non-traversal path.

        Returns the resolved Path on success.
        Raises ValueError on directory traversal or blocked paths.
        """
        resolved = Path(file_path).resolve()
        resolved_str = str(resolved).replace("\\", "/")

        # Block absolute Unix system paths
        for prefix in DiffEditor._BLOCKED_PREFIXES:
            if resolved_str.startswith(prefix):
                raise ValueError(f"Access denied: system path {prefix}")

        # Block obvious traversal patterns in the raw input
        normalised_input = file_path.replace("\\", "/")
        if ".." in normalised_input.split("/"):
            raise ValueError(f"Path traversal detected in: {file_path}")

        return resolved

    @staticmethod
    def apply_diff(file_path: str, old_text: str, new_text: str) -> tuple[bool, str]:
        """
        Apply a diff-based edit to a file.

        Args:
            file_path: Path to the file
            old_text: Exact text to find and replace
            new_text: Text to replace with

        Returns:
            (success, message)
        """
        try:
            path = DiffEditor._validate_path(file_path)
            if not path.exists():
                return False, f"File not found: {file_path}"

            content = path.read_text(encoding="utf-8")

            # Find exact match
            if old_text not in content:
                # Try fuzzy match

                # Use difflib to find closest match
                matcher = difflib.SequenceMatcher(None, content, old_text)
                match = matcher.find_longest_match(0, len(content), 0, len(old_text))

                if match.size < len(old_text) * 0.8:  # Less than 80% match
                    return (
                        False,
                        "Could not find exact text to replace. Text may have changed.",
                    )

                # Found fuzzy match - warn but proceed
                logger.warning("Using fuzzy match for edit in %s", file_path)

            # Apply replacement
            new_content = content.replace(old_text, new_text, 1)

            if new_content == content:
                return False, "No changes made - text not found or identical"

            # Write back
            path.write_text(new_content, encoding="utf-8")

            return True, f"Successfully edited {file_path}"

        except Exception as e:
            logger.error("Failed to apply diff to %s: %s", file_path, e)
            return False, str(e)

    @staticmethod
    def apply_line_edit(file_path: str, start_line: int, end_line: int, new_content: str) -> tuple[bool, str]:
        """
        Replace specific lines in a file.

        Args:
            file_path: Path to the file
            start_line: Starting line number (1-indexed)
            end_line: Ending line number (inclusive)
            new_content: New content for those lines

        Returns:
            (success, message)
        """
        try:
            path = DiffEditor._validate_path(file_path)
            if not path.exists():
                return False, f"File not found: {file_path}"

            lines = path.read_text(encoding="utf-8").split("\n")

            if start_line < 1 or end_line > len(lines):
                return (
                    False,
                    f"Line range {start_line}-{end_line} out of bounds (file has {len(lines)} lines)",
                )

            # Replace lines (convert to 0-indexed)
            new_lines = new_content.split("\n")
            lines[start_line - 1 : end_line] = new_lines

            path.write_text("\n".join(lines), encoding="utf-8")

            return True, f"Replaced lines {start_line}-{end_line} in {file_path}"

        except Exception as e:
            logger.error("Failed to edit lines in %s: %s", file_path, e)
            return False, str(e)

    @staticmethod
    def generate_diff_preview(old_content: str, new_content: str, file_path: str = "") -> str:
        """Generate a unified diff preview."""
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            lineterm="",
        )

        return "".join(diff)

    @staticmethod
    def generate_diff(content: str, old_text: str, new_text: str) -> str:
        """Generate a diff preview for a text replacement within a file."""
        new_content = content.replace(old_text, new_text, 1)
        return DiffEditor.generate_diff_preview(content, new_content)


class GitOperations:
    """Git operations for the agentic coder."""

    def __init__(self, working_dir: str = "."):
        self.working_dir = working_dir

    def _run_git(self, *args: str) -> tuple[bool, str]:
        """Run a git command and return (success, output)."""
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return True, result.stdout.strip()
            return False, result.stderr.strip()
        except subprocess.TimeoutExpired:
            return False, "Git command timed out"
        except FileNotFoundError:
            return False, "Git not found"
        except Exception as e:
            return False, str(e)

    def status(self) -> dict:
        """Get git status."""
        success, output = self._run_git("status", "--porcelain")
        if not success:
            return {"error": output}

        changes = {"staged": [], "unstaged": [], "untracked": []}
        for line in output.split("\n"):
            if not line:
                continue
            status = line[:2]
            file_path = line[3:]

            if status[0] in "MADRC":
                changes["staged"].append({"status": status[0], "file": file_path})
            if status[1] in "MADRC":
                changes["unstaged"].append({"status": status[1], "file": file_path})
            if status == "??":
                changes["untracked"].append(file_path)

        return changes

    def diff(self, file_path: str | None = None, staged: bool = False) -> str:
        """Get git diff."""
        args = ["diff"]
        if staged:
            args.append("--staged")
        if file_path:
            args.append(file_path)

        success, output = self._run_git(*args)
        return output if success else f"Error: {output}"

    def add(self, files: list[str]) -> tuple[bool, str]:
        """Stage files."""
        return self._run_git("add", *files)

    def commit(self, message: str) -> tuple[bool, str]:
        """Create a commit."""
        return self._run_git("commit", "-m", message)

    def branch(self, name: str | None = None, create: bool = False) -> tuple[bool, str]:
        """List or create branches."""
        if name and create:
            return self._run_git("checkout", "-b", name)
        elif name:
            return self._run_git("checkout", name)
        return self._run_git("branch", "--list")

    def log(self, count: int = 10) -> list[dict]:
        """Get recent commits."""
        success, output = self._run_git("log", f"-{count}", "--pretty=format:%H|%an|%ae|%s|%ci")
        if not success:
            return []

        commits = []
        for line in output.split("\n"):
            if not line:
                continue
            parts = line.split("|")
            if len(parts) >= 5:
                commits.append(
                    {
                        "hash": parts[0],
                        "author": parts[1],
                        "email": parts[2],
                        "message": parts[3],
                        "date": parts[4],
                    }
                )
        return commits


class CodeValidator:
    """Validates code changes."""

    @staticmethod
    def check_python_syntax(file_path: str) -> tuple[bool, str]:
        """Check Python file for syntax errors."""
        try:
            result = subprocess.run(
                ["python", "-m", "py_compile", file_path],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return True, "Syntax OK"
            return False, result.stderr
        except Exception as e:
            return False, str(e)

    @staticmethod
    def check_typescript_syntax(file_path: str) -> tuple[bool, str]:
        """Check TypeScript file for syntax errors."""
        try:
            result = subprocess.run(
                ["npx", "tsc", "--noEmit", file_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return True, "TypeScript OK"
            return False, result.stderr
        except Exception as e:
            return False, str(e)

    @staticmethod
    def validate_file(file_path: str) -> tuple[bool, str]:
        """Validate a file based on its extension."""
        ext = Path(file_path).suffix.lower()

        if ext == ".py":
            return CodeValidator.check_python_syntax(file_path)
        elif ext in (".ts", ".tsx"):
            return CodeValidator.check_typescript_syntax(file_path)
        elif ext in (".js", ".jsx"):
            return True, "JavaScript (no strict validation)"
        elif ext == ".json":
            try:
                json.loads(Path(file_path).read_text())
                return True, "Valid JSON"
            except json.JSONDecodeError as e:
                return False, f"Invalid JSON: {e}"
        else:
            return True, f"No validator for {ext}"


class AgenticCoder:
    """
    Autonomous coding agent that operates like Claude Code.

    Workflow:
    1. Understand task
    2. Search for relevant files
    3. Plan edits
    4. Apply diff-based edits
    5. Validate changes
    6. Iterate until complete or max iterations
    """

    def __init__(self, working_dir: str = "."):
        self.working_dir = Path(working_dir).resolve()
        self.editor = DiffEditor()
        self.git = GitOperations(str(self.working_dir))
        self.validator = CodeValidator()
        self.active_tasks: dict[str, TaskContext] = {}

    async def create_task(self, description: str, files: list[str] = None) -> TaskContext:
        """Create a new coding task."""
        import uuid

        task_id = str(uuid.uuid4())[:8]
        task = TaskContext(
            task_id=task_id,
            description=description,
            working_directory=str(self.working_dir),
            relevant_files=files or [],
        )

        self.active_tasks[task_id] = task
        logger.info("Created agentic task %s: %s", task_id, description[:50])

        return task

    def search_files(self, working_dir: str, query: str, file_pattern: str | None = None) -> list[dict]:
        """
        Search for code in the repository.

        Args:
            working_dir: Directory to search in
            query: Search query
            file_pattern: Optional file pattern (e.g., *.py)

        Returns:
            List of results with file paths and previews
        """
        import fnmatch

        results = []
        search_dir = Path(working_dir).resolve()
        query_lower = query.lower()

        for root, dirs, files in os.walk(search_dir):
            # Skip common non-code directories
            dirs[:] = [
                d
                for d in dirs
                if d
                not in {
                    "__pycache__",
                    "node_modules",
                    ".git",
                    ".venv",
                    "venv",
                    "dist",
                    "build",
                    ".next",
                    "coverage",
                    ".mypy_cache",
                }
            ]

            for file in files:
                # Apply file pattern filter
                if file_pattern and not fnmatch.fnmatch(file, file_pattern):
                    continue

                # Only search code files
                if not any(
                    file.endswith(ext)
                    for ext in [
                        ".py",
                        ".ts",
                        ".tsx",
                        ".js",
                        ".jsx",
                        ".json",
                        ".md",
                        ".yaml",
                        ".yml",
                        ".html",
                        ".css",
                    ]
                ):
                    continue

                file_path = Path(root) / file
                relative = str(file_path.relative_to(search_dir))

                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")

                    # Search for query
                    if query_lower in content.lower():
                        # Find the line(s) with the match
                        lines = content.split("\n")
                        for i, line in enumerate(lines):
                            if query_lower in line.lower():
                                # Get context (2 lines before and after)
                                start = max(0, i - 2)
                                end = min(len(lines), i + 3)
                                preview = "\n".join(lines[start:end])

                                results.append(
                                    {
                                        "file": relative,
                                        "line": i + 1,
                                        "preview": preview[:500],
                                    }
                                )

                                if len(results) >= 20:
                                    return results
                                break  # Only first match per file

                except Exception as e:
                    logger.debug("Could not search file %s: %s", relative, e)

        return results

    async def analyze_task(self, task: TaskContext) -> dict:
        """Analyze what needs to be done for the task."""
        task.status = TaskStatus.ANALYZING

        analysis = {
            "task_id": task.task_id,
            "description": task.description,
            "files_to_examine": [],
            "suggested_approach": "",
            "estimated_edits": 0,
        }

        # If no files specified, try to find relevant ones
        if not task.relevant_files:
            # Search for files based on task description keywords
            keywords = self._extract_keywords(task.description)
            task.relevant_files = await self._search_files(keywords)

        analysis["files_to_examine"] = task.relevant_files
        analysis["suggested_approach"] = self._generate_approach(task.description)
        analysis["estimated_edits"] = len(task.relevant_files)

        return analysis

    async def apply_edit(self, task: TaskContext, edit: CodeEdit) -> tuple[bool, str]:
        """Apply a single edit to the codebase."""
        task.status = TaskStatus.EDITING

        # Apply the edit
        if edit.line_start and edit.line_end:
            success, message = self.editor.apply_line_edit(
                edit.file_path, edit.line_start, edit.line_end, edit.new_content
            )
        else:
            success, message = self.editor.apply_diff(edit.file_path, edit.old_content, edit.new_content)

        if success:
            task.edits_made.append(edit)
            logger.info("Applied edit to %s: %s", edit.file_path, edit.description)

        return success, message

    async def validate_changes(self, task: TaskContext) -> list[dict]:
        """Validate all changes made in the task."""
        task.status = TaskStatus.VALIDATING
        results = []

        for edit in task.edits_made:
            valid, message = self.validator.validate_file(edit.file_path)
            result = {
                "file": edit.file_path,
                "valid": valid,
                "message": message,
            }
            results.append(result)
            task.validation_results.append(result)

        return results

    async def run_task_loop(
        self,
        task: TaskContext,
        edit_generator: callable,
    ) -> TaskContext:
        """
        Run the agentic coding loop until complete.

        Args:
            task: The task context
            edit_generator: Async function that generates edits based on task state
                           Should return list[CodeEdit] or None when done

        Returns:
            Updated task context
        """
        logger.info("Starting agentic loop for task %s", task.task_id)

        while task.iteration_count < task.max_iterations:
            task.iteration_count += 1
            logger.info("Iteration %d/%d", task.iteration_count, task.max_iterations)

            try:
                # Generate next edits
                edits = await edit_generator(task)

                if not edits:
                    # No more edits needed
                    task.status = TaskStatus.COMPLETE
                    task.completed_at = datetime.now(UTC).isoformat()
                    logger.info(
                        "Task %s complete after %d iterations",
                        task.task_id,
                        task.iteration_count,
                    )
                    break

                # Apply edits
                for edit in edits:
                    success, message = await self.apply_edit(task, edit)
                    if not success:
                        logger.warning("Edit failed: %s", message)

                # Validate
                validation = await self.validate_changes(task)
                all_valid = all(r["valid"] for r in validation)

                if not all_valid:
                    # Validation failed - will retry next iteration
                    logger.warning("Validation failed, will retry")
                    continue

            except Exception as e:
                logger.error("Error in agentic loop: %s", e)
                task.error = str(e)
                task.status = TaskStatus.FAILED
                break

            # Small delay to prevent runaway loops
            await asyncio.sleep(0.1)

        if task.iteration_count >= task.max_iterations:
            task.status = TaskStatus.BLOCKED
            task.error = f"Max iterations ({task.max_iterations}) reached"

        return task

    def _extract_keywords(self, description: str) -> list[str]:
        """Extract keywords from task description."""
        # Remove common words
        stop_words = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "to",
            "in",
            "for",
            "of",
            "and",
            "or",
            "it",
        }
        words = re.findall(r"\b\w+\b", description.lower())
        return [w for w in words if w not in stop_words and len(w) > 2]

    async def _search_files(self, keywords: list[str], limit: int = 10) -> list[str]:
        """Search for relevant files based on keywords."""
        relevant = []

        for root, dirs, files in os.walk(self.working_dir):
            # Skip common non-code directories
            dirs[:] = [
                d
                for d in dirs
                if d
                not in {
                    "__pycache__",
                    "node_modules",
                    ".git",
                    ".venv",
                    "venv",
                    "dist",
                    "build",
                    ".next",
                    "coverage",
                }
            ]

            for file in files:
                if len(relevant) >= limit:
                    return relevant

                file_path = Path(root) / file
                relative = str(file_path.relative_to(self.working_dir))

                # Check filename
                if any(kw in file.lower() for kw in keywords):
                    relevant.append(relative)
                    continue

                # Check file content for code files
                if file_path.suffix in {".py", ".ts", ".tsx", ".js", ".jsx"}:
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="ignore")[:5000]
                        if any(kw in content.lower() for kw in keywords):
                            relevant.append(relative)
                    except Exception as e:
                        logger.debug("Could not read file %s: %s", relative, e)

        return relevant

    def _generate_approach(self, description: str) -> str:
        """Generate a suggested approach for the task."""
        description_lower = description.lower()

        if "fix" in description_lower or "bug" in description_lower:
            return "1. Identify the bug location\n2. Understand the root cause\n3. Implement fix\n4. Add test coverage"
        elif "add" in description_lower or "create" in description_lower:
            return "1. Identify where to add code\n2. Plan the implementation\n3. Write the code\n4. Test the changes"
        elif "refactor" in description_lower:
            return "1. Understand current implementation\n2. Plan refactoring steps\n3. Apply changes incrementally\n4. Validate behavior unchanged"
        else:
            return "1. Analyze requirements\n2. Find relevant code\n3. Make necessary changes\n4. Validate"


# ============================================================================
# LLM-POWERED EDIT GENERATOR
# ============================================================================

_EDIT_SYSTEM_PROMPT = """\
You are an expert autonomous coding agent. You receive a task description, \
relevant file contents, and the history of edits already applied. Your job is \
to produce the NEXT batch of surgical code edits needed to complete the task.

RULES:
1. Return a JSON array of edit objects. Each edit has:
   {"file_path": "...", "old_content": "exact text to find", "new_content": "replacement text", "description": "what this edit does"}
2. old_content must be an EXACT substring of the current file — copy it verbatim including whitespace.
3. Keep edits minimal and surgical — change only what is needed.
4. If the task is COMPLETE (no more edits needed), return an empty array: []
5. Do NOT wrap the JSON in markdown code fences. Return raw JSON only.
6. Maximum 5 edits per response to keep changes reviewable.
"""

_MAX_FILE_CHARS = 8000  # max chars per file to include in prompt


async def llm_edit_generator(task: "TaskContext") -> list["CodeEdit"] | None:
    """Generate code edits using the LLM.

    This is the ``edit_generator`` callable expected by
    ``AgenticCoder.run_task_loop()``.  It reads relevant files, builds a
    prompt with full context (task description, file contents, prior edits
    and validation results), calls the unified LLM service, and parses
    the response into ``CodeEdit`` objects.

    Returns ``None`` (or an empty list) when the LLM signals the task is
    complete, which causes the loop to stop.
    """
    try:
        from apps.backend.services.unified_llm import unified_llm
    except ImportError:
        logger.error("unified_llm not available — cannot generate edits")
        return None

    # ------------------------------------------------------------------
    # 1. Read relevant files for context
    # ------------------------------------------------------------------
    file_contexts: list[str] = []
    for rel_path in task.relevant_files[:6]:  # cap at 6 files
        abs_path = Path(task.working_directory) / rel_path
        try:
            content = abs_path.read_text(encoding="utf-8", errors="ignore")
            if len(content) > _MAX_FILE_CHARS:
                content = content[:_MAX_FILE_CHARS] + "\n... (truncated)"
            file_contexts.append(f"=== {rel_path} ===\n{content}")
        except Exception as e:
            file_contexts.append(f"=== {rel_path} === (could not read: {e})")

    # ------------------------------------------------------------------
    # 2. Build the user prompt
    # ------------------------------------------------------------------
    parts = [f"TASK: {task.description}"]

    if file_contexts:
        parts.append("RELEVANT FILES:\n" + "\n\n".join(file_contexts))

    if task.edits_made:
        edit_summary = []
        for edit in task.edits_made[-10:]:  # last 10 edits
            edit_summary.append(f"- {edit.file_path}: {edit.description}")
        parts.append("EDITS ALREADY APPLIED:\n" + "\n".join(edit_summary))

    if task.validation_results:
        failed = [r for r in task.validation_results if not r["valid"]]
        if failed:
            parts.append(
                "VALIDATION FAILURES (fix these):\n" + "\n".join(f"- {r['file']}: {r['message']}" for r in failed)
            )

    parts.append(
        f"Iteration {task.iteration_count}/{task.max_iterations}. "
        "Return the next JSON array of edits, or [] if the task is complete."
    )

    user_prompt = "\n\n".join(parts)

    # ------------------------------------------------------------------
    # 3. Call the LLM
    # ------------------------------------------------------------------
    try:
        response = await unified_llm.chat(
            [
                {"role": "system", "content": _EDIT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=2048,
            temperature=0.2,  # low temp for deterministic code edits
        )
    except Exception as e:
        logger.error("LLM call failed during edit generation: %s", e)
        raise

    # ------------------------------------------------------------------
    # 4. Parse LLM response into CodeEdit objects
    # ------------------------------------------------------------------
    raw = response.strip()

    # Strip markdown fences if the model wrapped them anyway
    if raw.startswith("```"):
        lines = raw.split("\n")
        # Remove first and last fence lines
        lines = [line for line in lines if not line.strip().startswith("```")]
        raw = "\n".join(lines).strip()

    try:
        edits_data = json.loads(raw)
    except json.JSONDecodeError:
        # Try to find a JSON array in the response
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            try:
                edits_data = json.loads(match.group())
            except json.JSONDecodeError:
                logger.warning("Could not parse LLM response as JSON: %s", raw[:200])
                return None
        else:
            logger.warning("No JSON array found in LLM response: %s", raw[:200])
            return None

    if not isinstance(edits_data, list):
        logger.warning("LLM returned non-list: %s", type(edits_data))
        return None

    if len(edits_data) == 0:
        # LLM signals task is complete
        return None

    edits: list[CodeEdit] = []
    for item in edits_data[:5]:  # cap at 5 edits
        if not isinstance(item, dict):
            continue
        fp = item.get("file_path", "")
        old = item.get("old_content", "")
        new = item.get("new_content", "")
        desc = item.get("description", "LLM-generated edit")
        if fp and old and new and old != new:
            edits.append(
                CodeEdit(
                    file_path=fp,
                    old_content=old,
                    new_content=new,
                    description=desc,
                )
            )

    return edits if edits else None


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

_agentic_coder: AgenticCoder | None = None


def get_agentic_coder(working_dir: str = None) -> AgenticCoder:
    """Get or create the global agentic coder instance."""
    global _agentic_coder
    if _agentic_coder is None or working_dir:
        _agentic_coder = AgenticCoder(working_dir or ".")
    return _agentic_coder
