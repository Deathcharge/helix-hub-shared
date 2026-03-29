"""
Collaborative Canvas Service

Provides real-time collaborative editing capabilities similar to ChatGPT Canvas.
Supports multiple users, rich text, code blocks, and version history.
"""

import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from loguru import logger


@dataclass
class CanvasComment:
    """Comment on a canvas"""

    id: str
    canvas_id: str
    user_id: str
    user_name: str
    text: str
    position: dict[str, int]  # {x, y}
    timestamp: str
    resolved: bool = False


@dataclass
class CanvasUser:
    """User currently editing a canvas"""

    user_id: str
    user_name: str
    color: str
    cursor_position: dict[str, int] | None = None
    last_active: str = None


class CollaborativeCanvas:
    """Collaborative canvas document"""

    def __init__(self, canvas_id: str, title: str, creator_id: str, creator_name: str):
        self.canvas_id = canvas_id
        self.title = title
        self.content = ""  # Rich text content (could be HTML, Markdown, or JSON)
        self.creator_id = creator_id
        self.creator_name = creator_name
        self.created_at = datetime.now(UTC).isoformat()
        self.updated_at = datetime.now(UTC).isoformat()
        self.version = 1
        self.history = []  # Version history
        self.comments: list[CanvasComment] = []
        self.active_users: dict[str, CanvasUser] = {}  # user_id -> CanvasUser
        self.settings = {"is_public": False, "allow_editing": True, "allow_comments": True}

        # Add initial version to history
        self._save_version_to_history()

    def _save_version_to_history(self):
        """Save current state to version history"""
        version_entry = {
            "version": self.version,
            "timestamp": datetime.now(UTC).isoformat(),
            "content": self.content,
            "user_id": self.creator_id,
            "user_name": self.creator_name,
            "change_summary": "Initial version",
        }
        self.history.append(version_entry)

        # Keep only last 50 versions
        if len(self.history) > 50:
            self.history = self.history[-50:]

    def update_content(self, new_content: str, user_id: str, user_name: str, change_summary: str = "Content update"):
        """Update canvas content"""
        self.content = new_content
        self.version += 1
        self.updated_at = datetime.now(UTC).isoformat()

        # Save to history
        version_entry = {
            "version": self.version,
            "timestamp": datetime.now(UTC).isoformat(),
            "content": new_content,
            "user_id": user_id,
            "user_name": user_name,
            "change_summary": change_summary,
        }
        self.history.append(version_entry)

        # Trim history
        if len(self.history) > 50:
            self.history = self.history[-50:]

    def add_comment(self, comment: CanvasComment):
        """Add a comment to the canvas"""
        self.comments.append(comment)
        self.updated_at = datetime.now(UTC).isoformat()

    def resolve_comment(self, comment_id: str):
        """Resolve a comment"""
        for comment in self.comments:
            if comment.id == comment_id:
                comment.resolved = True
                self.updated_at = datetime.now(UTC).isoformat()
                break

    def add_active_user(self, user: CanvasUser):
        """Add or update an active user"""
        self.active_users[user.user_id] = user
        user.last_active = datetime.now(UTC).isoformat()

    def remove_active_user(self, user_id: str):
        """Remove an active user"""
        if user_id in self.active_users:
            del self.active_users[user_id]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        return {
            "canvas_id": self.canvas_id,
            "title": self.title,
            "content": self.content,
            "creator_id": self.creator_id,
            "creator_name": self.creator_name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
            "history": self.history,
            "comments": [asdict(c) for c in self.comments],
            "active_users": {k: asdict(v) for k, v in self.active_users.items()},
            "settings": self.settings,
        }


