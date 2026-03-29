"""
Per-User GitHub API Service

Uses a user's stored OAuth access token to make authenticated GitHub API
calls on their behalf.  All responses are proxied through the Helix backend
so tokens are never exposed to the browser.
"""

import logging
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"

# Timeout: 10s connect, 30s read — prevents indefinite hangs on GitHub API calls
_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)

# Validation patterns to prevent path injection / SSRF
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9._-]{1,100}$")
_SAFE_PATH_RE = re.compile(r"^[a-zA-Z0-9._/\-]{0,500}$")
_SAFE_BRANCH_RE = re.compile(r"^[a-zA-Z0-9._/\-]{1,256}$")


def _validate_owner_repo(owner: str, repo: str) -> None:
    """Validate owner/repo names to prevent path traversal and SSRF."""
    if not _SAFE_NAME_RE.match(owner):
        raise ValueError(f"Invalid owner name: {owner!r}")
    if not _SAFE_NAME_RE.match(repo):
        raise ValueError(f"Invalid repo name: {repo!r}")


def _validate_path(path: str) -> None:
    """Validate file path to prevent traversal."""
    if ".." in path or path.startswith("/"):
        raise ValueError(f"Invalid path: {path!r}")
    if path and not _SAFE_PATH_RE.match(path):
        raise ValueError(f"Invalid path characters: {path!r}")


def _validate_branch(branch: str) -> None:
    """Validate branch name."""
    if not _SAFE_BRANCH_RE.match(branch):
        raise ValueError(f"Invalid branch name: {branch!r}")


class GitHubUserService:
    """Make GitHub API calls on behalf of a specific user."""

    def __init__(self, access_token: str):
        self._token = access_token
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    # ------------------------------------------------------------------
    # User info
    # ------------------------------------------------------------------

    async def get_user(self) -> dict[str, Any]:
        """Get authenticated user profile."""
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{GITHUB_API}/user", headers=self._headers)
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # Repositories
    # ------------------------------------------------------------------

    async def list_repos(
        self,
        sort: str = "updated",
        per_page: int = 30,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        """List authenticated user's repositories."""
        per_page = max(1, min(per_page, 100))
        page = max(1, min(page, 100))
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{GITHUB_API}/user/repos",
                headers=self._headers,
                params={
                    "sort": sort,
                    "per_page": per_page,
                    "page": page,
                    "affiliation": "owner,collaborator",
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        """Get a single repository."""
        _validate_owner_repo(owner, repo)
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # File browsing
    # ------------------------------------------------------------------

    async def get_contents(self, owner: str, repo: str, path: str = "", ref: str | None = None) -> Any:
        """Get file or directory contents."""
        _validate_owner_repo(owner, repo)
        _validate_path(path)
        params: dict[str, str] = {}
        if ref:
            _validate_branch(ref)
            params["ref"] = ref

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
                headers=self._headers,
                params=params,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_file_content(self, owner: str, repo: str, path: str, ref: str | None = None) -> dict[str, Any]:
        """Get a single file's content (decoded)."""
        import base64

        data = await self.get_contents(owner, repo, path, ref)
        if isinstance(data, list):
            raise ValueError(f"Path '{path}' is a directory, not a file")

        content = ""
        if data.get("encoding") == "base64" and data.get("content"):
            content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")

        return {
            "path": data.get("path", path),
            "name": data.get("name", ""),
            "sha": data.get("sha", ""),
            "size": data.get("size", 0),
            "content": content,
        }

    # ------------------------------------------------------------------
    # Branches
    # ------------------------------------------------------------------

    async def list_branches(self, owner: str, repo: str, per_page: int = 30) -> list[dict[str, Any]]:
        """List branches for a repository."""
        _validate_owner_repo(owner, repo)
        per_page = max(1, min(per_page, 100))
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}/branches",
                headers=self._headers,
                params={"per_page": per_page},
            )
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # Commits & file operations
    # ------------------------------------------------------------------

    async def create_or_update_file(
        self,
        owner: str,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: str | None = None,
        sha: str | None = None,
    ) -> dict[str, Any]:
        """Create or update a file via the GitHub Contents API."""
        import base64

        _validate_owner_repo(owner, repo)
        _validate_path(path)

        body: dict[str, Any] = {
            "message": message[:500],
            "content": base64.b64encode(content.encode()).decode(),
        }
        if branch:
            _validate_branch(branch)
            body["branch"] = branch
        if sha:
            body["sha"] = sha

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.put(
                f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}",
                headers=self._headers,
                json=body,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_commits(
        self,
        owner: str,
        repo: str,
        branch: str | None = None,
        per_page: int = 20,
    ) -> list[dict[str, Any]]:
        """List recent commits."""
        _validate_owner_repo(owner, repo)
        per_page = max(1, min(per_page, 100))
        params: dict[str, Any] = {"per_page": per_page}
        if branch:
            _validate_branch(branch)
            params["sha"] = branch

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}/commits",
                headers=self._headers,
                params=params,
            )
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # Pull Requests
    # ------------------------------------------------------------------

    async def list_pull_requests(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        per_page: int = 20,
    ) -> list[dict[str, Any]]:
        """List pull requests."""
        _validate_owner_repo(owner, repo)
        per_page = max(1, min(per_page, 100))
        if state not in ("open", "closed", "all"):
            state = "open"
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}/pulls",
                headers=self._headers,
                params={"state": state, "per_page": per_page},
            )
            resp.raise_for_status()
            return resp.json()

    async def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        head: str,
        base: str,
        body: str = "",
    ) -> dict[str, Any]:
        """Create a pull request."""
        _validate_owner_repo(owner, repo)
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{GITHUB_API}/repos/{owner}/{repo}/pulls",
                headers=self._headers,
                json={"title": title, "head": head, "base": base, "body": body},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_pull_request(self, owner: str, repo: str, pr_number: int) -> dict[str, Any]:
        """Get pull request metadata."""
        _validate_owner_repo(owner, repo)
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_pull_request_files(
        self, owner: str, repo: str, pr_number: int, per_page: int = 30
    ) -> list[dict[str, Any]]:
        """Get the list of files changed in a PR, including their patches (diffs)."""
        _validate_owner_repo(owner, repo)
        per_page = max(1, min(per_page, 100))
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/files",
                headers=self._headers,
                params={"per_page": per_page},
            )
            resp.raise_for_status()
            return resp.json()

    async def create_pull_request_review(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        body: str,
        event: str = "COMMENT",
    ) -> dict[str, Any]:
        """Post a review on a PR.

        event can be 'COMMENT', 'APPROVE', or 'REQUEST_CHANGES'.
        """
        _validate_owner_repo(owner, repo)
        if event not in ("COMMENT", "APPROVE", "REQUEST_CHANGES"):
            event = "COMMENT"
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
                headers=self._headers,
                json={"body": body, "event": event},
            )
            resp.raise_for_status()
            return resp.json()


def get_github_service_for_user(user: dict[str, Any]) -> "GitHubUserService | None":
    """
    Create a GitHubUserService for a user if they have a linked GitHub token.

    Returns None if the user has not connected GitHub.
    """
    token = user.get("github_access_token")
    if not token:
        return None
    return GitHubUserService(access_token=token)
