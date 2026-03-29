"""
Helix Execution Tracer — Visual Observability System
=====================================================

Real-time execution tracing and observability for all Helix operations:
- Agent task execution traces
- Workflow execution traces
- LLM inference traces
- API request traces

Fills the competitive gap vs OpenAI's built-in tracing and LangGraph Studio.

Features:
- In-memory trace storage with configurable retention
- OpenTelemetry export for Jaeger/Zipkin/OTLP backends
- Trace context propagation across services
- SSE streaming for live trace monitoring

(c) Helix Collective 2025 - Proprietary Technology Stack
"""

import asyncio
import json
import logging
import os
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

# ============================================================================
# OPENTELEMETRY INTEGRATION
# ============================================================================

# OpenTelemetry imports with graceful fallback
OTEL_AVAILABLE = False
trace = None
SpanKind = None
Status = None
StatusCode = None
OTLPSpanExporter = None
JaegerExporter = None
ZipkinExporter = None
Resource = None
TracerProvider = None
BatchSpanProcessor = None
ConsoleSpanExporter = None

try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider as SDKTracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.trace import SpanKind, Status, StatusCode

    # Optional exporters
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    except ImportError as e:
        logger.debug("OTLP exporter not available: %s", e)

    try:
        from opentelemetry.exporter.jaeger.thrift import JaegerExporter
    except ImportError as e:
        logger.debug("Jaeger exporter not available: %s", e)

    try:
        from opentelemetry.exporter.zipkin.json import ZipkinExporter
    except ImportError as e:
        logger.debug("Zipkin exporter not available: %s", e)

    OTEL_AVAILABLE = True
    logger.info("OpenTelemetry integration available")
except ImportError as e:
    logger.debug("OpenTelemetry not available, using internal tracing only: %s", e)


class OpenTelemetryConfig:
    """Configuration for OpenTelemetry export."""

    def __init__(self):
        self.enabled = os.getenv("HELIX_OTEL_ENABLED", "false").lower() == "true"
        self.service_name = os.getenv("HELIX_SERVICE_NAME", "helix-unified")
        self.exporter_type = os.getenv("HELIX_OTEL_EXPORTER", "console")  # console, otlp, jaeger, zipkin
        self.otlp_endpoint = os.getenv("HELIX_OTEL_ENDPOINT", "http://localhost:4317")
        self.jaeger_host = os.getenv("HELIX_JAEGER_HOST", "localhost")
        self.jaeger_port = int(os.getenv("HELIX_JAEGER_PORT", "6831"))
        self.zipkin_url = os.getenv("HELIX_ZIPKIN_URL", "http://localhost:9411/api/v2/spans")
        self.sample_rate = float(os.getenv("HELIX_TRACE_SAMPLE_RATE", "1.0"))

    @classmethod
    def from_env(cls) -> "OpenTelemetryConfig":
        return cls()