class CanvasService:
    """Service for managing collaborative canvases"""

    def __init__(self):
        self.canvases: dict[str, CollaborativeCanvas] = {}
        self.canvas_shares: dict[str, list[str]] = {}  # canvas_id -> [user_ids with access]

    def create_canvas(
        self, title: str, creator_id: str, creator_name: str, initial_content: str = ""
    ) -> dict[str, Any]:
        """
        Create a new collaborative canvas.

        Args:
            title: Canvas title
            creator_id: ID of the creator
            creator_name: Name of the creator
            initial_content: Optional initial content

        Returns:
            Canvas information
        """
        try:
            canvas_id = str(uuid.uuid4())

            canvas = CollaborativeCanvas(canvas_id, title, creator_id, creator_name)

            if initial_content:
                canvas.content = initial_content

            self.canvases[canvas_id] = canvas
            self.canvas_shares[canvas_id] = [creator_id]

            logger.info("Created canvas: %s", canvas_id)

            return canvas.to_dict()

        except Exception as e:
            logger.error("Failed to create canvas: %s", e)
            raise

    def get_canvas(self, canvas_id: str) -> dict[str, Any] | None:
        """
        Get a canvas by ID.

        Args:
            canvas_id: Canvas ID

        Returns:
            Canvas information or None
        """
        canvas = self.canvases.get(canvas_id)
        if canvas:
            return canvas.to_dict()
        return None

    def update_canvas(
        self, canvas_id: str, new_content: str, user_id: str, user_name: str, change_summary: str = "Content update"
    ) -> dict[str, Any] | None:
        """
        Update canvas content.

        Args:
            canvas_id: Canvas ID
            new_content: New content
            user_id: User ID making the change
            user_name: User name
            change_summary: Description of the change

        Returns:
            Updated canvas information
        """
        canvas = self.canvases.get(canvas_id)
        if not canvas:
            return None

        canvas.update_content(new_content, user_id, user_name, change_summary)

        logger.info("Updated canvas: %s by %s", canvas_id, user_name)

        return canvas.to_dict()

    def delete_canvas(self, canvas_id: str) -> bool:
        """
        Delete a canvas.

        Args:
            canvas_id: Canvas ID

        Returns:
            True if deleted
        """
        if canvas_id in self.canvases:
            del self.canvases[canvas_id]
            if canvas_id in self.canvas_shares:
                del self.canvas_shares[canvas_id]

            logger.info("Deleted canvas: %s", canvas_id)
            return True

        return False

    def add_comment(
        self, canvas_id: str, user_id: str, user_name: str, text: str, position: dict[str, int]
    ) -> dict[str, Any] | None:
        """
        Add a comment to a canvas.

        Args:
            canvas_id: Canvas ID
            user_id: User ID
            user_name: User name
            text: Comment text
            position: Comment position {x, y}

        Returns:
        Comment information
        """
        canvas = self.canvases.get(canvas_id)
        if not canvas:
            return None

        comment = CanvasComment(
            id=str(uuid.uuid4()),
            canvas_id=canvas_id,
            user_id=user_id,
            user_name=user_name,
            text=text,
            position=position,
            timestamp=datetime.now(UTC).isoformat(),
        )

        canvas.add_comment(comment)

        logger.info("Added comment to canvas: %s", canvas_id)

        return asdict(comment)

    def resolve_comment(self, canvas_id: str, comment_id: str) -> bool:
        """
        Resolve a comment.

        Args:
            canvas_id: Canvas ID
            comment_id: Comment ID

        Returns:
            True if resolved
        """
        canvas = self.canvases.get(canvas_id)
        if not canvas:
            return False

        canvas.resolve_comment(comment_id)

        logger.info("Resolved comment %s on canvas: %s", comment_id, canvas_id)

        return True

    def get_version_history(self, canvas_id: str) -> list[dict[str, Any]]:
        """
        Get version history for a canvas.

        Args:
            canvas_id: Canvas ID

        Returns:
            List of version entries
        """
        canvas = self.canvases.get(canvas_id)
        if not canvas:
            return []

        return canvas.history

    def share_canvas(self, canvas_id: str, user_ids: list[str]) -> bool:
        """
        Share a canvas with users.

        Args:
            canvas_id: Canvas ID
            user_ids: List of user IDs to share with

        Returns:
            True if shared successfully
        """
        if canvas_id not in self.canvas_shares:
            return False

        self.canvas_shares[canvas_id].extend(user_ids)
        # Remove duplicates
        self.canvas_shares[canvas_id] = list(set(self.canvas_shares[canvas_id]))

        logger.info("Shared canvas %s with %s users", canvas_id, len(user_ids))

        return True

    def get_user_canvases(self, user_id: str) -> list[dict[str, Any]]:
        """
        Get all canvases accessible to a user.

        Args:
            user_id: User ID

        Returns:
            List of canvas information
        """
        user_canvases = []

        for canvas_id, shared_users in self.canvas_shares.items():
            if user_id in shared_users:
                canvas = self.canvases.get(canvas_id)
                if canvas:
                    user_canvases.append(canvas.to_dict())

        return user_canvases

    def join_canvas(self, canvas_id: str, user_id: str, user_name: str) -> dict[str, Any]:
        """
        User joins a canvas for editing.

        Args:
            canvas_id: Canvas ID
            user_id: User ID
            user_name: User name

        Returns:
            Canvas with active users
        """
        canvas = self.canvases.get(canvas_id)
        if not canvas:
            return None

        # Generate a color for the user
        colors = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7", "#DDA0DD"]
        color = colors[hash(user_id) % len(colors)]

        user = CanvasUser(user_id=user_id, user_name=user_name, color=color)

        canvas.add_active_user(user)

        logger.info("User %s joined canvas: %s", user_name, canvas_id)

        return canvas.to_dict()

    def leave_canvas(self, canvas_id: str, user_id: str) -> bool:
        """
        User leaves a canvas.

        Args:
            canvas_id: Canvas ID
            user_id: User ID

        Returns:
            True if left successfully
        """
        canvas = self.canvases.get(canvas_id)
        if not canvas:
            return False

        canvas.remove_active_user(user_id)

        logger.info("User %s left canvas: %s", user_id, canvas_id)

        return True

    def update_cursor_position(self, canvas_id: str, user_id: str, position: dict[str, int]) -> bool:
        """
        Update user's cursor position.

        Args:
            canvas_id: Canvas ID
            user_id: User ID
            position: Cursor position {x, y}

        Returns:
            True if updated
        """
        canvas = self.canvases.get(canvas_id)
        if not canvas:
            return False

        user = canvas.active_users.get(user_id)
        if user:
            user.cursor_position = position
            user.last_active = datetime.now(UTC).isoformat()
            return True

        return False

    def get_active_users(self, canvas_id: str) -> list[dict[str, Any]]:
        """
        Get active users for a canvas.

        Args:
            canvas_id: Canvas ID

        Returns:
            List of active users
        """
        canvas = self.canvases.get(canvas_id)
        if not canvas:
            return []

        return [asdict(u) for u in canvas.active_users.values()]


# Global canvas service instance
canvas_service = CanvasService()
