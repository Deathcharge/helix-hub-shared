# NOTE: This service is not currently wired to any route.
# The convenience functions (clean_message, clean_text) are imported
# via services/__init__.py lazy getter but never called by any route
# or cron job. Wire to a data preprocessing pipeline or remove.
"""
Data Hygiene Service
Cleans and normalizes text data for agent processing and analysis.
"""

import logging
import os
import re
import statistics
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


class DataHygiene:
    """
    Cleans text data by removing noise, keyboard artifacts, and invalid content.
    Used for preprocessing agent messages and coordination data streams.
    """

    def __init__(self, strip_non_ascii: bool = False) -> None:
        """
        Initialize the data hygiene processor.

        Args:
            strip_non_ascii: If True, removes non-ASCII characters (including emojis)
        """
        self.strip_non_ascii = strip_non_ascii
        self.stats = {
            "lines_processed": 0,
            "lines_cleaned": 0,
            "lines_removed": 0,
            "chars_removed": 0,
        }

    def clean_line(self, text: str) -> str:
        """
        Clean a single line of text.

        Removes:
        - Excessive whitespace
        - Repeated characters (keyboard babble)
        - Single-token spam
        - Optional: non-ASCII characters

        Args:
            text: Raw text to clean

        Returns:
            Cleaned text or empty string if line should be removed
        """
        original_len = len(text)

        # Collapse whitespace & stray punctuation
        t = re.sub(r"\s+", " ", text)

        # Remove repeated letters/keys like tttttt or lolololol beyond 4x
        t = re.sub(r"(\w)\1{3,}", r"\1\1", t)

        # Optionally strip non-ASCII (emojis, special chars)
        if self.strip_non_ascii:
            t = re.sub(r"[^\x00-\x7F]+", " ", t)

        # Collapse multiple spaces again after substitutions
        t = re.sub(r"\s+", " ", t)

        # Check for keyboard runaway (same token repeated)
        tokens = t.split()
        if len(tokens) > 4 and len(set(tokens)) < 2:
            self.stats["lines_removed"] += 1
            return ""  # Likely keyboard runaway

        result = t.strip()
        self.stats["chars_removed"] += original_len - len(result)

        return result

    def clean_text(self, text: str) -> str:
        """
        Clean a block of text (multiple lines).

        Args:
            text: Raw text block

        Returns:
            Cleaned text with noise removed
        """
        lines = text.split("\n")
        cleaned_lines = []

        for line in lines:
            self.stats["lines_processed"] += 1
            cleaned = self.clean_line(line)
            if cleaned:
                cleaned_lines.append(cleaned)
                self.stats["lines_cleaned"] += 1
            else:
                self.stats["lines_removed"] += 1

        return "\n".join(cleaned_lines)

    def clean_message(self, message: str) -> str:
        """
        Clean a single user/agent message.
        Preserves message even if short, but removes noise.

        Args:
            message: Raw message text

        Returns:
            Cleaned message
        """
        # For single messages, be less aggressive
        t = re.sub(r"\s+", " ", message)
        t = re.sub(r"(\w)\1{4,}", r"\1\1\1", t)  # Allow up to 3 repeats
        return t.strip()

    def clean_file(self, input_path: str, output_path: str) -> dict[str, int]:
        """
        Clean a file and write to output path.

        Args:
            input_path: Path to raw file
            output_path: Path for cleaned output

        Returns:
            Statistics about cleaning
        """
        with open(input_path, encoding="utf-8") as f:
            raw_content = f.read()

        cleaned_content = self.clean_text(raw_content)

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(cleaned_content)

        logger.info("Cleaned %s → %s", input_path, output_path)
        return self.get_stats()

    def get_stats(self) -> dict[str, int]:
        """Get cleaning statistics."""
        return self.stats.copy()

    def reset_stats(self):
        """Reset statistics counters."""
        self.stats = {
            "lines_processed": 0,
            "lines_cleaned": 0,
            "lines_removed": 0,
            "chars_removed": 0,
        }