class OpenTelemetryBridge:
    """Bridge between Helix traces and OpenTelemetry."""

    def __init__(self, config: OpenTelemetryConfig | None = None):
        self.config = config or OpenTelemetryConfig()
        self._tracer = None
        self._provider = None
        self._active_otel_spans: dict[str, Any] = {}  # span_id -> OTEL span

        if OTEL_AVAILABLE and self.config.enabled:
            self._setup_otel()

    def _setup_otel(self):
        """Initialize OpenTelemetry with configured exporter."""
        if not OTEL_AVAILABLE:
            logger.warning("OpenTelemetry requested but not available")
            return

        try:
            # Create resource with service info
            resource = Resource.create(
                {
                    "service.name": self.config.service_name,
                    "service.version": "1.0.0",
                }
            )

            # Create tracer provider
            self._provider = SDKTracerProvider(resource=resource)

            # Add configured exporter
            exporter = self._create_exporter()
            if exporter:
                processor = BatchSpanProcessor(exporter)
                self._provider.add_span_processor(processor)

            # Set global tracer provider
            trace.set_tracer_provider(self._provider)
            self._tracer = trace.get_tracer(__name__)

            logger.info("OpenTelemetry initialized with %s exporter", self.config.exporter_type)
        except Exception as e:
            logger.error("Failed to initialize OpenTelemetry: %s", e)
            self._tracer = None

    def _create_exporter(self):
        """Create the configured exporter."""
        exporter_type = self.config.exporter_type.lower()

        if exporter_type == "console":
            return ConsoleSpanExporter()

        if exporter_type == "otlp" and OTLPSpanExporter:
            return OTLPSpanExporter(endpoint=self.config.otlp_endpoint)

        if exporter_type == "jaeger" and JaegerExporter:
            return JaegerExporter(
                agent_host_name=self.config.jaeger_host,
                agent_port=self.config.jaeger_port,
            )

        if exporter_type == "zipkin" and ZipkinExporter:
            return ZipkinExporter(endpoint=self.config.zipkin_url)

        logger.warning("Unknown exporter type '%s' or exporter not available, using console", exporter_type)
        return ConsoleSpanExporter()

    def is_enabled(self) -> bool:
        """Check if OpenTelemetry is enabled and available."""
        return OTEL_AVAILABLE and self.config.enabled and self._tracer is not None

    def start_otel_span(
        self,
        span_id: str,
        name: str,
        span_type: str,
        parent_span_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Any | None:
        """Start an OpenTelemetry span and link it to a Helix span."""
        if not self.is_enabled():
            return None

        try:
            # Determine span kind based on type
            kind = SpanKind.INTERNAL
            if span_type in ("llm", "inference"):
                kind = SpanKind.CLIENT
            elif span_type in ("api", "request"):
                kind = SpanKind.SERVER
            elif span_type in ("agent", "workflow"):
                kind = SpanKind.CONSUMER

            # Create attributes
            attrs = {
                "helix.span_id": span_id,
                "helix.span_type": span_type,
            }
            if attributes:
                attrs.update(attributes)

            # Start span
            otel_span = self._tracer.start_span(name, kind=kind, attributes=attrs)
            self._active_otel_spans[span_id] = otel_span

            return otel_span
        except Exception as e:
            logger.debug("Failed to start OTEL span: %s", e)
            return None

    def end_otel_span(
        self,
        span_id: str,
        status: "SpanStatus",
        error: str | None = None,
    ):
        """End an OpenTelemetry span."""
        otel_span = self._active_otel_spans.pop(span_id, None)
        if not otel_span:
            return

        try:
            # Set status
            if status == "failed" or error:
                otel_span.set_status(Status(StatusCode.ERROR, error))
            else:
                otel_span.set_status(Status(StatusCode.OK))

            otel_span.end()
        except Exception as e:
            logger.debug("Failed to end OTEL span: %s", e)

    def add_event(self, span_id: str, event_name: str, attributes: dict[str, Any] | None = None):
        """Add an event to an OpenTelemetry span."""
        otel_span = self._active_otel_spans.get(span_id)
        if otel_span:
            try:
                otel_span.add_event(event_name, attributes or {})
            except Exception as e:
                logger.debug("Failed to add OTEL event: %s", e)

    def shutdown(self):
        """Shutdown the OpenTelemetry provider."""
        if self._provider:
            try:
                self._provider.shutdown()
            except Exception as e:
                logger.debug("Failed to shutdown OTEL provider: %s", e)


# Global OTEL bridge instance
_otel_bridge: OpenTelemetryBridge | None = None


def get_otel_bridge() -> OpenTelemetryBridge:
    """Get the global OpenTelemetry bridge instance."""
    global _otel_bridge
    if _otel_bridge is None:
        _otel_bridge = OpenTelemetryBridge()
    return _otel_bridge


router = APIRouter(prefix="/api/traces", tags=["Execution Tracer"])


# ============================================================================
# TRACE TYPES
# ============================================================================


class TraceType(StrEnum):
    AGENT_TASK = "agent_task"
    WORKFLOW = "workflow"
    LLM_INFERENCE = "llm_inference"
    API_REQUEST = "api_request"
    HANDOFF = "handoff"
    COORDINATION = "coordination"


class SpanStatus(StrEnum):
    STARTED = "started"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Span:
    """A single unit of work within a trace."""

    span_id: str
    trace_id: str
    parent_span_id: str | None = None
    name: str = ""
    type: str = ""
    status: SpanStatus = SpanStatus.STARTED
    started_at: float = 0.0
    ended_at: float | None = None
    duration_ms: float | None = None
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    agent_id: str | None = None
    coordination_metrics: dict[str, float] = field(default_factory=dict)
    tokens_used: int = 0
    cost_usd: float = 0.0


@dataclass
class Trace:
    """A complete execution trace containing multiple spans."""

    trace_id: str
    type: TraceType
    name: str = ""
    status: SpanStatus = SpanStatus.STARTED
    started_at: float = 0.0
    ended_at: float | None = None
    duration_ms: float | None = None
    spans: list[Span] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    user_id: str | None = None
    session_id: str | None = None
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    coordination_summary: dict[str, float] = field(default_factory=dict)


# ============================================================================
# TRACE STORE
# ============================================================================


class TraceStore:
    """In-memory trace store with configurable retention."""

    def __init__(self, max_traces: int = 10000):
        self._traces: dict[str, Trace] = {}
        self._trace_order: deque = deque()
        self._active_spans: dict[str, Span] = {}
        self._max_traces = max_traces

    def create_trace(
        self,
        trace_type: TraceType,
        name: str = "",
        user_id: str | None = None,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        trace_id = str(uuid.uuid4())
        trace = Trace(
            trace_id=trace_id,
            type=trace_type,
            name=name,
            started_at=time.time(),
            user_id=user_id,
            session_id=session_id,
            metadata=metadata or {},
        )
        self._traces[trace_id] = trace
        self._trace_order.append(trace_id)

        # Evict old traces
        while len(self._traces) > self._max_traces:
            old_id = self._trace_order.popleft()
            self._traces.pop(old_id, None)

        return trace_id

    def start_span(
        self,
        trace_id: str,
        name: str,
        span_type: str = "",
        parent_span_id: str | None = None,
        input_data: dict[str, Any] | None = None,
        agent_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        span_id = str(uuid.uuid4())[:12]
        span = Span(
            span_id=span_id,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            name=name,
            type=span_type,
            started_at=time.time(),
            input_data=input_data or {},
            agent_id=agent_id,
            metadata=metadata or {},
        )
        self._active_spans[span_id] = span

        if trace_id in self._traces:
            self._traces[trace_id].spans.append(span)

        # Bridge to OpenTelemetry if enabled
        otel_bridge = get_otel_bridge()
        if otel_bridge.is_enabled():
            otel_bridge.start_otel_span(
                span_id=span_id,
                name=name,
                span_type=span_type,
                parent_span_id=parent_span_id,
                attributes={
                    "helix.trace_id": trace_id,
                    "helix.agent_id": agent_id or "",
                },
            )

        return span_id

    def end_span(
        self,
        span_id: str,
        status: SpanStatus = SpanStatus.COMPLETED,
        output_data: dict[str, Any] | None = None,
        error: str | None = None,
        tokens_used: int = 0,
        cost_usd: float = 0.0,
        coordination_metrics: dict[str, float] | None = None,
    ):
        span = self._active_spans.pop(span_id, None)
        if not span:
            return

        span.status = status
        span.ended_at = time.time()
        span.duration_ms = (span.ended_at - span.started_at) * 1000
        span.output_data = output_data or {}
        span.error = error
        span.tokens_used = tokens_used
        span.cost_usd = cost_usd
        span.coordination_metrics = coordination_metrics or {}

        # Update trace totals
        trace = self._traces.get(span.trace_id)
        if trace:
            trace.total_tokens += tokens_used
            trace.total_cost_usd += cost_usd

        # Bridge to OpenTelemetry if enabled
        otel_bridge = get_otel_bridge()
        if otel_bridge.is_enabled():
            otel_bridge.end_otel_span(
                span_id=span_id,
                status=status.value if isinstance(status, SpanStatus) else status,
                error=error,
            )

    def end_trace(self, trace_id: str, status: SpanStatus = SpanStatus.COMPLETED):
        trace = self._traces.get(trace_id)
        if not trace:
            return

        trace.status = status
        trace.ended_at = time.time()
        trace.duration_ms = (trace.ended_at - trace.started_at) * 1000

        # Calculate coordination summary
        all_metrics: dict[str, list[float]] = defaultdict(list)
        for span in trace.spans:
            for key, val in span.coordination_metrics.items():
                all_metrics[key].append(val)
        trace.coordination_summary = {k: sum(v) / len(v) for k, v in all_metrics.items() if v}

    def add_event(self, span_id: str, event_name: str, data: dict[str, Any] | None = None):
        span = self._active_spans.get(span_id)
        if span:
            span.events.append(
                {
                    "name": event_name,
                    "timestamp": time.time(),
                    "data": data or {},
                }
            )

    def get_trace(self, trace_id: str) -> Trace | None:
        return self._traces.get(trace_id)

    def list_traces(
        self,
        trace_type: TraceType | None = None,
        user_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Trace]:
        traces = list(self._traces.values())

        if trace_type:
            traces = [t for t in traces if t.type == trace_type]
        if user_id:
            traces = [t for t in traces if t.user_id == user_id]

        # Sort by most recent first
        traces.sort(key=lambda t: t.started_at, reverse=True)
        return traces[offset : offset + limit]

    def get_stats(self) -> dict[str, Any]:
        traces = list(self._traces.values())
        completed = [t for t in traces if t.status == SpanStatus.COMPLETED]
        failed = [t for t in traces if t.status == SpanStatus.FAILED]

        type_counts = defaultdict(int)
        for t in traces:
            type_counts[t.type.value] += 1

        avg_duration = 0.0
        if completed:
            durations = [t.duration_ms for t in completed if t.duration_ms]
            avg_duration = sum(durations) / len(durations) if durations else 0.0

        return {
            "total_traces": len(traces),
            "active_traces": len([t for t in traces if t.status in (SpanStatus.STARTED, SpanStatus.RUNNING)]),
            "completed_traces": len(completed),
            "failed_traces": len(failed),
            "total_spans": sum(len(t.spans) for t in traces),
            "total_tokens": sum(t.total_tokens for t in traces),
            "total_cost_usd": round(sum(t.total_cost_usd for t in traces), 4),
            "avg_duration_ms": round(avg_duration, 2),
            "type_breakdown": dict(type_counts),
            "active_spans": len(self._active_spans),
        }


# Singleton
_trace_store: TraceStore | None = None


def get_trace_store() -> TraceStore:
    global _trace_store
    if _trace_store is None:
        _trace_store = TraceStore()
    return _trace_store


# ============================================================================
# API ROUTES
# ============================================================================


@router.get("/")
async def list_traces(
    type: str | None = Query(None, description="Filter by trace type"),
    user_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List execution traces with optional filtering."""
    store = get_trace_store()
    trace_type = TraceType(type) if type else None
    traces = store.list_traces(trace_type=trace_type, user_id=user_id, limit=limit, offset=offset)

    return {
        "traces": [
            {
                "trace_id": t.trace_id,
                "type": t.type.value,
                "name": t.name,
                "status": t.status.value,
                "started_at": datetime.fromtimestamp(t.started_at, tz=UTC).isoformat(),
                "duration_ms": t.duration_ms,
                "span_count": len(t.spans),
                "total_tokens": t.total_tokens,
                "total_cost_usd": t.total_cost_usd,
                "user_id": t.user_id,
                "coordination_summary": t.coordination_summary,
            }
            for t in traces
        ],
        "total": len(traces),
        "limit": limit,
        "offset": offset,
    }


@router.get("/stats")
async def get_trace_stats():
    """Get aggregate trace statistics."""
    store = get_trace_store()
    return store.get_stats()


@router.get("/otel/status")
async def get_otel_status():
    """Get OpenTelemetry configuration and status."""
    otel_bridge = get_otel_bridge()
    config = otel_bridge.config

    return {
        "available": OTEL_AVAILABLE,
        "enabled": otel_bridge.is_enabled(),
        "config": {
            "service_name": config.service_name,
            "exporter_type": config.exporter_type,
            "otlp_endpoint": config.otlp_endpoint if config.exporter_type == "otlp" else None,
            "jaeger_host": config.jaeger_host if config.exporter_type == "jaeger" else None,
            "jaeger_port": config.jaeger_port if config.exporter_type == "jaeger" else None,
            "zipkin_url": config.zipkin_url if config.exporter_type == "zipkin" else None,
            "sample_rate": config.sample_rate,
        },
        "active_otel_spans": len(otel_bridge._active_otel_spans),
    }


@router.post("/otel/reload")
async def reload_otel_config():
    """Reload OpenTelemetry configuration from environment."""
    global _otel_bridge
    if _otel_bridge:
        _otel_bridge.shutdown()
    _otel_bridge = OpenTelemetryBridge()

    return {
        "success": True,
        "enabled": _otel_bridge.is_enabled(),
        "message": "OpenTelemetry configuration reloaded",
    }


# ============================================================================
# TRACE CONTEXT PROPAGATION
# ============================================================================


def get_trace_context(span_id: str | None = None) -> dict[str, str]:
    """
    Get trace context for propagation across services.

    Returns a dict with trace headers that can be injected into
    HTTP requests or message headers for distributed tracing.
    """
    store = get_trace_store()
    context = {
        "helix-trace-enabled": "true",
    }

    if span_id and span_id in store._active_spans:
        span = store._active_spans[span_id]
        context["helix-trace-id"] = span.trace_id
        context["helix-span-id"] = span_id
        context["helix-parent-span-id"] = span.parent_span_id or ""

    # Also include W3C TraceContext if OTEL is enabled
    if OTEL_AVAILABLE and trace:
        try:
            current_span = trace.get_current_span()
            if current_span and current_span.get_span_context().is_valid:
                ctx = current_span.get_span_context()
                context["traceparent"] = f"00-{ctx.trace_id:032x}-{ctx.span_id:016x}-01"
        except Exception as e:
            logger.debug("Failed to get W3C trace context: %s", e)

    return context


def inject_trace_context(headers: dict[str, str], span_id: str | None = None) -> dict[str, str]:
    """
    Inject trace context into HTTP headers.

    Usage:
        headers = {"Authorization": "Bearer ..."}
        headers = inject_trace_context(headers, current_span_id)
    """
    context = get_trace_context(span_id)
    headers.update(context)
    return headers


@contextmanager
def trace_context_injector(span_id: str) -> Generator[dict[str, str], None, None]:
    """
    Context manager for trace context injection.

    Usage:
        with trace_context_injector(span_id) as headers:
            await http_client.post(url, headers=headers, json=data)
    """
    context = get_trace_context(span_id)
    try:
        yield context
    finally:
        pass  # Placeholder for future span cleanup (e.g., flushing buffers)


@router.get("/{trace_id}")
async def get_trace(trace_id: str):
    """Get a complete trace with all spans."""
    store = get_trace_store()
    trace = store.get_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")

    return {
        "trace_id": trace.trace_id,
        "type": trace.type.value,
        "name": trace.name,
        "status": trace.status.value,
        "started_at": datetime.fromtimestamp(trace.started_at, tz=UTC).isoformat(),
        "ended_at": datetime.fromtimestamp(trace.ended_at, tz=UTC).isoformat() if trace.ended_at else None,
        "duration_ms": trace.duration_ms,
        "total_tokens": trace.total_tokens,
        "total_cost_usd": trace.total_cost_usd,
        "coordination_summary": trace.coordination_summary,
        "metadata": trace.metadata,
        "spans": [
            {
                "span_id": s.span_id,
                "parent_span_id": s.parent_span_id,
                "name": s.name,
                "type": s.type,
                "status": s.status.value,
                "started_at": datetime.fromtimestamp(s.started_at, tz=UTC).isoformat(),
                "ended_at": datetime.fromtimestamp(s.ended_at, tz=UTC).isoformat() if s.ended_at else None,
                "duration_ms": s.duration_ms,
                "input_data": s.input_data,
                "output_data": s.output_data,
                "error": s.error,
                "agent_id": s.agent_id,
                "tokens_used": s.tokens_used,
                "cost_usd": s.cost_usd,
                "coordination_metrics": s.coordination_metrics,
                "events": s.events,
                "metadata": s.metadata,
            }
            for s in trace.spans
        ],
    }


@router.get("/{trace_id}/timeline")
async def get_trace_timeline(trace_id: str):
    """Get a timeline view of a trace for visualization."""
    store = get_trace_store()
    trace = store.get_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")

    # Build a tree structure from spans
    span_map = {s.span_id: s for s in trace.spans}  # noqa: F841 — available for tree building
    root_spans = [s for s in trace.spans if not s.parent_span_id]

    def build_tree(span: Span) -> dict[str, Any]:
        children = [s for s in trace.spans if s.parent_span_id == span.span_id]
        return {
            "span_id": span.span_id,
            "name": span.name,
            "type": span.type,
            "status": span.status.value,
            "started_at": span.started_at,
            "duration_ms": span.duration_ms or 0,
            "agent_id": span.agent_id,
            "tokens_used": span.tokens_used,
            "error": span.error,
            "coordination_metrics": span.coordination_metrics,
            "children": [build_tree(c) for c in children],
        }

    return {
        "trace_id": trace.trace_id,
        "name": trace.name,
        "type": trace.type.value,
        "total_duration_ms": trace.duration_ms,
        "timeline": [build_tree(s) for s in root_spans],
    }


@router.get("/{trace_id}/stream")
async def stream_trace(trace_id: str):
    """Stream trace updates via SSE for live monitoring."""
    store = get_trace_store()
    trace = store.get_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")

    async def event_generator():
        last_span_count = 0
        while True:
            current_trace = store.get_trace(trace_id)
            if not current_trace:
                break

            if len(current_trace.spans) > last_span_count:
                new_spans = current_trace.spans[last_span_count:]
                for span in new_spans:
                    data = json.dumps(
                        {
                            "event": "span_update",
                            "span_id": span.span_id,
                            "name": span.name,
                            "status": span.status.value,
                            "duration_ms": span.duration_ms,
                            "agent_id": span.agent_id,
                        }
                    )
                    yield f"data: {data}\n\n"
                last_span_count = len(current_trace.spans)

            if current_trace.status in (SpanStatus.COMPLETED, SpanStatus.FAILED):
                data = json.dumps(
                    {
                        "event": "trace_complete",
                        "status": current_trace.status.value,
                        "duration_ms": current_trace.duration_ms,
                        "total_tokens": current_trace.total_tokens,
                    }
                )
                yield f"data: {data}\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
