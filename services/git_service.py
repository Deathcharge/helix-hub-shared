"""
Git Service

Provides Git operations including automatic commit generation,
branch management, and pull request creation.
"""

import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger


class GitService:
    """Git operations service"""

    def __init__(self, project_root: str | None = None):
        self.project_root = Path(project_root) if project_root else Path.cwd()

    @staticmethod
    def _sanitize_ref(ref: str) -> str:
        """Sanitize a git ref (branch/tag name) to prevent flag injection.

        Git interprets arguments starting with '-' as flags, so a malicious
        branch name like '--exec=...' could inject options. This prefixes
        such refs with '--' separator or rejects obviously invalid ones.
        """
        ref = ref.strip()
        if not ref or "\x00" in ref:
            raise ValueError("Invalid git ref")
        # Reject refs that look like flags
        if ref.startswith("-"):
            raise ValueError("Invalid git ref: must not start with '-'")
        return ref

    def _run_git_command(self, args: list[str], capture_output: bool = True) -> dict[str, Any]:
        """
        Run a git command.

        Args:
            args: Git command arguments
            capture_output: Whether to capture output

        Returns:
            Dict with command result
        """
        try:
            cmd = ["git"] + args
            result = subprocess.run(cmd, cwd=self.project_root, capture_output=capture_output, text=True, timeout=30)

            return {
                "success": result.returncode == 0,
                "exit_code": result.returncode,
                "stdout": result.stdout if capture_output else "",
                "stderr": result.stderr if capture_output else "",
            }

        except subprocess.TimeoutExpired:
            logger.error("Git command timed out: %s", " ".join(args))
            return {"success": False, "exit_code": -1, "stdout": "", "stderr": "Command timed out"}
        except (OSError, ValueError) as e:
            logger.debug("Git command execution error: %s", e)
            return {"success": False, "exit_code": -1, "stdout": "", "stderr": "Git command failed"}
        except Exception as e:
            logger.error("Git command failed: %s", e)
            return {"success": False, "exit_code": -1, "stdout": "", "stderr": "Git command failed"}

    def get_status(self) -> dict[str, Any]:
        """
        Get Git repository status.

        Returns:
            Dict with repository status
        """
        try:
            # Check if we're in a git repository
            check_git = self._run_git_command(["rev-parse", "--git-dir"])
            if not check_git["success"]:
                return {"is_git_repo": False, "error": "Not a Git repository"}

            # Get branch
            branch_result = self._run_git_command(["branch", "--show-current"])
            current_branch = branch_result["stdout"].strip() if branch_result["success"] else "unknown"

            # Get status
            status_result = self._run_git_command(["status", "--porcelain"])
            status_lines = status_result["stdout"].splitlines() if status_result["success"] else []

            # Parse status
            staged = []
            modified = []
            untracked = []

            for line in status_lines:
                if not line:
                    continue

                status_code = line[:2]
                file_path = line[3:]

                if status_code[0] in "MADRC":
                    staged.append(file_path)
                if status_code[1] in "MADRC":
                    modified.append(file_path)
                if status_code == "??":
                    untracked.append(file_path)

            # Get ahead/behind
            ahead = 0
            behind = 0
            if current_branch != "unknown":
                ahead_behind = self._run_git_command(["rev-list", "--count", "--left-right", "@{u}...HEAD"])
                if ahead_behind["success"]:
                    parts = ahead_behind["stdout"].strip().split("\t")
                    if len(parts) == 2:
                        behind = int(parts[0])
                        ahead = int(parts[1])

            return {
                "is_git_repo": True,
                "current_branch": current_branch,
                "staged_files": staged,
                "modified_files": modified,
                "untracked_files": untracked,
                "ahead": ahead,
                "behind": behind,
                "has_changes": bool(staged or modified or untracked),
            }

        except Exception as e:
            logger.error("Failed to get git status: %s", e)
            return {"is_git_repo": False, "error": "Failed to get repository status"}

    def create_commit(self, message: str, files: list[str] | None = None, amend: bool = False) -> dict[str, Any]:
        """
        Create a Git commit.

        Args:
            message: Commit message
            files: Optional list of files to stage
            amend: Whether to amend previous commit

        Returns:
            Dict with commit result
        """
        try:
            # Stage files if specified
            if files:
                for file_path in files:
                    result = self._run_git_command(["add", file_path])
                    if not result["success"]:
                        logger.warning("Failed to stage %s: %s", file_path, result["stderr"])

            # Create commit
            commit_args = ["commit", "-m", message]
            if amend:
                commit_args.append("--amend")

            result = self._run_git_command(commit_args)

            if result["success"]:
                # Get commit hash
                hash_result = self._run_git_command(["rev-parse", "HEAD"])
                commit_hash = hash_result["stdout"].strip() if hash_result["success"] else "unknown"

                return {
                    "success": True,
                    "commit_hash": commit_hash,
                    "message": message,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            else:
                return {"success": False, "error": result["stderr"]}

        except Exception as e:
            logger.error("Failed to create commit: %s", e)
            return {"success": False, "error": "Failed to create commit"}

    def suggest_commit_message(self) -> str:
        """
        Suggest a commit message based on staged changes.

        Returns:
            Suggested commit message
        """
        try:
            # Get diff of staged changes
            diff_result = self._run_git_command(["diff", "--staged"])
            if not diff_result["success"]:
                return "Update files"

            # Analyze changes
            added_files = []
            modified_files = []
            deleted_files = []

            # Get list of staged files
            status_result = self._run_git_command(["diff", "--staged", "--name-status"])
            if status_result["success"]:
                for line in status_result["stdout"].splitlines():
                    if line:
                        status_code = line[0]
                        file_path = line[2:]

                        if status_code == "A":
                            added_files.append(file_path)
                        elif status_code == "M":
                            modified_files.append(file_path)
                        elif status_code == "D":
                            deleted_files.append(file_path)

            # Generate message
            parts = []

            if added_files:
                if len(added_files) == 1:
                    parts.append(f"Add {Path(added_files[0]).name}")
                else:
                    parts.append(f"Add {len(added_files)} files")

            if modified_files:
                if len(modified_files) == 1:
                    parts.append(f"Update {Path(modified_files[0]).name}")
                else:
                    parts.append(f"Update {len(modified_files)} files")

            if deleted_files:
                if len(deleted_files) == 1:
                    parts.append(f"Remove {Path(deleted_files[0]).name}")
                else:
                    parts.append(f"Remove {len(deleted_files)} files")

            if parts:
                message = ", ".join(parts)
            else:
                message = "Update files"

            return message

        except Exception as e:
            logger.error("Failed to suggest commit message: %s", e)
            return "Update files"

    def create_branch(
        self, branch_name: str, checkout: bool = True, base_branch: str | None = None
    ) -> dict[str, Any]:
        """
        Create a new branch.

        Args:
            branch_name: Name of the new branch
            checkout: Whether to checkout the new branch
            base_branch: Optional base branch to create from

        Returns:
            Dict with branch creation result
        """
        try:
            branch_name = self._sanitize_ref(branch_name)
            args = ["branch"]
            if checkout:
                args = ["checkout", "-b"]
            args.append(branch_name)

            if base_branch:
                base_branch = self._sanitize_ref(base_branch)
                args.extend(["--track", base_branch])

            result = self._run_git_command(args)

            if result["success"]:
                return {"success": True, "branch_name": branch_name, "checkout": checkout}
            else:
                return {"success": False, "error": result["stderr"]}

        except Exception as e:
            logger.error("Failed to create branch: %s", e)
            return {"success": False, "error": "Failed to create branch"}

    def get_log(self, limit: int = 10, branch: str | None = None) -> list[dict[str, Any]]:
        """
        Get commit history.

        Args:
            limit: Number of commits to return
            branch: Optional branch to get history from

        Returns:
            List of commits
        """
        try:
            args = ["log", "--pretty=format:%H|%an|%ae|%ad|%s", "--date=iso"]
            if branch:
                args.append(self._sanitize_ref(branch))
            args.extend(["-n", str(limit)])

            result = self._run_git_command(args)

            if not result["success"]:
                return []

            commits = []
            for line in result["stdout"].splitlines():
                if not line:
                    continue

                parts = line.split("|", 4)
                if len(parts) == 5:
                    commits.append(
                        {"hash": parts[0], "author": parts[1], "email": parts[2], "date": parts[3], "message": parts[4]}
                    )

            return commits

        except Exception as e:
            logger.error("Failed to get git log: %s", e)
            return []

    def create_pull_request(self, title: str, body: str, head: str, base: str = "main") -> dict[str, Any]:
        """
        Create a pull request (requires GitHub CLI).

        Args:
            title: PR title
            body: PR description
            head: Branch to merge from
            base: Branch to merge to

        Returns:
            Dict with PR creation result
        """
        try:
            # Check if gh CLI is available
            if not shutil.which("gh"):
                return {"success": False, "error": "GitHub CLI (gh) not installed"}

            # Create PR using gh CLI
            cmd = ["gh", "pr", "create", "--title", title, "--body", body, "--head", head, "--base", base]

            result = subprocess.run(cmd, cwd=self.project_root, capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                return {"success": True, "url": result.stdout.strip(), "title": title, "head": head, "base": base}
            else:
                return {"success": False, "error": result.stderr}

        except Exception as e:
            logger.error("Failed to create pull request: %s", e)
            return {"success": False, "error": "Failed to create pull request"}

    def merge_branch(self, source_branch: str, target_branch: str, strategy: str = "merge") -> dict[str, Any]:
        """
        Merge a branch into another.

        Args:
            source_branch: Branch to merge from
            target_branch: Branch to merge to
            strategy: Merge strategy (merge, rebase, squash)

        Returns:
            Dict with merge result
        """
        try:
            # Checkout target branch
            checkout_result = self._run_git_command(["checkout", target_branch])
            if not checkout_result["success"]:
                return {"success": False, "error": f"Failed to checkout {target_branch}"}

            # Perform merge
            if strategy == "merge":
                merge_result = self._run_git_command(["merge", source_branch])
            elif strategy == "rebase":
                merge_result = self._run_git_command(["rebase", source_branch])
            elif strategy == "squash":
                merge_result = self._run_git_command(["merge", "--squash", source_branch])
                if merge_result["success"]:
                    commit_result = self._run_git_command(
                        ["commit", "-m", f"Merge {source_branch} into {target_branch}"]
                    )
                    merge_result = commit_result
            else:
                return {"success": False, "error": f"Unknown merge strategy: {strategy}"}

            if merge_result["success"]:
                return {
                    "success": True,
                    "source_branch": source_branch,
                    "target_branch": target_branch,
                    "strategy": strategy,
                }
            else:
                return {"success": False, "error": merge_result["stderr"]}

        except Exception as e:
            logger.error("Failed to merge branch: %s", e)
            return {"success": False, "error": "Failed to merge branch"}


# Global git service instance
git_service = GitService()
