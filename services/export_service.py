"""
Export Service - Generate PDF/JSON/CSV reports for Helix data.

Supports exporting:
- Discovery results and analysis
- Coordination metrics history
- Agent conversation transcripts
- Workflow execution logs

Features:
- Multiple formats (PDF, JSON, CSV)
- Customizable templates
- Branding options
- Scheduled exports
"""

import csv
import io
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Optional PDF support
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False
    logger.warning("reportlab not installed - PDF export unavailable")


@dataclass
class ExportOptions:
    """Options for export generation."""

    format: str = "json"  # json, csv, pdf
    include_metadata: bool = True
    include_timestamps: bool = True
    branding: bool = True
    title: str | None = None


@dataclass
class ExportResult:
    """Result of an export operation."""

    success: bool
    format: str
    filename: str
    content_type: str
    data: bytes
    size_bytes: int
    generated_at: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "format": self.format,
            "filename": self.filename,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "generated_at": self.generated_at,
            "error": self.error,
        }


class ExportService:
    """Service for generating exportable reports."""

    CONTENT_TYPES = {
        "json": "application/json",
        "csv": "text/csv",
        "pdf": "application/pdf",
    }

    def __init__(self):
        self.logger = logging.getLogger("ExportService")

    def export_discovery_results(
        self,
        results: list[dict[str, Any]],
        options: ExportOptions | None = None,
    ) -> ExportResult:
        """Export discovery results to specified format."""
        opts = options or ExportOptions()
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"helix_discovery_{timestamp}.{opts.format}"

        try:
            if opts.format == "json":
                data = self._export_json(results, opts)
            elif opts.format == "csv":
                data = self._export_csv(results, opts)
            elif opts.format == "pdf":
                data = self._export_pdf(
                    results,
                    opts,
                    title=opts.title or "Helix Discovery Report",
                )
            else:
                raise ValueError(f"Unsupported format: {opts.format}")

            return ExportResult(
                success=True,
                format=opts.format,
                filename=filename,
                content_type=self.CONTENT_TYPES.get(opts.format, "application/octet-stream"),
                data=data,
                size_bytes=len(data),
                generated_at=datetime.now(UTC).isoformat(),
            )

        except Exception as e:
            self.logger.error("Export failed: %s", e)
            return ExportResult(
                success=False,
                format=opts.format,
                filename=filename,
                content_type="text/plain",
                data=b"",
                size_bytes=0,
                generated_at=datetime.now(UTC).isoformat(),
                error=str(e),
            )

    def export_coordination_metrics(
        self,
        metrics: list[dict[str, Any]],
        options: ExportOptions | None = None,
    ) -> ExportResult:
        """Export coordination metrics history."""
        opts = options or ExportOptions()
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        filename = f"helix_coordination_{timestamp}.{opts.format}"

        try:
            if opts.format == "json":
                data = self._export_json(metrics, opts)
            elif opts.format == "csv":
                data = self._export_csv(metrics, opts)
            elif opts.format == "pdf":
                data = self._export_pdf(
                    metrics,
                    opts,
                    title=opts.title or "Helix Coordination Metrics",
                )
            else:
                raise ValueError(f"Unsupported format: {opts.format}")

            return ExportResult(
                success=True,
                format=opts.format,
                filename=filename,
                content_type=self.CONTENT_TYPES.get(opts.format, "application/octet-stream"),
                data=data,
                size_bytes=len(data),
                generated_at=datetime.now(UTC).isoformat(),
            )

        except Exception as e:
            self.logger.error("Coordination export failed: %s", e)
            return ExportResult(
                success=False,
                format=opts.format,
                filename=filename,
                content_type="text/plain",
                data=b"",
                size_bytes=0,
                generated_at=datetime.now(UTC).isoformat(),
                error=str(e),
            )

    def export_conversation(
        self,
        messages: list[dict[str, Any]],
        agent_name: str = "Helix Agent",
        options: ExportOptions | None = None,
    ) -> ExportResult:
        """Export agent conversation transcript."""
        opts = options or ExportOptions()
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        safe_name = agent_name.lower().replace(" ", "_")
        filename = f"helix_conversation_{safe_name}_{timestamp}.{opts.format}"

        try:
            # Enrich messages with agent context
            enriched = {
                "agent": agent_name,
                "exported_at": datetime.now(UTC).isoformat(),
                "message_count": len(messages),
                "messages": messages,
            }

            if opts.format == "json":
                data = self._export_json(enriched, opts)
            elif opts.format == "csv":
                # Flatten for CSV
                data = self._export_csv(messages, opts)
            elif opts.format == "pdf":
                data = self._export_conversation_pdf(
                    messages,
                    agent_name,
                    opts,
                )
            else:
                raise ValueError(f"Unsupported format: {opts.format}")

            return ExportResult(
                success=True,
                format=opts.format,
                filename=filename,
                content_type=self.CONTENT_TYPES.get(opts.format, "application/octet-stream"),
                data=data,
                size_bytes=len(data),
                generated_at=datetime.now(UTC).isoformat(),
            )

        except Exception as e:
            self.logger.error("Conversation export failed: %s", e)
            return ExportResult(
                success=False,
                format=opts.format,
                filename=filename,
                content_type="text/plain",
                data=b"",
                size_bytes=0,
                generated_at=datetime.now(UTC).isoformat(),
                error=str(e),
            )

    def _export_json(self, data: Any, options: ExportOptions) -> bytes:
        """Export data as JSON."""
        output = {
            "data": data,
            "metadata": {
                "exported_at": datetime.now(UTC).isoformat(),
                "format": "json",
                "version": "1.0",
                "source": "Helix Collective",
            },
        }
        return json.dumps(output, indent=2, default=str).encode("utf-8")

    def _export_csv(self, data: list[dict[str, Any]], options: ExportOptions) -> bytes:
        """Export data as CSV."""
        if not data:
            return b"No data\n"

        output = io.StringIO()

        # Flatten nested dicts for CSV
        flattened = []
        for item in data:
            flat = {}
            for key, value in item.items():
                if isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        flat[f"{key}_{sub_key}"] = sub_value
                elif isinstance(value, list):
                    flat[key] = "; ".join(str(v) for v in value)
                else:
                    flat[key] = value
            flattened.append(flat)

        # Get all unique keys
        all_keys = set()
        for item in flattened:
            all_keys.update(item.keys())
        fieldnames = sorted(all_keys)

        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flattened)

        return output.getvalue().encode("utf-8")

    def _export_pdf(
        self,
        data: Any,
        options: ExportOptions,
        title: str = "Helix Report",
    ) -> bytes:
        """Export data as PDF."""
        if not HAS_REPORTLAB:
            raise ImportError("reportlab is required for PDF export. Install with: pip install reportlab")

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        # Title
        title_style = ParagraphStyle(
            "CustomTitle",
            parent=styles["Heading1"],
            fontSize=24,
            spaceAfter=30,
            textColor=colors.HexColor("#8B5CF6"),
        )
        story.append(Paragraph(title, title_style))

        # Branding
        if options.branding:
            branding_style = ParagraphStyle(
                "Branding",
                parent=styles["Normal"],
                fontSize=10,
                textColor=colors.gray,
            )
            story.append(Paragraph("Generated by Helix Collective", branding_style))
            story.append(
                Paragraph(
                    f"Date: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
                    branding_style,
                )
            )
        story.append(Spacer(1, 0.5 * inch))

        # Convert data to table
        if isinstance(data, list) and data:
            # Get headers from first item
            if isinstance(data[0], dict):
                headers = list(data[0].keys())[:6]  # Limit columns
                table_data = [headers]
                for item in data[:50]:  # Limit rows
                    row = []
                    for h in headers:
                        val = item.get(h, "")
                        if isinstance(val, dict):
                            val = json.dumps(val)[:30] + "..."
                        elif isinstance(val, list):
                            val = ", ".join(str(v)[:20] for v in val[:3])
                        else:
                            val = str(val)[:40]
                        row.append(val)
                    table_data.append(row)

                table = Table(table_data)
                table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#8B5CF6")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                            ("FONTSIZE", (0, 0), (-1, 0), 10),
                            ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                            ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                            ("TEXTCOLOR", (0, 1), (-1, -1), colors.black),
                            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                            ("FONTSIZE", (0, 1), (-1, -1), 8),
                            ("GRID", (0, 0), (-1, -1), 1, colors.gray),
                        ]
                    )
                )
                story.append(table)
        elif isinstance(data, dict):
            # Key-value pairs
            for key, value in list(data.items())[:20]:
                story.append(
                    Paragraph(
                        f"<b>{key}:</b> {str(value)[:100]}",
                        styles["Normal"],
                    )
                )
                story.append(Spacer(1, 0.1 * inch))

        doc.build(story)
        return buffer.getvalue()

    def _export_conversation_pdf(
        self,
        messages: list[dict[str, Any]],
        agent_name: str,
        options: ExportOptions,
    ) -> bytes:
        """Export conversation as formatted PDF."""
        if not HAS_REPORTLAB:
            raise ImportError("reportlab is required for PDF export. Install with: pip install reportlab")

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        # Title
        title_style = ParagraphStyle(
            "ConvTitle",
            parent=styles["Heading1"],
            fontSize=20,
            spaceAfter=20,
            textColor=colors.HexColor("#8B5CF6"),
        )
        story.append(Paragraph(f"Conversation with {agent_name}", title_style))

        if options.branding:
            story.append(
                Paragraph(
                    f"Helix Collective | {datetime.now(UTC).strftime('%Y-%m-%d')}",
                    styles["Normal"],
                )
            )
        story.append(Spacer(1, 0.3 * inch))

        # Message styles
        user_style = ParagraphStyle(
            "User",
            parent=styles["Normal"],
            fontSize=10,
            leftIndent=20,
            textColor=colors.HexColor("#3B82F6"),
        )
        agent_style = ParagraphStyle(
            "Agent",
            parent=styles["Normal"],
            fontSize=10,
            leftIndent=20,
            textColor=colors.HexColor("#8B5CF6"),
        )
        timestamp_style = ParagraphStyle(
            "Timestamp",
            parent=styles["Normal"],
            fontSize=8,
            textColor=colors.gray,
        )

        for msg in messages[:100]:  # Limit messages
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:500]
            timestamp = msg.get("timestamp", "")

            # Role label
            story.append(
                Paragraph(
                    f"<b>{role.upper()}:</b>",
                    user_style if role == "user" else agent_style,
                )
            )
            # Content
            story.append(
                Paragraph(
                    content,
                    user_style if role == "user" else agent_style,
                )
            )
            # Timestamp
            if timestamp and options.include_timestamps:
                story.append(Paragraph(timestamp, timestamp_style))
            story.append(Spacer(1, 0.15 * inch))

        doc.build(story)
        return buffer.getvalue()


# Singleton instance
export_service = ExportService()
