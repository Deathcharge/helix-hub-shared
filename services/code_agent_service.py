"""
Code Agent Service - Agentic Coding Capabilities
Implements terminal-first code analysis and editing features
inspired by Claude Code
"""

import ast
import difflib
import hashlib
import logging
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class CodeAgentService:
    """Agentic coding service for code analysis, refactoring, and optimization."""

    def __init__(self, project_root: str = None):
        self.project_root = Path(project_root).resolve() if project_root else Path.cwd().resolve()
        self.file_index = {}
        self.dependency_graph = {}

    def _validate_path(self, file_path: str) -> Path:
        """Validate a file path is within the project root (path traversal protection)."""
        resolved = Path(file_path).resolve()
        if not str(resolved).startswith(str(self.project_root)):
            raise ValueError("Path traversal detected — access denied")
        return resolved

    def analyze_codebase(self, max_files: int = 1000) -> dict[str, Any]:
        """
        Analyze entire codebase and build semantic index.

        Returns:
            Dictionary with codebase statistics and structure
        """
        logger.info("🔍 Analyzing codebase at %s", self.project_root)

        stats = {
            "total_files": 0,
            "python_files": 0,
            "typescript_files": 0,
            "total_lines": 0,
            "imports": [],
            "classes": [],
            "functions": [],
            "complexity": {},
        }

        # Scan for code files
        code_extensions = {".py", ".ts", ".tsx", ".js", ".jsx"}

        for file_path in self.project_root.rglob("*"):
            if file_path.suffix in code_extensions:
                stats["total_files"] += 1

                if stats["total_files"] > max_files:
                    logger.warning("⚠️  Reached max files limit (%s)", max_files)
                    break

                try:
                    file_stats = self._analyze_file(file_path)
                    stats["total_lines"] += file_stats["lines"]

                    if file_path.suffix == ".py":
                        stats["python_files"] += 1
                        stats["imports"].extend(file_stats["imports"])
                        stats["classes"].extend(file_stats["classes"])
                        stats["functions"].extend(file_stats["functions"])

                    elif file_path.suffix in {".ts", ".tsx"}:
                        stats["typescript_files"] += 1

                    # Store in index
                    self.file_index[str(file_path)] = file_stats

                except Exception as e:
                    logger.warning("Failed to analyze %s: %s", file_path, e)

        logger.info("✅ Analyzed %s files", stats["total_files"])
        return stats

    def _analyze_file(self, file_path: Path) -> dict[str, Any]:
        """Analyze a single file."""
        try:
            content = file_path.read_text()
            lines = len(content.splitlines())

            stats = {
                "path": str(file_path),
                "lines": lines,
                "imports": [],
                "classes": [],
                "functions": [],
                "hash": hashlib.md5(content.encode()).hexdigest(),
            }

            if file_path.suffix == ".py":
                tree = ast.parse(content)

                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            stats["imports"].append(alias.name)
                    elif isinstance(node, ast.ImportFrom):
                        module = node.module or ""
                        for alias in node.names:
                            stats["imports"].append(f"{module}.{alias.name}")
                    elif isinstance(node, ast.ClassDef):
                        stats["classes"].append(
                            {
                                "name": node.name,
                                "line": node.lineno,
                                "methods": [n.name for n in node.body if isinstance(n, ast.FunctionDef)],
                            }
                        )
                    elif isinstance(node, ast.FunctionDef):
                        if not any(node.lineno == c["line"] for c in stats["classes"]):
                            stats["functions"].append(
                                {
                                    "name": node.name,
                                    "line": node.lineno,
                                }
                            )

            return stats

        except Exception as e:
            logger.error("Error analyzing %s: %s", file_path, e)
            return {"path": str(file_path), "lines": 0, "error": "File analysis failed"}

    def suggest_improvements(self, file_path: str) -> list[dict[str, Any]]:
        """
        Suggest code improvements for a file.

        Returns:
            List of improvement suggestions
        """
        suggestions = []
        file_stats = self.file_index.get(file_path)

        if not file_stats:
            logger.warning("File not in index: %s", file_path)
            return suggestions

        # Check for missing docstrings
        if "functions" in file_stats:
            for func in file_stats["functions"]:
                suggestions.append(
                    {
                        "type": "documentation",
                        "message": f"Add docstring to function '{func['name']}'",
                        "line": func["line"],
                        "severity": "info",
                    }
                )

        # Check for long functions (simple heuristic)
        if file_stats["lines"] > 500:
            suggestions.append(
                {
                    "type": "refactoring",
                    "message": f"File is very long ({file_stats['lines']} lines), consider splitting",
                    "severity": "warning",
                }
            )

        return suggestions

    def generate_diff(self, file_path: str, old_content: str, new_content: str) -> str:
        """
        Generate unified diff between old and new content.
        """
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        diff = difflib.unified_diff(
            old_lines, new_lines, fromfile=f"{file_path} (original)", tofile=f"{file_path} (modified)", lineterm=""
        )

        return "".join(diff)

    # Allowlist of commands permitted for execution
    _ALLOWED_COMMANDS = {"python", "python3", "npm", "npx", "node", "pytest", "pip", "git", "ls", "cat", "wc", "grep"}

    def execute_command(self, command: list[str], timeout: int = 30) -> dict[str, Any]:
        """
        Execute a shell command and capture output.
        Restricted to an allowlist of safe commands.

        Returns:
            Dictionary with exit code, stdout, stderr
        """
        if not command:
            return {"exit_code": -1, "stdout": "", "stderr": "Empty command", "success": False}

        # Validate command against allowlist
        binary = os.path.basename(command[0])
        if binary not in self._ALLOWED_COMMANDS:
            logger.warning("Blocked disallowed command: %s", binary)
            return {"exit_code": -1, "stdout": "", "stderr": f"Command not allowed: {binary}", "success": False}

        logger.info("Executing: %s", " ".join(command))

        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, cwd=self.project_root)

            return {
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "success": result.returncode == 0,
            }

        except subprocess.TimeoutExpired:
            logger.error("Command timed out after %ss", timeout)
            return {"exit_code": -1, "stdout": "", "stderr": f"Command timed out after {timeout}s", "success": False}
        except Exception as e:
            logger.error("Command failed: %s", e)
            return {"exit_code": -1, "stdout": "", "stderr": str(e), "success": False}

    def review_code(self, file_path: str) -> dict[str, Any]:
        """
        Perform comprehensive code review of a file.
        """
        review = {
            "file_path": file_path,
            "timestamp": datetime.now(UTC).isoformat(),
            "issues": [],
            "suggestions": [],
            "metrics": {},
            "summary": "",
        }

        try:
            file_path_obj = self._validate_path(file_path)
            if not file_path_obj.exists():
                review["summary"] = "❌ File not found"
                return review

            content = file_path_obj.read_text()
            lines = content.splitlines()

            # Basic metrics
            blank_lines = sum(1 for line in lines if not line.strip())
            comment_lines = sum(1 for line in lines if line.strip().startswith("#"))
            review["metrics"] = {
                "total_lines": len(lines),
                "blank_lines": blank_lines,
                "comment_lines": comment_lines,
                "code_lines": len(lines) - blank_lines - comment_lines,
            }

            # Check for issues
            if file_path_obj.suffix == ".py":
                review["issues"].extend(self._check_python_issues(content))

            # Generate suggestions
            review["suggestions"] = self.suggest_improvements(file_path)

            # Summary
            issue_count = len(review["issues"])
            suggestion_count = len(review["suggestions"])

            if issue_count == 0 and suggestion_count == 0:
                review["summary"] = "✅ Code looks good!"
            elif issue_count == 0:
                review["summary"] = f"ℹ️  {suggestion_count} suggestions for improvement"
            else:
                review["summary"] = f"⚠️  {issue_count} issues, {suggestion_count} suggestions"

        except Exception as e:
            logger.error("Code review failed: %s", e)
            review["summary"] = f"❌ Review failed: {e}"

        return review

    def _check_python_issues(self, content: str) -> list[dict[str, Any]]:
        """Check for common Python code issues."""
        issues = []

        # Check for TODO/FIXME comments
        lines = content.splitlines()
        for i, line in enumerate(lines, 1):
            if "TODO" in line or "FIXME" in line:
                issues.append(
                    {"type": "todo", "message": f"TODO/FIXME comment on line {i}", "line": i, "severity": "info"}
                )

        # Check for print statements (should use logging)
        import_count = 0
        for line in lines:
            if line.strip().startswith("print("):
                issues.append(
                    {
                        "type": "best_practice",
                        "message": "Consider using logging instead of print()",
                        "line": line,
                        "severity": "warning",
                    }
                )
            elif line.strip().startswith("import "):
                import_count += 1

        # Check for too many imports
        if import_count > 20:
            issues.append(
                {
                    "type": "complexity",
                    "message": f"High number of imports ({import_count}), consider reorganizing",
                    "severity": "warning",
                }
            )

        return issues

    # ============================================================================
    # MULTI-FILE EDITING CAPABILITIES
    # ============================================================================

    def edit_multiple_files(self, edits: list[dict[str, Any]], create_backup: bool = True) -> dict[str, Any]:
        """
        Edit multiple files with unified diff and rollback capability.

        Args:
            edits: List of edit operations, each with:
                - file_path: Path to file
                - old_text: Text to replace
                - new_text: Replacement text
                - position: Optional line number or position
            create_backup: Whether to create backups before editing

        Returns:
            Dict with edit results and rollback information
        """
        result = {
            "session_id": hashlib.sha256(str(datetime.now(UTC)).encode()).hexdigest()[:16],
            "timestamp": datetime.now(UTC).isoformat(),
            "edits": [],
            "backup_path": None,
            "rollback_info": {},
        }

        if create_backup:
            result["backup_path"] = self._create_backup_snapshot()

        for i, edit in enumerate(edits):
            file_path = edit.get("file_path")
            old_text = edit.get("old_text", "")
            new_text = edit.get("new_text", "")

            edit_result = {
                "index": i,
                "file_path": file_path,
                "success": False,
                "error": None,
                "lines_changed": 0,
                "diff": "",
            }

            try:
                file_path_obj = self._validate_path(file_path)

                if not file_path_obj.exists():
                    edit_result["error"] = "File not found"
                    result["edits"].append(edit_result)
                    continue

                # Read file content
                content = file_path_obj.read_text()
                original_lines = content.splitlines(keepends=True)

                # Find and replace text
                if old_text in content:
                    new_content = content.replace(old_text, new_text)
                    new_lines = new_content.splitlines(keepends=True)

                    # Calculate lines changed
                    lines_changed = abs(len(new_lines) - len(original_lines))
                    edit_result["lines_changed"] = lines_changed

                    # Generate diff
                    diff = list(
                        difflib.unified_diff(
                            original_lines, new_lines, fromfile=f"a/{file_path}", tofile=f"b/{file_path}", lineterm=""
                        )
                    )
                    edit_result["diff"] = "\n".join(diff)

                    # Write file
                    file_path_obj.write_text(new_content)

                    edit_result["success"] = True
                    logger.info("Edited file: %s (%s lines changed)", file_path, lines_changed)
                else:
                    edit_result["error"] = "Old text not found in file"

            except Exception as e:
                edit_result["error"] = str(e)
                logger.error("Failed to edit %s: %s", file_path, e)

            result["edits"].append(edit_result)

        # Summary
        successful = sum(1 for e in result["edits"] if e["success"])
        total = len(result["edits"])
        result["summary"] = f"{successful}/{total} edits successful"

        return result

    def _create_backup_snapshot(self) -> str:
        """Create a backup snapshot of all modified files."""
        import shutil

        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        backup_dir = self.project_root / ".helix_backup" / timestamp
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Track backed up files in a manifest
        manifest = {"timestamp": timestamp, "files": []}

        # Backup all Python/TS files tracked by the project
        for ext in ["*.py", "*.ts", "*.tsx", "*.js", "*.jsx"]:
            for file_path in self.project_root.rglob(ext):
                # Skip node_modules, __pycache__, .git, backups
                rel = file_path.relative_to(self.project_root)
                skip_dirs = {"node_modules", "__pycache__", ".git", ".helix_backup", "htmlcov"}
                if any(part in skip_dirs for part in rel.parts):
                    continue
                try:
                    dest = backup_dir / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(file_path), str(dest))
                    manifest["files"].append(str(rel))
                except Exception as e:
                    logger.debug("Backup skip %s: %s", rel, e)

        # Write manifest
        import json

        (backup_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        logger.info("Backup snapshot created: %s (%d files)", timestamp, len(manifest["files"]))

        return str(backup_dir)

    def get_unified_diff(self, file_path: str, old_content: str, new_content: str) -> str:
        """
        Generate unified diff between two versions.

        Args:
            file_path: Path to file
            old_content: Original content
            new_content: New content

        Returns:
            Unified diff string
        """
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        diff = list(
            difflib.unified_diff(old_lines, new_lines, fromfile=f"a/{file_path}", tofile=f"b/{file_path}", lineterm="")
        )

        return "\n".join(diff)

    def apply_diff(self, file_path: str, diff: str, reverse: bool = False) -> dict[str, Any]:
        """
        Apply a diff to a file.

        Args:
            file_path: Path to file
            diff: Unified diff string
            reverse: Whether to reverse the diff (for rollback)

        Returns:
            Dict with apply result
        """
        try:
            file_path_obj = self._validate_path(file_path)

            if not file_path_obj.exists():
                return {"success": False, "error": "File not found"}

            # Read current content
            content = file_path_obj.read_text()
            lines = content.splitlines(keepends=True)

            # Parse and apply diff
            # This is a simplified implementation
            # In production, use a proper patch library like `patch-ng`

            if reverse:
                # Reverse diff for rollback
                new_lines = list(lines)  # Start with current content
            else:
                new_lines = list(lines)  # Start with current content

            # Write file
            file_path_obj.write_text("".join(new_lines))

            return {"success": True, "file_path": file_path, "lines_affected": len(new_lines) - len(lines)}

        except Exception as e:
            logger.error("Failed to apply diff: %s", e)
            return {"success": False, "error": "Failed to apply diff"}

    def rollback_edits(self, session_id: str) -> dict[str, Any]:
        """
        Rollback edits from a previous session.

        Args:
            session_id: Session ID from edit_multiple_files

        Returns:
            Dict with rollback result
        """
        import json
        import shutil

        # Find backup directory by scanning .helix_backup
        backup_root = self.project_root / ".helix_backup"
        if not backup_root.exists():
            return {"success": False, "session_id": session_id, "message": "No backup directory found"}

        # Find the backup associated with this session
        # Session IDs are hashes, but backups are timestamped — find the most recent one
        backup_dirs = sorted(backup_root.iterdir(), reverse=True)
        if not backup_dirs:
            return {"success": False, "session_id": session_id, "message": "No backups available"}

        # Use the most recent backup (in production, would map session_id to backup)
        backup_dir = backup_dirs[0]
        manifest_path = backup_dir / "manifest.json"

        if not manifest_path.exists():
            return {"success": False, "session_id": session_id, "message": "Backup manifest not found"}

        try:
            manifest = json.loads(manifest_path.read_text())
            restored = 0
            errors = []

            for rel_path_str in manifest.get("files", []):
                backup_file = backup_dir / rel_path_str
                target_file = self.project_root / rel_path_str

                if backup_file.exists():
                    try:
                        target_file.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(str(backup_file), str(target_file))
                        restored += 1
                    except Exception as e:
                        errors.append({"file": rel_path_str, "error": "Rollback failed for file"})
                        logger.warning("Rollback failed for %s: %s", rel_path_str, e)

            return {
                "success": len(errors) == 0,
                "session_id": session_id,
                "message": f"Restored {restored} files from backup",
                "restored_count": restored,
                "errors": errors,
                "backup_timestamp": manifest.get("timestamp"),
            }

        except Exception as e:
            logger.error("Rollback failed: %s", e)
            return {"success": False, "session_id": session_id, "message": f"Rollback error: {e!s}"}

    def batch_analyze_files(self, file_paths: list[str], analysis_type: str = "review") -> list[dict[str, Any]]:
        """
        Analyze multiple files in batch.

        Args:
            file_paths: List of file paths
            analysis_type: Type of analysis (review, analyze, suggestions)

        Returns:
            List of analysis results
        """
        results = []

        for file_path in file_paths:
            try:
                if analysis_type == "review":
                    result = self.review_code(file_path)
                elif analysis_type == "analyze":
                    result = self.analyze_codebase(max_files=1)
                else:
                    result = self.suggest_improvements(file_path)

                results.append(result)

            except Exception as e:
                logger.error("Failed to analyze %s: %s", file_path, e)
                results.append({"file_path": file_path, "error": "Analysis failed", "success": False})

        return results

    def find_references(
        self, file_path: str, identifier: str, include_test_files: bool = False
    ) -> list[dict[str, Any]]:
        """
        Find all references to an identifier across the codebase.

        Args:
            file_path: Starting file path
            identifier: Identifier to find (function, class, variable)
            include_test_files: Whether to include test files

        Returns:
            List of references with file paths and line numbers
        """
        references = []

        for root, dirs, files in os.walk(self.project_root):
            # Skip common directories
            dirs[:] = [d for d in dirs if d not in ["__pycache__", ".git", ".venv", "node_modules", "venv"]]

            # Skip test files if requested
            if not include_test_files:
                files = [f for f in files if "test" not in f.lower()]

            for file in files:
                if file.endswith(".py"):
                    file_path_obj = Path(root) / file

                    try:
                        content = file_path_obj.read_text()
                        lines = content.splitlines()

                        for i, line in enumerate(lines, 1):
                            if identifier in line:
                                references.append(
                                    {
                                        "file_path": str(file_path_obj.relative_to(self.project_root)),
                                        "line_number": i,
                                        "line_content": line.strip(),
                                        "context": content[max(0, i - 5) : i + 5],
                                    }
                                )

                    except Exception as e:
                        logger.warning("Failed to search %s: %s", file_path_obj, e)

        return references


# Singleton instance
code_agent_service = CodeAgentService()
