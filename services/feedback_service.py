"""
Feedback service for Helix Collective.

This service handles all business logic related to feedback management,
including CRUD operations, statistics calculation, and data export.
"""

import csv
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import desc, func, select
from sqlalchemy.orm import joinedload

from ..models.feedback import Feedback, FeedbackResponse

logger = logging.getLogger(__name__)


class FeedbackService:
    """Service for managing feedback operations"""

    def __init__(self) -> None:
        pass  # Remove the incorrect db initialization

    async def create_feedback(self, feedback_data: dict[str, Any], db) -> Feedback | None:
        """
        Create new feedback record

        Args:
            feedback_data: Dictionary containing feedback data
            db: Database session

        Returns:
            Created Feedback object or None if failed
        """
        try:
            validated_data = self.validate_feedback_data(feedback_data)

            # Create feedback with validated values
            feedback = Feedback(
                id=str(uuid4()),
                text=validated_data["text"],
                page=validated_data.get("page", "unknown"),
                user_agent=validated_data.get("user_agent", "Unknown"),
                ip=validated_data.get("ip", "0.0.0.0"),
                user_id=validated_data.get("user_id"),
                status=validated_data.get("status", "new"),
                priority=validated_data.get("priority", "medium"),
                category=validated_data.get("category"),
                extra_data=validated_data.get("metadata", {}),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

            db.add(feedback)
            await db.commit()
            await db.refresh(feedback)

            logger.info("Created feedback %s", feedback.id)
            return feedback

        except (ValueError, TypeError, KeyError) as e:
            logger.debug("Feedback creation validation error: %s", e)
            return None
        except Exception as e:
            logger.error("Error creating feedback: %s", e)
            return None

    async def create_audit_feedback(
        self,
        message: str,
        category: str,
        performance_score: int,
        user_agent: str = "Unknown",
        ip_address: str = "0.0.0.0",
        user_id: str | None = None,
        db=None,
    ) -> Feedback | None:
        """
        Create feedback record for audit endpoint with coordination tracking

        Args:
            message: Feedback message
            category: Feedback category
            performance_score: Coordination level (1-10)
            user_agent: User agent string
            ip_address: IP address
            user_id: Optional user ID
            db: Database session

        Returns:
            Created Feedback object or None if failed
        """
        try:
            if not message or len(message.strip()) < 5:
                raise ValueError("Feedback message must be at least 5 characters")

            if not 1 <= performance_score <= 10:
                raise ValueError("Coordination level must be between 1 and 10")

            # Analyze sentiment
            sentiment = await self.analyze_sentiment(message)

            # Create feedback with audit-specific fields
            feedback = Feedback(
                id=str(uuid4()),
                text=message,
                page="audit_endpoint",  # Default page for audit feedback
                user_agent=user_agent,
                ip=ip_address,
                user_id=user_id,
                status="new",
                priority="medium",
                category=category,
                sentiment=sentiment,
                performance_score=performance_score,
                extra_data={},
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

            db.add(feedback)
            await db.commit()
            await db.refresh(feedback)

            logger.info("Created audit feedback %s with sentiment '%s'", feedback.id, sentiment)
            return feedback

        except ValueError:
            # Re-raise validation errors
            raise
        except Exception as e:
            logger.error("Error creating audit feedback: %s", e)
            return None

    def validate_feedback_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Validate and sanitize feedback data

        Args:
            data: Raw feedback data

        Returns:
            Validated and sanitized data

        Raises:
            ValueError: If validation fails
        """
        if not data.get("text"):
            raise ValueError("Feedback text is required")

        if not data.get("text", "").strip():
            raise ValueError("Feedback text cannot be empty")

        if len(data.get("text", "")) > 10000:
            raise ValueError("Feedback text too long (max 10000 characters)")

        # Validate status
        valid_statuses = ["new", "reviewed", "resolved", "archived"]
        status = data.get("status", "new")
        if status not in valid_statuses:
            raise ValueError(f"Invalid status '{status}'. Valid statuses are: {', '.join(valid_statuses)}")

        # Validate priority
        valid_priorities = ["low", "medium", "high", "critical"]
        priority = data.get("priority", "medium")
        if priority not in valid_priorities:
            raise ValueError(f"Invalid priority '{priority}'. Valid priorities are: {', '.join(valid_priorities)}")

        # Validate category if provided
        if data.get("category"):
            valid_categories = ["bug", "feature", "general", "cycle", "coordination"]
            if data["category"] not in valid_categories:
                raise ValueError(
                    f"Invalid category '{data['category']}'. Valid categories are: {', '.join(valid_categories)}"
                )

        # Sanitize sensitive data
        sanitized_data = data.copy()
        sanitized_data["ip"] = self._sanitize_ip(data.get("ip", ""))
        sanitized_data["user_agent"] = self._sanitize_user_agent(data.get("user_agent", ""))

        return sanitized_data

    async def analyze_sentiment(self, message: str) -> str:
        """
        Analyze sentiment of feedback message

        Args:
            message: Feedback message text

        Returns:
            Sentiment classification: 'positive', 'negative', or 'neutral'
        """
        try:
            # In production, this could be replaced with ML models or external APIs
            message_lower = message.lower()

            # Positive keywords
            positive_keywords = [
                "great",
                "excellent",
                "amazing",
                "wonderful",
                "fantastic",
                "love",
                "awesome",
                "brilliant",
                "perfect",
                "outstanding",
                "impressive",
                "helpful",
                "useful",
                "easy",
                "intuitive",
                "smooth",
                "fast",
                "responsive",
                "beautiful",
                "clean",
                "thank",
                "appreciate",
                "enjoy",
                "like",
                "good",
                "nice",
                "well",
                "best",
            ]

            # Negative keywords
            negative_keywords = [
                "terrible",
                "awful",
                "horrible",
                "bad",
                "worst",
                "hate",
                "disappointed",
                "frustrated",
                "annoying",
                "confusing",
                "slow",
                "broken",
                "buggy",
                "crash",
                "error",
                "fail",
                "problem",
                "issue",
                "difficult",
                "hard",
                "complicated",
                "ugly",
                "messy",
                "poor",
                "lame",
                "suck",
                "stupid",
                "ridiculous",
                "waste",
            ]

            positive_count = sum(1 for word in positive_keywords if word in message_lower)
            negative_count = sum(1 for word in negative_keywords if word in message_lower)

            if positive_count > negative_count:
                return "positive"
            elif negative_count > positive_count:
                return "negative"
            else:
                return "neutral"

        except Exception as e:
            logger.error("Error analyzing sentiment: %s", e)
            return "neutral"  # Default to neutral on error

    def _sanitize_ip(self, ip: str) -> str:
        """
        Sanitize IP address for privacy

        Args:
            ip: IP address string

        Returns:
            Sanitized IP address
        """
        if not ip:
            return "0.0.0.0"

        # For privacy, we can mask the last octet of IPv4 addresses
        if "." in ip and ip.count(".") == 3:
            parts = ip.split(".")
            if len(parts) == 4 and all(part.isdigit() and 0 <= int(part) <= 255 for part in parts):
                # Mask last octet
                parts[3] = "xxx"
                return ".".join(parts)

        # For IPv6 or other formats, return as-is for now
        return ip

    def _sanitize_user_agent(self, user_agent: str) -> str:
        """
        Sanitize user agent string for privacy

        Args:
            user_agent: User agent string

        Returns:
            Sanitized user agent
        """
        if not user_agent:
            return "Unknown"

        # Remove potentially sensitive information
        # For now, we'll keep it simple and just ensure it's not empty
        # In production, you might want to parse and remove specific identifiers
        return user_agent.strip() or "Unknown"

    async def get_feedback_by_id(self, feedback_id: str, db) -> Feedback | None:
        """
        Get feedback by ID

        Args:
            feedback_id: Feedback ID to retrieve
            db: Database session

        Returns:
            Feedback object or None if not found
        """
        try:
            result = await db.execute(
                select(Feedback).where(Feedback.id == feedback_id).options(joinedload(Feedback.responses))
            )
            return result.scalar_one_or_none()

        except Exception as e:
            logger.error("Error getting feedback %s: %s", feedback_id, e)
            return None

    async def get_feedback_list(
        self,
        db,
        page: int = 1,
        page_size: int = 50,
        status: str | None = None,
        priority: str | None = None,
        category: str | None = None,
        user_id: str | None = None,
    ) -> tuple[list[Feedback], int]:
        """
        Get paginated list of feedback

        Args:
            db: Database session
            page: Page number (1-based)
            page_size: Number of items per page
            status: Filter by status
            priority: Filter by priority
            category: Filter by category
            user_id: Filter by user ID

        Returns:
            Tuple of (feedback_list, total_count)
        """
        try:
            query = select(Feedback)

            if status:
                query = query.where(Feedback.status == status)
            if priority:
                query = query.where(Feedback.priority == priority)
            if category:
                query = query.where(Feedback.category == category)
            if user_id:
                query = query.where(Feedback.user_id == user_id)

            # Get total count for pagination
            count_query = select(func.count()).select_from(query.subquery())
            total_count_result = await db.execute(count_query)
            total_count = total_count_result.scalar()

            # Apply pagination and ordering
            query = query.order_by(desc(Feedback.created_at))
            query = query.offset((page - 1) * page_size).limit(page_size)

            # Execute query
            result = await db.execute(query)
            feedback_list = result.scalars().all()

            return feedback_list, total_count

        except Exception as e:
            logger.error("Error getting feedback list: %s", e)
            return [], 0

    async def update_feedback(self, feedback_id: str, update_data: dict[str, Any], db) -> Feedback | None:
        """
        Update feedback record

        Args:
            feedback_id: Feedback ID to update
            update_data: Dictionary of fields to update
            db: Database session

        Returns:
            Updated Feedback object or None if failed
        """
        try:
            result = await db.execute(select(Feedback).where(Feedback.id == feedback_id))
            feedback = result.scalar_one_or_none()

            if not feedback:
                return None

            # Update fields
            for key, value in update_data.items():
                if hasattr(feedback, key):
                    setattr(feedback, key, value)

            feedback.updated_at = datetime.now(UTC)
            await db.commit()
            await db.refresh(feedback)

            logger.info("Updated feedback %s", feedback_id)
            return feedback

        except Exception as e:
            logger.error("Error updating feedback %s: %s", feedback_id, e)
            return None

    async def delete_feedback(self, feedback_id: str, db) -> bool:
        """
        Delete feedback record

        Args:
            feedback_id: Feedback ID to delete
            db: Database session

        Returns:
            True if deleted, False if failed or not found
        """
        try:
            result = await db.execute(select(Feedback).where(Feedback.id == feedback_id))
            feedback = result.scalar_one_or_none()

            if not feedback:
                return False

            await db.delete(feedback)
            await db.commit()

            logger.info("Deleted feedback %s", feedback_id)
            return True

        except Exception as e:
            logger.error("Error deleting feedback %s: %s", feedback_id, e)
            return False

    async def create_response(
        self,
        feedback_id: str,
        admin_id: str,
        response_text: str,
        is_public: bool = False,
        db=None,
    ) -> FeedbackResponse | None:
        """
        Create admin response to feedback

        Args:
            feedback_id: Feedback ID to respond to
            admin_id: Admin user ID
            response_text: Response text
            is_public: Whether response is public
            db: Database session

        Returns:
            Created FeedbackResponse object or None if failed
        """
        try:
            feedback_result = await db.execute(select(Feedback).where(Feedback.id == feedback_id))
            feedback = feedback_result.scalar_one_or_none()

            if not feedback:
                return None

            # Create response
            response = FeedbackResponse(
                id=str(uuid4()),
                feedback_id=feedback_id,
                admin_id=admin_id,
                response_text=response_text,
                is_public=is_public,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

            db.add(response)
            await db.commit()
            await db.refresh(response)

            # Update feedback status if it was new
            if feedback.status == "new":
                feedback.status = "reviewed"
                feedback.updated_at = datetime.now(UTC)
                await db.commit()

            logger.info("Created response %s for feedback %s", response.id, feedback_id)
            return response

        except Exception as e:
            logger.error("Error creating response for feedback %s: %s", feedback_id, e)
            return None

    async def get_feedback_stats(self, db) -> dict[str, Any]:
        """
        Calculate feedback statistics

        Args:
            db: Database session

        Returns:
            Dictionary containing feedback statistics
        """
        try:
            status_counts = await db.execute(select(Feedback.status, func.count(Feedback.id)).group_by(Feedback.status))
            status_counts = dict(status_counts.all())

            # Counts by priority
            priority_counts = await db.execute(
                select(Feedback.priority, func.count(Feedback.id)).group_by(Feedback.priority)
            )
            priority_counts = dict(priority_counts.all())

            # Counts by category
            category_counts = await db.execute(
                select(Feedback.category, func.count(Feedback.id)).group_by(Feedback.category)
            )
            category_counts = dict(category_counts.all())

            # Total count
            total_count = await db.execute(select(func.count(Feedback.id)))
            total_count = total_count.scalar()

            # Calculate trends (last 30 days)
            thirty_days_ago = datetime.now(UTC) - timedelta(days=30)

            daily_trends = await db.execute(
                select(func.date(Feedback.created_at), func.count(Feedback.id))
                .where(Feedback.created_at >= thirty_days_ago)
                .group_by(func.date(Feedback.created_at))
                .order_by(func.date(Feedback.created_at))
            )
            daily_trends = dict(daily_trends.all())

            weekly_trends = await db.execute(
                select(
                    func.extract("week", Feedback.created_at),
                    func.count(Feedback.id),
                )
                .where(Feedback.created_at >= thirty_days_ago)
                .group_by(func.extract("week", Feedback.created_at))
                .order_by(func.extract("week", Feedback.created_at))
            )
            weekly_trends = dict(weekly_trends.all())

            return {
                "total": total_count,
                "new": status_counts.get("new", 0),
                "reviewed": status_counts.get("reviewed", 0),
                "resolved": status_counts.get("resolved", 0),
                "archived": status_counts.get("archived", 0),
                "by_priority": priority_counts,
                "by_category": category_counts,
                "trends": {"daily": daily_trends, "weekly": weekly_trends},
            }

        except Exception as e:
            logger.error("Error calculating feedback stats: %s", e)
            return {
                "total": 0,
                "new": 0,
                "reviewed": 0,
                "resolved": 0,
                "archived": 0,
                "by_priority": {},
                "by_category": {},
                "trends": {"daily": {}, "weekly": {}},
            }

    async def search_feedback(self, query: str, limit: int = 10, db=None) -> list[Feedback]:
        """
        Search feedback by text content

        Args:
            query: Search query string
            limit: Maximum number of results
            db: Database session

        Returns:
            List of matching feedback objects
        """
        try:
            search_query = (
                select(Feedback)
                .where(Feedback.text.ilike(f"%{query}%"))
                .order_by(desc(Feedback.created_at))
                .limit(limit)
            )

            result = await db.execute(search_query)
            return result.scalars().all()

        except Exception as e:
            logger.error("Error searching feedback: %s", e)
            return []

    async def get_recent_feedback(self, limit: int = 10, db=None) -> list[Feedback]:
        """
        Get most recent feedback

        Args:
            limit: Number of recent feedback items to retrieve
            db: Database session

        Returns:
            List of recent feedback objects
        """
        try:
            result = await db.execute(select(Feedback).order_by(desc(Feedback.created_at)).limit(limit))
            return result.scalars().all()

        except Exception as e:
            logger.error("Error getting recent feedback: %s", e)
            return []

    async def get_feedback(self, feedback_id: str) -> Feedback | None:
        """
        Get feedback by ID (alias for get_feedback_by_id)

        Args:
            feedback_id: Feedback ID to retrieve

        Returns:
            Feedback object or None if not found
        """
        return await self.get_feedback_by_id(feedback_id)

    async def list_feedback(
        self,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        priority: str | None = None,
        category: str | None = None,
        user_id: str | None = None,
    ) -> tuple[list[Feedback], int]:
        """
        List feedback with pagination (alias for get_feedback_list)

        Args:
            limit: Number of items per page
            offset: Offset for pagination
            status: Filter by status
            priority: Filter by priority
            category: Filter by category
            user_id: Filter by user ID

        Returns:
            Tuple of (feedback_list, total_count)
        """
        page = (offset // limit) + 1 if limit > 0 else 1
        return await self.get_feedback_list(
            page=page,
            page_size=limit,
            status=status,
            priority=priority,
            category=category,
            user_id=user_id,
        )

    async def export_feedback(self, format_type: str, db) -> str:
        """
        Export feedback data in specified format

        Args:
            format_type: Export format ('csv' or 'json')
            db: Database session

        Returns:
            Exported data as string
        """
        try:
            result = await db.execute(select(Feedback).options(joinedload(Feedback.responses)))
            feedback_list = result.scalars().all()

            if format_type.lower() == "csv":
                import io

                output = io.StringIO()
                writer = csv.writer(output)

                # Write header
                writer.writerow(
                    [
                        "ID",
                        "Text",
                        "Page",
                        "User Agent",
                        "IP",
                        "User ID",
                        "Status",
                        "Priority",
                        "Category",
                        "Created At",
                        "Updated At",
                    ]
                )

                # Write data
                for feedback in feedback_list:
                    writer.writerow(
                        [
                            feedback.id,
                            feedback.text,
                            feedback.page,
                            feedback.user_agent,
                            feedback.ip,
                            feedback.user_id,
                            feedback.status,
                            feedback.priority,
                            feedback.category,
                            (feedback.created_at.isoformat() if feedback.created_at else ""),
                            (feedback.updated_at.isoformat() if feedback.updated_at else ""),
                        ]
                    )

                return output.getvalue()

            elif format_type.lower() == "json":
                feedback_data = []
                for feedback in feedback_list:
                    feedback_dict = {
                        "id": feedback.id,
                        "text": feedback.text,
                        "page": feedback.page,
                        "user_agent": feedback.user_agent,
                        "ip": feedback.ip,
                        "user_id": feedback.user_id,
                        "status": feedback.status,
                        "priority": feedback.priority,
                        "category": feedback.category,
                        "created_at": (feedback.created_at.isoformat() if feedback.created_at else None),
                        "updated_at": (feedback.updated_at.isoformat() if feedback.updated_at else None),
                        "responses": [
                            {
                                "id": response.id,
                                "response_text": response.response_text,
                                "admin_id": response.admin_id,
                                "is_public": response.is_public,
                                "created_at": (response.created_at.isoformat() if response.created_at else None),
                            }
                            for response in feedback.responses
                        ],
                    }
                    feedback_data.append(feedback_dict)

                return json.dumps(feedback_data, indent=2)

            else:
                raise ValueError(f"Unsupported export format: {format_type}")

        except Exception as e:
            logger.error("Error exporting feedback: %s", e)
            return ""


# Initialize feedback service
feedback_service = FeedbackService()
