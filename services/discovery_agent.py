"""
Discovery Agent - Coordination-Aware URL Analysis
===================================================

A coordination-driven content discovery and analysis agent that fetches,
analyzes, and evaluates web content while respecting ethical boundaries
and integrating with the UCF coordination framework.

Features:
- URL validation with security checks
- Domain allowlist/blocklist enforcement
- Content fetching with timeout and size limits
- Coordination relevance analysis
- Integration with Ethics Validator ethics validation
- Zapier webhook triggers for discovered content

Security:
- SSRF protection (blocks private IPs, localhost)
- Content type filtering (rejects binary)
- Response size limits
- Rate limiting support
- Redirect loop detection
"""

import asyncio
import logging
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from aiohttp import ClientError, ClientTimeout

# Try to import BeautifulSoup for HTML parsing
try:
    from bs4 import BeautifulSoup

    HAS_BS4 = True
except ImportError:
    BeautifulSoup = None
    HAS_BS4 = False

# Import aiohttp for HTTP requests
try:
    import aiohttp
    from aiohttp import ClientSession

    HAS_AIOHTTP = True
except ImportError:
    aiohttp = None
    ClientSession = None
    HAS_AIOHTTP = False


class DiscoveryError(Exception):
    """Exception raised during content discovery operations."""


@dataclass
class DiscoveryResult:
    """Result of a content discovery operation."""

    timestamp: str
    url: str
    status: str  # success, failed, blocked
    content_preview: str | None = None
    content_length: int = 0
    content_type: str = "unknown"
    title: str | None = None
    description: str | None = None
    analysis: dict[str, Any] | None = None
    coordination_metrics: dict[str, float] | None = None
    error: str | None = None
    success: bool = False
    extracted_links: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class URLValidation:
    """Result of URL validation."""

    valid: bool
    url: str
    reason: str | None = None
    domain: str | None = None


