"""
Knowledge Base Service

Business logic for knowledge base operations with database persistence.
Replaces the in-memory fallback with proper DB/Redis backing.

Copyright (c) 2026 Helix Collective. All Rights Reserved.
"""

import json
import logging
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.backend.models.knowledge_base import (
    KBArticleModel,
    KBCategoryModel,
    KBFavoriteModel,
    KBViewHistoryModel,
)

logger = logging.getLogger(__name__)

# Cache key prefixes
CACHE_PREFIX_ARTICLE = "kb:article:"
CACHE_PREFIX_FAVORITES = "kb:favorites:"
CACHE_PREFIX_VIEWS = "kb:views:"
CACHE_TTL = 300  # 5 minutes


class KnowledgeBaseService:
    """
    Service for knowledge base operations with database persistence.

    Features:
    - Database-backed article storage
    - Redis caching for performance
    - View tracking and analytics
    - User favorites management
    """

    def __init__(self, db: AsyncSession, redis: Any | None = None):
        """
        Initialize the KB service.

        Args:
            db: SQLAlchemy async session for database operations
            redis: Optional Redis client for caching
        """
        self._db = db
        self._redis = redis
        self._cache_ttl = CACHE_TTL

    # ========================================================================
    # ARTICLE OPERATIONS
    # ========================================================================

    async def get_article(
        self,
        article_id: str,
        user_id: str | None = None,
        track_view: bool = True,
    ) -> dict[str, Any] | None:
        """
        Get an article by ID with view tracking.

        Args:
            article_id: Article ID or slug
            user_id: Optional user ID for view tracking and favorites
            track_view: Whether to increment view count

        Returns:
            Article dict or None if not found
        """
        # Try cache first
        if self._redis:
            try:
                cached = await self._redis.get(f"{CACHE_PREFIX_ARTICLE}{article_id}")
                if cached:
                    article = json.loads(cached)
                    # Still check favorites for user
                    if user_id:
                        article["is_favorite"] = await self._is_favorite(user_id, article_id)
                    return article
            except (ConnectionError, TimeoutError) as e:
                logger.debug("Redis connection error for article cache %s: %s", article_id, e)

        # Query database
        query = select(KBArticleModel).where(
            (KBArticleModel.id == article_id) | (KBArticleModel.slug == article_id),
            KBArticleModel.is_published.is_(True),
        )
        result = await self._db.execute(query)
        article = result.scalar_one_or_none()

        if not article:
            return None

        # Track view
        if track_view:
            await self._increment_view_count(article.id, user_id)

        # Check if favorited
        is_favorite = False
        if user_id:
            is_favorite = await self._is_favorite(user_id, article.id)

        article_dict = self._article_to_dict(article)
        article_dict["is_favorite"] = is_favorite

        # Cache the result
        if self._redis:
            try:
                await self._redis.setex(
                    f"{CACHE_PREFIX_ARTICLE}{article_id}",
                    self._cache_ttl,
                    json.dumps(article_dict, default=str),
                )
            except (ConnectionError, TimeoutError) as e:
                logger.debug("Redis connection error caching article %s: %s", article_id, e)

        return article_dict

    async def list_articles(
        self,
        category: str | None = None,
        user_id: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """
        List articles with optional filtering.

        Args:
            category: Optional category filter
            user_id: Optional user ID for favorites
            page: Page number (1-indexed)
            page_size: Items per page

        Returns:
            Dict with articles, total, and categories
        """
        # Build query
        query = select(KBArticleModel).where(KBArticleModel.is_published.is_(True))

        if category:
            query = query.where(KBArticleModel.category == category)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self._db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply pagination
        query = query.order_by(KBArticleModel.views.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self._db.execute(query)
        articles = result.scalars().all()

        # Get user favorites if user provided
        user_favorites = set()
        if user_id:
            user_favorites = await self._get_user_favorite_ids(user_id)

        # Convert to dicts
        article_dicts = []
        for article in articles:
            article_dict = self._article_to_dict(article)
            article_dict["is_favorite"] = article.id in user_favorites
            article_dicts.append(article_dict)

        # Get categories
        categories = await self._get_categories()

        return {
            "pages": article_dicts,
            "total": total,
            "categories": categories,
            "page": page,
            "page_size": page_size,
        }

    async def search_articles(
        self,
        query: str,
        category: str | None = None,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Search articles by query string.

        Args:
            query: Search query
            category: Optional category filter
            user_id: Optional user ID for favorites

        Returns:
            List of matching articles
        """
        # Build search query using PostgreSQL full-text search or LIKE fallback
        # Escape LIKE wildcards to prevent injection of % and _ characters
        sanitized = query.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        search_term = f"%{sanitized}%"

        sql_query = select(KBArticleModel).where(
            KBArticleModel.is_published.is_(True),
            (
                func.lower(KBArticleModel.title).like(search_term)
                | func.lower(KBArticleModel.description).like(search_term)
                | func.lower(KBArticleModel.content).like(search_term)
            ),
        )

        if category:
            sql_query = sql_query.where(KBArticleModel.category == category)

        # Sort by relevance (title matches first)
        sql_query = sql_query.order_by(KBArticleModel.views.desc())

        result = await self._db.execute(sql_query)
        articles = result.scalars().all()

        # Get user favorites
        user_favorites = set()
        if user_id:
            user_favorites = await self._get_user_favorite_ids(user_id)

        # Convert to dicts
        article_dicts = []
        for article in articles:
            article_dict = self._article_to_dict(article)
            article_dict["is_favorite"] = article.id in user_favorites
            article_dicts.append(article_dict)

        return article_dicts

    async def create_article(
        self,
        data: dict[str, Any],
        author_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a new article.

        Args:
            data: Article data
            author_id: Optional author user ID

        Returns:
            Created article dict
        """
        article = KBArticleModel(
            id=data.get("id", data.get("slug")),
            title=data["title"],
            slug=data["slug"],
            category=data["category"],
            description=data["description"],
            content=data["content"],
            author_id=author_id,
            tags=data.get("tags", []),
            is_published=data.get("is_published", True),
        )

        self._db.add(article)
        await self._db.commit()
        await self._db.refresh(article)

        # Invalidate cache
        await self._invalidate_article_cache(article.id)

        logger.info("Created KB article: %s", article.slug)
        return self._article_to_dict(article)

    async def update_article(
        self,
        article_id: str,
        data: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        Update an existing article.

        Args:
            article_id: Article ID
            data: Updated data

        Returns:
            Updated article dict or None
        """
        query = select(KBArticleModel).where(KBArticleModel.id == article_id)
        result = await self._db.execute(query)
        article = result.scalar_one_or_none()

        if not article:
            return None

        # Update fields — allowlist to prevent mass-assignment of id, author_id, etc.
        _UPDATABLE_FIELDS = {
            "title",
            "slug",
            "category",
            "description",
            "content",
            "tags",
            "is_published",
            "metadata_json",
        }
        for key, value in data.items():
            if key in _UPDATABLE_FIELDS and hasattr(article, key):
                setattr(article, key, value)

        await self._db.commit()
        await self._db.refresh(article)

        # Invalidate cache
        await self._invalidate_article_cache(article_id)

        logger.info("Updated KB article: %s", article.slug)
        return self._article_to_dict(article)

    async def delete_article(self, article_id: str) -> bool:
        """
        Delete an article.

        Args:
            article_id: Article ID

        Returns:
            True if deleted, False if not found
        """
        query = select(KBArticleModel).where(KBArticleModel.id == article_id)
        result = await self._db.execute(query)
        article = result.scalar_one_or_none()

        if not article:
            return False

        await self._db.delete(article)
        await self._db.commit()

        # Invalidate cache
        await self._invalidate_article_cache(article_id)

        logger.info("Deleted KB article: %s", article_id)
        return True

    # ========================================================================
    # FAVORITES OPERATIONS
    # ========================================================================

    async def toggle_favorite(
        self,
        user_id: str,
        article_id: str,
    ) -> dict[str, Any]:
        """
        Toggle favorite status for an article.

        Args:
            user_id: User ID
            article_id: Article ID

        Returns:
            Dict with article_id and is_favorite status
        """
        # Check if already favorited
        query = select(KBFavoriteModel).where(
            KBFavoriteModel.user_id == user_id,
            KBFavoriteModel.article_id == article_id,
        )
        result = await self._db.execute(query)
        existing = result.scalar_one_or_none()

        if existing:
            # Remove favorite
            await self._db.delete(existing)
            await self._db.commit()
            is_favorite = False
            logger.info("Removed favorite: user=%s article=%s", user_id, article_id)
        else:
            # Add favorite
            favorite = KBFavoriteModel(
                user_id=user_id,
                article_id=article_id,
            )
            self._db.add(favorite)
            await self._db.commit()
            is_favorite = True
            logger.info("Added favorite: user=%s article=%s", user_id, article_id)

        # Invalidate favorites cache
        await self._invalidate_favorites_cache(user_id)

        return {
            "article_id": article_id,
            "is_favorite": is_favorite,
        }

    async def get_user_favorites(
        self,
        user_id: str,
    ) -> list[dict[str, Any]]:
        """
        Get all favorites for a user.

        Args:
            user_id: User ID

        Returns:
            List of favorited articles
        """
        query = (
            select(KBArticleModel)
            .join(KBFavoriteModel)
            .where(KBFavoriteModel.user_id == user_id)
            .options(selectinload(KBArticleModel.favorites))
        )
        result = await self._db.execute(query)
        articles = result.scalars().all()

        return [self._article_to_dict(a, is_favorite=True) for a in articles]

    async def _is_favorite(self, user_id: str, article_id: str) -> bool:
        """Check if article is favorited by user."""
        query = select(KBFavoriteModel).where(
            KBFavoriteModel.user_id == user_id,
            KBFavoriteModel.article_id == article_id,
        )
        result = await self._db.execute(query)
        return result.scalar_one_or_none() is not None

    async def _get_user_favorite_ids(self, user_id: str) -> set:
        """Get set of article IDs favorited by user."""
        query = select(KBFavoriteModel.article_id).where(KBFavoriteModel.user_id == user_id)
        result = await self._db.execute(query)
        return {row[0] for row in result.fetchall()}

    # ========================================================================
    # VIEW TRACKING
    # ========================================================================

    async def _increment_view_count(
        self,
        article_id: str,
        user_id: str | None = None,
    ) -> int:
        """
        Increment view count for an article.

        Args:
            article_id: Article ID
            user_id: Optional user ID for history

        Returns:
            New view count
        """
        # Increment in database
        query = (
            update(KBArticleModel)
            .where(KBArticleModel.id == article_id)
            .values(views=KBArticleModel.views + 1)
            .returning(KBArticleModel.views)
        )
        result = await self._db.execute(query)
        new_count = result.scalar() or 0

        # Track in Redis for real-time metrics
        if self._redis:
            try:
                await self._redis.incr(f"{CACHE_PREFIX_VIEWS}{article_id}")
            except Exception as e:
                logger.debug("Failed to track view in Redis: %s", e)

        # Record view history
        if user_id:
            history = KBViewHistoryModel(
                user_id=user_id,
                article_id=article_id,
            )
            self._db.add(history)
            await self._db.commit()

        return new_count

    async def get_view_count(self, article_id: str) -> int:
        """Get current view count for an article."""
        query = select(KBArticleModel.views).where(KBArticleModel.id == article_id)
        result = await self._db.execute(query)
        return result.scalar() or 0

    # ========================================================================
    # CATEGORIES
    # ========================================================================

    async def _get_categories(self) -> list[str]:
        """Get list of all categories."""
        query = select(KBArticleModel.category).distinct()
        result = await self._db.execute(query)
        return sorted([row[0] for row in result.fetchall()])

    async def list_categories(self) -> list[dict[str, Any]]:
        """Get all categories with metadata."""
        query = select(KBCategoryModel).where(KBCategoryModel.is_active.is_(True)).order_by(KBCategoryModel.sort_order)
        result = await self._db.execute(query)
        categories = result.scalars().all()

        return [
            {
                "id": c.id,
                "name": c.name,
                "slug": c.slug,
                "description": c.description,
                "icon": c.icon,
            }
            for c in categories
        ]

    # ========================================================================
    # CACHE MANAGEMENT
    # ========================================================================

    async def _invalidate_article_cache(self, article_id: str) -> None:
        """Invalidate cache for an article."""
        if self._redis:
            try:
                await self._redis.delete(f"{CACHE_PREFIX_ARTICLE}{article_id}")
            except Exception as e:
                logger.debug("Failed to invalidate article cache: %s", e)

    async def _invalidate_favorites_cache(self, user_id: str) -> None:
        """Invalidate favorites cache for a user."""
        if self._redis:
            try:
                await self._redis.delete(f"{CACHE_PREFIX_FAVORITES}{user_id}")
            except Exception as e:
                logger.debug("Failed to invalidate favorites cache: %s", e)

    # ========================================================================
    # UTILITY METHODS
    # ========================================================================

    def _article_to_dict(
        self,
        article: KBArticleModel,
        is_favorite: bool = False,
    ) -> dict[str, Any]:
        """Convert article model to dictionary."""
        return {
            "id": article.id,
            "title": article.title,
            "slug": article.slug,
            "category": article.category,
            "description": article.description,
            "content": article.content,
            "updated_at": article.updated_at.isoformat() if article.updated_at else None,
            "views": article.views,
            "is_favorite": is_favorite,
            "tags": article.tags or [],
            "author": "Helix Team",  # Could be derived from author relationship
        }


# ============================================================================
# SERVICE FACTORY
# ============================================================================


async def get_kb_service(db: AsyncSession, redis: Any | None = None) -> KnowledgeBaseService:
    """
    Factory function to create KB service.

    Args:
        db: SQLAlchemy async session
        redis: Optional Redis client

    Returns:
        KnowledgeBaseService instance
    """
    return KnowledgeBaseService(db, redis)