class NeutralStandardCalculator:
    """
    Calculates neutral baseline standards from analysis data.
    Used for UCF harmony/tone baseline comparisons.
    """

    def __init__(self) -> None:
        self.baseline: dict[str, Any] | None = None
        self.history: list[dict[str, Any]] = []

    def calculate_from_distribution(self, distribution: dict[str, int], total: int | None = None) -> dict[str, Any]:
        """
        Calculate neutral standard from a distribution.

        Args:
            distribution: Dict of category → count
            total: Optional total count (calculated if not provided)

        Returns:
            Baseline metrics including mean, stdev, and ratios
        """
        if total is None:
            total = sum(distribution.values()) or 1

        ratios = {k: v / total for k, v in distribution.items()}

        values = list(ratios.values())
        baseline = {
            "total": total,
            "mean": statistics.mean(values) if values else 0,
            "stdev": statistics.pstdev(values) if len(values) > 1 else 0,
            "min": min(values) if values else 0,
            "max": max(values) if values else 0,
            "ratios": ratios,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        return baseline

    def calculate_ucf_baseline(self, ucf_samples: list[dict[str, float]]) -> dict[str, Any]:
        """
        Calculate UCF baseline from historical samples.

        Args:
            ucf_samples: List of UCF state dicts with harmony, resilience, etc.

        Returns:
            Baseline for each UCF field
        """
        if not ucf_samples:
            return {"error": "No samples provided"}

        fields = ["velocity", "harmony", "resilience", "throughput", "focus", "friction"]
        baseline = {}

        for field in fields:
            values = [s.get(field, 0) for s in ucf_samples if field in s]
            if values:
                baseline[field] = {
                    "mean": statistics.mean(values),
                    "stdev": statistics.pstdev(values) if len(values) > 1 else 0,
                    "min": min(values),
                    "max": max(values),
                    "samples": len(values),
                }

        baseline["calculated_at"] = datetime.now(UTC).isoformat()
        baseline["total_samples"] = len(ucf_samples)

        self.baseline = baseline
        self.history.append(baseline)

        return baseline

    def compare_to_baseline(self, current: dict[str, float], baseline: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Compare current UCF state to baseline.

        Args:
            current: Current UCF state
            baseline: Baseline to compare against (uses stored if not provided)

        Returns:
            Comparison with drift indicators
        """
        baseline = baseline or self.baseline
        if not baseline:
            return {"error": "No baseline available"}

        comparison = {}

        for field, value in current.items():
            if field in baseline and isinstance(baseline[field], dict):
                field_baseline = baseline[field]
                mean = field_baseline.get("mean", value)
                stdev = field_baseline.get("stdev", 0)

                # Calculate z-score (how many stdevs from mean)
                if stdev > 0:
                    z_score = (value - mean) / stdev
                else:
                    z_score = 0 if value == mean else (1 if value > mean else -1)

                comparison[field] = {
                    "current": value,
                    "baseline_mean": mean,
                    "baseline_stdev": stdev,
                    "z_score": z_score,
                    "drift": self._classify_drift(z_score),
                }

        return comparison

    def _classify_drift(self, z_score: float) -> str:
        """Classify the drift level based on z-score."""
        if abs(z_score) < 1:
            return "normal"
        elif abs(z_score) < 2:
            return "slight"
        elif abs(z_score) < 3:
            return "moderate"
        else:
            return "significant"


class CleaningStats:
    """
    Tracks and visualizes data cleaning statistics.
    """

    def __init__(self) -> None:
        self.file_stats: list[dict[str, Any]] = []

    def add_file_stats(self, filename: str, raw_lines: int, clean_lines: int):
        """Add statistics for a cleaned file."""
        self.file_stats.append(
            {
                "filename": filename,
                "raw_lines": raw_lines,
                "clean_lines": clean_lines,
                "removed_lines": raw_lines - clean_lines,
                "keep_ratio": clean_lines / raw_lines if raw_lines > 0 else 1.0,
            }
        )

    def get_summary(self) -> dict[str, Any]:
        """Get summary statistics across all files."""
        if not self.file_stats:
            return {"files": 0}

        total_raw = sum(f["raw_lines"] for f in self.file_stats)
        total_clean = sum(f["clean_lines"] for f in self.file_stats)

        return {
            "files": len(self.file_stats),
            "total_raw_lines": total_raw,
            "total_clean_lines": total_clean,
            "total_removed": total_raw - total_clean,
            "overall_keep_ratio": total_clean / total_raw if total_raw > 0 else 1.0,
            "file_details": self.file_stats,
        }

    def generate_report(self) -> str:
        """Generate a text report of cleaning statistics."""
        summary = self.get_summary()

        lines = [
            "=" * 50,
            "DATA HYGIENE REPORT",
            "=" * 50,
            f"Files processed: {summary['files']}",
            f"Total lines (raw): {summary['total_raw_lines']}",
            f"Total lines (clean): {summary['total_clean_lines']}",
            f"Lines removed: {summary['total_removed']}",
            f"Keep ratio: {summary['overall_keep_ratio']:.1%}",
            "-" * 50,
        ]

        for f in self.file_stats:
            lines.append(f"  {f['filename']}: {f['clean_lines']}/{f['raw_lines']} ({f['keep_ratio']:.1%} kept)")

        lines.append("=" * 50)
        return "\n".join(lines)


# Convenience functions


def clean_message(message: str) -> str:
    """Quick clean a single message."""
    hygiene = DataHygiene(strip_non_ascii=False)
    return hygiene.clean_message(message)


def clean_text(text: str, strip_non_ascii: bool = False) -> str:
    """Quick clean a text block."""
    hygiene = DataHygiene(strip_non_ascii=strip_non_ascii)
    return hygiene.clean_text(text)


def calculate_ucf_baseline(samples: list[dict[str, float]]) -> dict[str, Any]:
    """Quick calculate UCF baseline from samples."""
    calc = NeutralStandardCalculator()
    return calc.calculate_ucf_baseline(samples)