class DiscoveryAgent:
    """
    Coordination-aware content discovery agent.

    Integrates with the Helix coordination framework to:
    - Gate discovery operations based on coordination level
    - Evaluate content relevance to coordination expansion
    - Trigger appropriate Zapier workflows for valuable discoveries
    - Maintain ethical boundaries via Ethics Validator validation

    Example:
        >>> agent = DiscoveryAgent()
        >>> result = await agent.discover(
        ...     "https://docs.python.org/3/library/asyncio.html",
        ...     user_context={"performance_score": 7.0}
        ... )
        >>> if result.status == "success":
        ...     print("Discovered: {}".format(result.title))
    """

    def __init__(
        self,
        allowed_domains: list[str] | None = None,
        blocked_domains: list[str] | None = None,
        timeout_seconds: int = 10,
        max_content_size: int = 1_048_576,  # 1MB
        user_agent: str = "Helix-Discovery/1.0",
    ):
        self.logger = logging.getLogger("DiscoveryAgent")

        # Domain configuration
        self.allowed_domains = allowed_domains or [
            # Documentation sites
            "docs.python.org",
            "developer.mozilla.org",
            "fastapi.tiangolo.com",
            "nodejs.org",
            "docs.github.com",
            "railway.app",
            # Code repositories
            "github.com",
            "gitlab.com",
            "bitbucket.org",
            # Q&A and learning
            "stackoverflow.com",
            "stackexchange.com",
            "dev.to",
            "medium.com",
            # AI and coordination research
            "arxiv.org",
            "openai.com",
            "anthropic.com",
            # Helix ecosystem
            "helixspiral.work",
            "helix-unified-production.up.railway.app",
        ]

        self.blocked_domains = blocked_domains or [
            # Social media (high noise)
            "facebook.com",
            "twitter.com",
            "tiktok.com",
            "instagram.com",
            # Potential security risks
            "bit.ly",
            "t.co",
            "goo.gl",
            # Adult content
            "pornhub.com",
            "xvideos.com",
        ]

        self.timeout_seconds = timeout_seconds
        self.max_content_size = max_content_size
        self.user_agent = user_agent

        # Rate limiting
        self._request_times: dict[str, list[datetime]] = {}
        self._rate_limit_per_minute = 10

        # Coordination keywords for relevance analysis
        self.coordination_keywords = [
            "ai",
            "artificial intelligence",
            "machine learning",
            "neural",
            "agent",
            "coordination",
            "automation",
            "algorithm",
            "api",
            "webhook",
            "integration",
            "workflow",
            "awareness",
            "cognition",
            "reasoning",
            "learning",
            "model",
            "training",
            "inference",
            "ethics",
            "safety",
            "alignment",
            "harmony",
            "wisdom",
        ]

        # Dangerous patterns to block
        self.dangerous_patterns = [
            r"localhost",
            r"127\.0\.0\.\d+",
            r"192\.168\.\d+\.\d+",
            r"10\.\d+\.\d+\.\d+",
            r"172\.(1[6-9]|2\d|3[01])\.\d+\.\d+",
            r"0\.0\.0\.0",
            r"::1",
            r"file://",
            r"ftp://",
        ]

    async def discover(
        self,
        url: str,
        user_context: dict[str, Any] | None = None,
        analysis_depth: str = "standard",
    ) -> DiscoveryResult:
        """
        Discover and analyze content from a URL.

        Args:
            url: The URL to discover
            user_context: Context including performance_score, user_id, etc.
            analysis_depth: "quick", "standard", or "deep"

        Returns:
            DiscoveryResult with content analysis and coordination metrics
        """
        context = user_context or {}
        performance_score = context.get("performance_score", 5.0)

        # Check coordination level gate
        if performance_score < 4.0:
            return DiscoveryResult(
                timestamp=datetime.now(UTC).isoformat(),
                url=url,
                status="blocked",
                error="Discovery suspended - coordination level below threshold (4.0)",
                coordination_metrics={"harmony": 0.7, "relevance": 0.0},
                success=False,
                extracted_links=[],
            )

        # Validate URL
        validation = self._validate_url(url)
        if not validation.valid:
            return DiscoveryResult(
                timestamp=datetime.now(UTC).isoformat(),
                url=url,
                status="blocked",
                error=validation.reason,
                coordination_metrics={"harmony": 0.7, "relevance": 0.0},
                success=False,
                extracted_links=[],
            )

        # Derive a normalized, safe URL for fetching to reduce SSRF risk
        parsed = urlparse(url)
        scheme = (parsed.scheme or "").lower()
        if scheme not in ("http", "https"):
            return DiscoveryResult(
                timestamp=datetime.now(UTC).isoformat(),
                url=url,
                status="blocked",
                error="Unsupported URL scheme: {}".format(scheme or "missing"),
                coordination_metrics={"harmony": 0.7, "relevance": 0.0},
                success=False,
                extracted_links=[],
            )
        parsed.geturl()

        # Check rate limit
        if not self._check_rate_limit(validation.domain):
            return DiscoveryResult(
                timestamp=datetime.now(UTC).isoformat(),
                url=url,
                status="blocked",
                error="Rate limit exceeded",
                coordination_metrics={"harmony": 0.6, "relevance": 0.0},
                success=False,
                extracted_links=[],
            )

        # Fetch content
        try:
            content_data = await self._fetch_content(url)
            if not content_data["success"]:
                return DiscoveryResult(
                    timestamp=datetime.now(UTC).isoformat(),
                    url=url,
                    status="failed",
                    error=content_data.get("error", "Unknown fetch error"),
                    coordination_metrics={"harmony": 0.7, "relevance": 0.0},
                    success=False,
                    extracted_links=[],
                )

            # Analyze content
            analysis = self._analyze_content(
                content_data["content"],
                content_data["content_type"],
                url,
                analysis_depth,
            )

            # Calculate coordination metrics
            coordination_metrics = self._calculate_coordination_metrics(analysis, performance_score)

            return DiscoveryResult(
                timestamp=datetime.now(UTC).isoformat(),
                url=url,
                status="success",
                content_preview=(
                    content_data["content"][:500] + "..."
                    if len(content_data["content"]) > 500
                    else content_data["content"]
                ),
                content_length=len(content_data["content"]),
                content_type=content_data["content_type"],
                title=analysis.get("title"),
                description=analysis.get("description"),
                analysis=analysis,
                coordination_metrics=coordination_metrics,
                success=True,
                extracted_links=[],
            )

        except Exception as e:
            self.logger.error("Discovery failed for %s: %s", url, e)
            return DiscoveryResult(
                timestamp=datetime.now(UTC).isoformat(),
                url=url,
                status="failed",
                error=str(e),
                coordination_metrics={"harmony": 0.6, "relevance": 0.0},
                success=False,
                extracted_links=[],
            )

    def _validate_url(self, url: str) -> URLValidation:
        """Validate URL for safety and allowed domains."""
        try:
            parsed = urlparse(url)

            # Check scheme
            if parsed.scheme not in ("http", "https"):
                return URLValidation(
                    valid=False,
                    url=url,
                    reason=f"Invalid scheme: {parsed.scheme}",
                )

            # Extract domain
            domain = parsed.hostname
            if not domain:
                return URLValidation(valid=False, url=url, reason="Could not extract domain")

            domain = domain.lower().lstrip("www.")

            # Check dangerous patterns (SSRF protection)
            for pattern in self.dangerous_patterns:
                if re.search(pattern, url, re.IGNORECASE):
                    return URLValidation(
                        valid=False,
                        url=url,
                        reason="Security violation: dangerous URL pattern detected",
                    )

            # Check blocked domains
            if any(blocked in domain for blocked in self.blocked_domains):
                return URLValidation(valid=False, url=url, reason=f"Domain blocked: {domain}")

            # Check allowed domains (if allowlist is non-empty)
            if self.allowed_domains:
                if not any(allowed in domain for allowed in self.allowed_domains):
                    return URLValidation(
                        valid=False,
                        url=url,
                        reason=f"Domain not in allowlist: {domain}",
                    )

            # Check for suspicious file extensions
            suspicious_extensions = [".exe", ".zip", ".tar", ".gz", ".rar", ".7z"]
            if any(url.lower().endswith(ext) for ext in suspicious_extensions):
                return URLValidation(
                    valid=False,
                    url=url,
                    reason="Binary/archive file types not supported",
                )

            return URLValidation(valid=True, url=url, domain=domain)

        except Exception as e:
            return URLValidation(valid=False, url=url, reason=f"URL parsing error: {e}")

    def _check_rate_limit(self, domain: str) -> bool:
        """Check if domain is within rate limits."""
        now = datetime.now(UTC)
        cutoff = now - timedelta(minutes=1)

        # Clean old entries
        if domain in self._request_times:
            self._request_times[domain] = [t for t in self._request_times[domain] if t > cutoff]
        else:
            self._request_times[domain] = []

        # Check rate
        if len(self._request_times[domain]) >= self._rate_limit_per_minute:
            return False

        # Record this request
        self._request_times[domain].append(now)
        return True

    async def _fetch_content(self, url: str) -> dict[str, Any]:
        """
        Fetches the resource at the given URL and returns a structured result subject to safety checks.

        Performs scheme validation, HTTP status and content-type checks, and enforces a maximum content size. The returned dictionary contains a success flag and, on success, the fetched text along with content metadata; on failure it contains an error message describing the reason.

        Parameters:
            url (str): The URL to fetch.

        Returns:
            Dict[str, Any]: A result dictionary with the following keys:
                - success (bool): `True` if the fetch succeeded and content passed safety checks, `False` otherwise.
                - content (str): The fetched text content when `success` is `True`.
                - content_type (str): The reported Content-Type header (lowercased) when `success` is `True`.
                - status_code (int): The HTTP status code returned by the server when `success` is `True`.
                - error (str): A human-readable error message when `success` is `False` (examples: unsupported scheme, HTTP error status, unsupported content type, content too large, request timed out, client error).
        """
        # Defensive check: only allow HTTP(S) URLs to be fetched
        parsed = urlparse(url)
        scheme = (parsed.scheme or "").lower()
        if scheme not in ("http", "https"):
            return {
                "success": False,
                "error": "Unsupported URL scheme for fetch: {}".format(scheme or "missing"),
            }

        if not HAS_AIOHTTP:
            return {"success": False, "error": "aiohttp not installed"}

        timeout = ClientTimeout(total=self.timeout_seconds)

        try:
            async with (
                aiohttp.ClientSession(timeout=timeout) as session,
                session.get(
                    url,
                    headers={
                        "User-Agent": self.user_agent,
                        "Accept": "text/html,text/plain,application/json",
                    },
                    max_redirects=5,
                ) as response,
            ):
                # Check status
                if response.status >= 400:
                    return {
                        "success": False,
                        "error": f"HTTP {response.status}: {response.reason}",
                    }

                # Check content type
                content_type = response.headers.get("Content-Type", "").lower()
                if not any(ct in content_type for ct in ["text", "json", "html", "xml"]):
                    return {
                        "success": False,
                        "error": f"Unsupported content type: {content_type}",
                    }

                # Check content length
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > self.max_content_size:
                    return {
                        "success": False,
                        "error": f"Content too large: {content_length} bytes",
                    }

                # Read content with size limit
                content = await response.text()
                if len(content) > self.max_content_size:
                    content = content[: self.max_content_size]

                return {
                    "success": True,
                    "content": content,
                    "content_type": content_type,
                    "status_code": response.status,
                }

        except TimeoutError:
            return {"success": False, "error": "Request timed out"}
        except ClientError as e:
            return {"success": False, "error": f"Client error: {e}"}

    def _analyze_content(self, content: str, content_type: str, url: str, depth: str) -> dict[str, Any]:
        """Analyze content for relevance and metadata."""
        analysis = {
            "content_type_detected": self._detect_content_type(content, url),
            "word_count": len(content.split()),
            "estimated_reading_time": len(content.split()) // 200,  # ~200 wpm
        }

        # Extract title and description if HTML
        if "html" in content_type.lower() and HAS_BS4:
            soup = BeautifulSoup(content, "html.parser")

            # Extract title
            title_tag = soup.find("title")
            if title_tag:
                analysis["title"] = title_tag.get_text().strip()

            # Extract description
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc:
                analysis["description"] = meta_desc.get("content", "").strip()

            # Extract main content text for analysis
            text_content = soup.get_text()
        else:
            text_content = content
            analysis["title"] = None
            analysis["description"] = None

        # Analyze coordination relevance
        content_lower = text_content.lower()
        keyword_matches = [kw for kw in self.coordination_keywords if kw in content_lower]

        analysis["coordination_keywords_found"] = keyword_matches
        analysis["coordination_relevance"] = min(len(keyword_matches) / len(self.coordination_keywords), 1.0)

        # Detect if this is code/documentation
        code_indicators = ["```", "def ", "function ", "class ", "import ", "const "]
        analysis["contains_code"] = any(ind in content for ind in code_indicators)

        return analysis

    def _detect_content_type(self, content: str, url: str) -> str:
        """Detect the semantic type of content."""
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()

        if hostname == "github.com" or hostname.endswith(".github.com"):
            return "code_repository"
        elif any(doc in url.lower() for doc in ["docs.", "documentation", "/doc/"]):
            return "documentation"
        elif "stackoverflow" in hostname:
            return "qa_forum"
        elif hostname == "arxiv.org" or hostname.endswith(".arxiv.org"):
            return "research_paper"
        elif content.strip().startswith("{") or content.strip().startswith("["):
            return "json_data"
        elif "<html" in content.lower():
            return "webpage"
        else:
            return "text_content"

    def _calculate_coordination_metrics(self, analysis: dict[str, Any], base_coordination: float) -> dict[str, float]:
        """Calculate coordination impact metrics for the discovery."""
        relevance = analysis.get("coordination_relevance", 0.0)

        # Harmony boost for relevant content
        harmony = 0.7 + (relevance * 0.2)

        # Relevance directly from analysis
        relevance_score = relevance

        # Processing load based on content size
        word_count = analysis.get("word_count", 0)
        processing_load = min(word_count / 5000, 0.3)

        # Discovery value based on content type and relevance
        content_type = analysis.get("content_type_detected", "unknown")
        type_bonus = {
            "documentation": 0.2,
            "code_repository": 0.15,
            "research_paper": 0.25,
            "qa_forum": 0.1,
        }.get(content_type, 0.0)

        discovery_value = min(1.0, relevance + type_bonus)

        return {
            "harmony": round(harmony, 4),
            "relevance": round(relevance_score, 4),
            "processing_load": round(processing_load, 4),
            "discovery_value": round(discovery_value, 4),
        }

    async def batch_discover(
        self,
        urls: list[str],
        user_context: dict[str, Any] | None = None,
        max_concurrent: int = 5,
    ) -> list[DiscoveryResult]:
        """
        Discover multiple URLs concurrently.

        Args:
            urls: List of URLs to discover
            user_context: Shared context for all discoveries
            max_concurrent: Maximum concurrent requests

        Returns:
            List of DiscoveryResult for each URL
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def bounded_discover(url: str) -> DiscoveryResult:
            async with semaphore:
                return await self.discover(url, user_context)

        tasks = [bounded_discover(url) for url in urls]
        return await asyncio.gather(*tasks)

    async def crawl_sitemap(
        self,
        sitemap_url: str,
        user_context: dict[str, Any] | None = None,
        max_urls: int = 50,
    ) -> dict[str, Any]:
        """
        Crawl a sitemap.xml and discover all URLs within.

        Args:
            sitemap_url: URL to sitemap.xml
            user_context: User context for discoveries
            max_urls: Maximum URLs to process from sitemap

        Returns:
            Dict with sitemap metadata and discovery results

        Example:
            >>> results = await agent.crawl_sitemap(
            ...     "https://example.com/sitemap.xml"
            ... )
        """
        self.logger.info("Crawling sitemap: %s", sitemap_url)

        # Validate sitemap URL
        validation = self._validate_url(sitemap_url)
        if not validation.valid:
            return {
                "success": False,
                "sitemap_url": sitemap_url,
                "error": validation.reason,
                "urls_found": 0,
                "urls_processed": 0,
                "results": [],
            }

        # Fetch sitemap
        content_data = await self._fetch_content(sitemap_url)
        if not content_data["success"]:
            return {
                "success": False,
                "sitemap_url": sitemap_url,
                "error": content_data.get("error", "Failed to fetch sitemap"),
                "urls_found": 0,
                "urls_processed": 0,
                "results": [],
            }

        # Parse sitemap XML
        urls = self._parse_sitemap(content_data["content"])
        self.logger.info("Found %d URLs in sitemap", len(urls))

        # Limit URLs
        urls_to_process = urls[:max_urls]

        # Discover all URLs
        results = await self.batch_discover(
            urls_to_process,
            user_context=user_context,
            max_concurrent=5,
        )

        successful = sum(1 for r in results if r.success)

        return {
            "success": True,
            "sitemap_url": sitemap_url,
            "urls_found": len(urls),
            "urls_processed": len(urls_to_process),
            "successful_discoveries": successful,
            "failed_discoveries": len(urls_to_process) - successful,
            "results": [r.to_dict() for r in results],
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def _parse_sitemap(self, content: str) -> list[str]:
        """Parse sitemap XML and extract URLs."""
        urls = []

        if HAS_BS4:
            soup = BeautifulSoup(content, "xml")
            # Standard sitemap format
            for loc in soup.find_all("loc"):
                url = loc.get_text().strip()
                if url:
                    urls.append(url)
        else:
            # Fallback regex parsing
            import re

            loc_pattern = r"<loc>\s*(https?://[^<]+)\s*</loc>"
            matches = re.findall(loc_pattern, content, re.IGNORECASE)
            urls = [m.strip() for m in matches]

        return urls

    async def crawl_rss(
        self,
        feed_url: str,
        user_context: dict[str, Any] | None = None,
        max_items: int = 20,
    ) -> dict[str, Any]:
        """
        Crawl an RSS/Atom feed and discover linked content.

        Args:
            feed_url: URL to RSS or Atom feed
            user_context: User context for discoveries
            max_items: Maximum feed items to process

        Returns:
            Dict with feed metadata and discovery results

        Example:
            >>> results = await agent.crawl_rss(
            ...     "https://example.com/feed.xml"
            ... )
        """
        self.logger.info("Crawling RSS feed: %s", feed_url)

        # Validate feed URL
        validation = self._validate_url(feed_url)
        if not validation.valid:
            return {
                "success": False,
                "feed_url": feed_url,
                "error": validation.reason,
                "items_found": 0,
                "items_processed": 0,
                "results": [],
            }

        # Fetch feed
        content_data = await self._fetch_content(feed_url)
        if not content_data["success"]:
            return {
                "success": False,
                "feed_url": feed_url,
                "error": content_data.get("error", "Failed to fetch feed"),
                "items_found": 0,
                "items_processed": 0,
                "results": [],
            }

        # Parse feed
        feed_data = self._parse_rss(content_data["content"])
        self.logger.info(
            "Found %d items in feed: %s",
            len(feed_data["items"]),
            feed_data.get("title", "Unknown"),
        )

        # Get URLs from feed items
        urls = [item["link"] for item in feed_data["items"][:max_items] if item.get("link")]

        # Discover all URLs
        results = await self.batch_discover(
            urls,
            user_context=user_context,
            max_concurrent=5,
        )

        successful = sum(1 for r in results if r.success)

        return {
            "success": True,
            "feed_url": feed_url,
            "feed_title": feed_data.get("title"),
            "feed_description": feed_data.get("description"),
            "items_found": len(feed_data["items"]),
            "items_processed": len(urls),
            "successful_discoveries": successful,
            "failed_discoveries": len(urls) - successful,
            "results": [r.to_dict() for r in results],
            "items_metadata": [
                {
                    "title": item.get("title"),
                    "link": item.get("link"),
                    "published": item.get("published"),
                }
                for item in feed_data["items"][:max_items]
            ],
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def _parse_rss(self, content: str) -> dict[str, Any]:
        """Parse RSS/Atom feed and extract items."""
        feed_data = {
            "title": None,
            "description": None,
            "items": [],
        }

        if HAS_BS4:
            soup = BeautifulSoup(content, "xml")

            # Try RSS format
            channel = soup.find("channel")
            if channel:
                title_tag = channel.find("title")
                if title_tag:
                    feed_data["title"] = title_tag.get_text().strip()

                desc_tag = channel.find("description")
                if desc_tag:
                    feed_data["description"] = desc_tag.get_text().strip()

                for item in soup.find_all("item"):
                    item_data = {}
                    title = item.find("title")
                    if title:
                        item_data["title"] = title.get_text().strip()
                    link = item.find("link")
                    if link:
                        item_data["link"] = link.get_text().strip()
                    pub_date = item.find("pubDate")
                    if pub_date:
                        item_data["published"] = pub_date.get_text().strip()
                    description = item.find("description")
                    if description:
                        item_data["description"] = description.get_text().strip()[:200]
                    if item_data:
                        feed_data["items"].append(item_data)

            # Try Atom format
            else:
                title_tag = soup.find("title")
                if title_tag:
                    feed_data["title"] = title_tag.get_text().strip()

                subtitle = soup.find("subtitle")
                if subtitle:
                    feed_data["description"] = subtitle.get_text().strip()

                for entry in soup.find_all("entry"):
                    item_data = {}
                    title = entry.find("title")
                    if title:
                        item_data["title"] = title.get_text().strip()
                    link = entry.find("link")
                    if link:
                        item_data["link"] = link.get("href", "")
                    published = entry.find("published") or entry.find("updated")
                    if published:
                        item_data["published"] = published.get_text().strip()
                    summary = entry.find("summary") or entry.find("content")
                    if summary:
                        item_data["description"] = summary.get_text().strip()[:200]
                    if item_data:
                        feed_data["items"].append(item_data)
        else:
            # Fallback regex parsing for RSS
            import re

            title_match = re.search(r"<title>([^<]+)</title>", content, re.IGNORECASE)
            if title_match:
                feed_data["title"] = title_match.group(1).strip()

            # Extract items
            item_pattern = r"<item>(.*?)</item>"
            items = re.findall(item_pattern, content, re.DOTALL | re.IGNORECASE)

            for item_content in items:
                item_data = {}
                title_match = re.search(r"<title>([^<]+)</title>", item_content)
                if title_match:
                    item_data["title"] = title_match.group(1).strip()
                link_match = re.search(r"<link>([^<]+)</link>", item_content)
                if link_match:
                    item_data["link"] = link_match.group(1).strip()
                if item_data:
                    feed_data["items"].append(item_data)

        return feed_data


# Synchronous wrapper for non-async contexts
def discover_sync(url: str, user_context: dict[str, Any] | None = None) -> DiscoveryResult:
    """Synchronous wrapper for discover()."""
    agent = DiscoveryAgent()
    return asyncio.run(agent.discover(url, user_context))
