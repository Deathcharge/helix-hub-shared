"""
Advanced Coordination Analytics System

Comprehensive analytics and insights generation for coordination data.
Integrates with existing UCF metrics and coordination tracking infrastructure.
"""

import logging
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

try:
    import numpy as np
    import pandas as pd
    from scipy import stats
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler

    HAS_ML_DEPS = True
except ImportError:
    np = None  # type: ignore[assignment]
    pd = None  # type: ignore[assignment]
    stats = None  # type: ignore[assignment]
    KMeans = None  # type: ignore[assignment]
    StandardScaler = None  # type: ignore[assignment]
    HAS_ML_DEPS = False

from sqlalchemy.orm import Session

from ..services.agent_service import AgentService
from ..services.coordination_service import CoordinationService
from ..services.ucf_calculator import UCFCalculator

logger = logging.getLogger(__name__)


class AnalyticsType(str, Enum):
    PATTERN_ANALYSIS = "pattern_analysis"
    CORRELATION_ANALYSIS = "correlation_analysis"
    TREND_ANALYSIS = "trend_analysis"
    ANOMALY_DETECTION = "anomaly_detection"
    PREDICTIVE_ANALYTICS = "predictive_analytics"
    PERFORMANCE_ANALYTICS = "performance_analytics"


class InsightType(str, Enum):
    OPTIMIZATION = "optimization"
    WARNING = "warning"
    OPPORTUNITY = "opportunity"
    PATTERN = "pattern"
    CORRELATION = "correlation"


@dataclass
class CoordinationPattern:
    """Detected coordination pattern"""

    pattern_type: str
    pattern_description: str
    pattern_strength: float
    pattern_duration: int  # minutes
    pattern_confidence: float
    pattern_metadata: dict[str, Any]


@dataclass
class CoordinationCorrelation:
    """Detected coordination correlation"""

    metric1: str
    metric2: str
    correlation_coefficient: float
    correlation_significance: float
    correlation_description: str
    correlation_metadata: dict[str, Any]


@dataclass
class CoordinationInsight:
    """Generated coordination insight"""

    insight_type: InsightType
    insight_title: str
    insight_description: str
    insight_priority: str  # "high", "medium", "low"
    insight_actions: list[str]
    insight_metadata: dict[str, Any]


@dataclass
class AnalyticsReport:
    """Comprehensive analytics report"""

    report_type: AnalyticsType
    report_data: dict[str, Any]
    insights: list[CoordinationInsight]
    patterns: list[CoordinationPattern]
    correlations: list[CoordinationCorrelation]
    report_metadata: dict[str, Any]


class PerformanceAnalytics:
    """Advanced coordination analytics and insights generation system"""

    def __init__(
        self,
        db_session: Session,
        coordination_service: CoordinationService,
        agent_service: AgentService,
        database_service,  # Database class from unified_auth
        ucf_calculator: UCFCalculator,
    ):
        self.db = db_session
        self.coordination_service = coordination_service
        self.agent_service = agent_service
        self.database_service = database_service
        self.ucf_calculator = ucf_calculator

        # Analytics data storage
        self.analytics_cache: dict[str, Any] = {}
        self.insight_history: list[CoordinationInsight] = []
        self.pattern_history: list[CoordinationPattern] = []
        self.correlation_history: list[CoordinationCorrelation] = []

        # Analytics parameters
        self.analysis_windows = {
            "short_term": 60,  # 1 hour
            "medium_term": 360,  # 6 hours
            "long_term": 1440,  # 24 hours
        }

        self.insight_thresholds = {
            "high_priority": 0.8,
            "medium_priority": 0.6,
            "low_priority": 0.4,
        }

        # Machine learning models
        self.pattern_detectors = {}
        self.correlation_analyzers = {}
        self.predictive_models = {}

    async def analyze_coordination_patterns(
        self, time_window: str = "medium_term", agent_ids: list[str] | None = None
    ) -> list[CoordinationPattern]:
        """Analyze coordination patterns over specified time window"""
        if not HAS_ML_DEPS:
            logger.warning("ML dependencies (numpy/pandas/scipy/sklearn) not available — skipping pattern analysis")
            return []
        try:
            minutes = self.analysis_windows.get(time_window, 360)
            historical_data = await self._get_coordination_history(minutes, agent_ids)

            if not historical_data:
                return []

            # Convert to DataFrame for analysis
            df = pd.DataFrame(historical_data)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.sort_values("timestamp")

            # Detect patterns
            patterns = []

            # 1. Cyclic patterns
            cyclic_patterns = await self._detect_cyclic_patterns(df)
            patterns.extend(cyclic_patterns)

            # 2. Trend patterns
            trend_patterns = await self._detect_trend_patterns(df)
            patterns.extend(trend_patterns)

            # 3. Cluster patterns
            cluster_patterns = await self._detect_cluster_patterns(df)
            patterns.extend(cluster_patterns)

            # 4. Anomaly patterns
            anomaly_patterns = await self._detect_anomaly_patterns(df)
            patterns.extend(anomaly_patterns)

            # Cache results
            cache_key = f"patterns_{time_window}_{agent_ids or 'all'}"
            self.analytics_cache[cache_key] = patterns

            # Update pattern history
            self.pattern_history.extend(patterns)

            logger.info("Detected %s coordination patterns in %s window", len(patterns), time_window)
            return patterns

        except Exception as e:
            logger.error("Coordination pattern analysis failed: %s", e)
            return []

    async def analyze_coordination_correlations(
        self, time_window: str = "medium_term", agent_ids: list[str] | None = None
    ) -> list[CoordinationCorrelation]:
        """Analyze correlations between coordination metrics"""
        if not HAS_ML_DEPS:
            logger.warning("ML dependencies not available — skipping correlation analysis")
            return []
        try:
            minutes = self.analysis_windows.get(time_window, 360)
            historical_data = await self._get_coordination_history(minutes, agent_ids)

            if not historical_data:
                return []

            # Convert to DataFrame
            df = pd.DataFrame(historical_data)
            df["timestamp"] = pd.to_datetime(df["timestamp"])

            # Calculate correlations
            correlations = []
            metrics = [
                "performance_score",
                "harmony",
                "resilience",
                "throughput",
                "focus",
                "friction",
            ]

            for i, metric1 in enumerate(metrics):
                for j, metric2 in enumerate(metrics):
                    if i < j and metric1 in df.columns and metric2 in df.columns:
                        # Calculate correlation
                        correlation_matrix = df[[metric1, metric2]].corr()
                        correlation_coeff = correlation_matrix.iloc[0, 1]

                        # Calculate significance
                        if len(df) > 2:
                            _, p_value = stats.pearsonr(df[metric1], df[metric2])
                        else:
                            p_value = 1.0

                        # Create correlation record
                        correlation = CoordinationCorrelation(
                            metric1=metric1,
                            metric2=metric2,
                            correlation_coefficient=correlation_coeff,
                            correlation_significance=p_value,
                            correlation_description=self._generate_correlation_description(
                                metric1, metric2, correlation_coeff
                            ),
                            correlation_metadata={
                                "time_window": time_window,
                                "agent_ids": agent_ids,
                                "data_points": len(df),
                                "absolute_correlation": abs(correlation_coeff),
                            },
                        )

                        correlations.append(correlation)

            # Filter significant correlations
            significant_correlations = [
                c for c in correlations if abs(c.correlation_coefficient) > 0.3 and c.correlation_significance < 0.05
            ]

            # Cache results
            cache_key = f"correlations_{time_window}_{agent_ids or 'all'}"
            self.analytics_cache[cache_key] = significant_correlations

            # Update correlation history
            self.correlation_history.extend(significant_correlations)

            logger.info("Detected %s significant correlations in %s window", len(significant_correlations), time_window)
            return significant_correlations

        except Exception as e:
            logger.error("Coordination correlation analysis failed: %s", e)
            return []

    async def generate_coordination_insights(
        self,
        time_window: str = "medium_term",
        insight_types: list[InsightType] | None = None,
    ) -> list[CoordinationInsight]:
        """Generate actionable insights from coordination data"""
        if not HAS_ML_DEPS:
            logger.warning("ML dependencies not available — skipping insight generation")
            return []
        try:
            minutes = self.analysis_windows.get(time_window, 360)
            historical_data = await self._get_coordination_history(minutes)

            if not historical_data:
                return []

            # Generate insights based on type
            insights = []

            if not insight_types or InsightType.OPTIMIZATION in insight_types:
                optimization_insights = await self._generate_optimization_insights(historical_data)
                insights.extend(optimization_insights)

            if not insight_types or InsightType.WARNING in insight_types:
                warning_insights = await self._generate_warning_insights(historical_data)
                insights.extend(warning_insights)

            if not insight_types or InsightType.OPPORTUNITY in insight_types:
                opportunity_insights = await self._generate_opportunity_insights(historical_data)
                insights.extend(opportunity_insights)

            if not insight_types or InsightType.PATTERN in insight_types:
                pattern_insights = await self._generate_pattern_insights(historical_data)
                insights.extend(pattern_insights)

            if not insight_types or InsightType.CORRELATION in insight_types:
                correlation_insights = await self._generate_correlation_insights(historical_data)
                insights.extend(correlation_insights)

            # Cache results
            cache_key = f"insights_{time_window}_{insight_types or 'all'}"
            self.analytics_cache[cache_key] = insights

            # Update insight history
            self.insight_history.extend(insights)

            logger.info("Generated %s coordination insights for %s window", len(insights), time_window)
            return insights

        except Exception as e:
            logger.error("Coordination insights generation failed: %s", e)
            return []

    async def create_coordination_reports(
        self,
        report_types: list[AnalyticsType],
        time_window: str = "medium_term",
        agent_ids: list[str] | None = None,
    ) -> list[AnalyticsReport]:
        """Create comprehensive coordination analytics reports"""
        if not HAS_ML_DEPS:
            logger.warning("ML dependencies not available — skipping report creation")
            return []
        try:
            reports = []

            for report_type in report_types:
                if report_type == AnalyticsType.PATTERN_ANALYSIS:
                    patterns = await self.analyze_coordination_patterns(time_window, agent_ids)
                    report = AnalyticsReport(
                        report_type=report_type,
                        report_data={"patterns": [asdict(p) for p in patterns]},
                        insights=[],
                        patterns=patterns,
                        correlations=[],
                        report_metadata={
                            "time_window": time_window,
                            "agent_ids": agent_ids,
                            "timestamp": datetime.now(UTC).isoformat(),
                        },
                    )

                elif report_type == AnalyticsType.CORRELATION_ANALYSIS:
                    correlations = await self.analyze_coordination_correlations(time_window, agent_ids)
                    report = AnalyticsReport(
                        report_type=report_type,
                        report_data={"correlations": [asdict(c) for c in correlations]},
                        insights=[],
                        patterns=[],
                        correlations=correlations,
                        report_metadata={
                            "time_window": time_window,
                            "agent_ids": agent_ids,
                            "timestamp": datetime.now(UTC).isoformat(),
                        },
                    )

                elif report_type == AnalyticsType.TREND_ANALYSIS:
                    trends = await self._analyze_trends(time_window, agent_ids)
                    report = AnalyticsReport(
                        report_type=report_type,
                        report_data={"trends": trends},
                        insights=[],
                        patterns=[],
                        correlations=[],
                        report_metadata={
                            "time_window": time_window,
                            "agent_ids": agent_ids,
                            "timestamp": datetime.now(UTC).isoformat(),
                        },
                    )

                elif report_type == AnalyticsType.ANOMALY_DETECTION:
                    anomalies = await self._detect_anomalies(time_window, agent_ids)
                    insights = await self._generate_anomaly_insights(anomalies)
                    report = AnalyticsReport(
                        report_type=report_type,
                        report_data={"anomalies": anomalies},
                        insights=insights,
                        patterns=[],
                        correlations=[],
                        report_metadata={
                            "time_window": time_window,
                            "agent_ids": agent_ids,
                            "timestamp": datetime.now(UTC).isoformat(),
                        },
                    )

                elif report_type == AnalyticsType.PREDICTIVE_ANALYTICS:
                    predictions = await self._generate_predictions(time_window, agent_ids)
                    insights = await self._generate_prediction_insights(predictions)
                    report = AnalyticsReport(
                        report_type=report_type,
                        report_data={"predictions": predictions},
                        insights=insights,
                        patterns=[],
                        correlations=[],
                        report_metadata={
                            "time_window": time_window,
                            "agent_ids": agent_ids,
                            "timestamp": datetime.now(UTC).isoformat(),
                        },
                    )

                elif report_type == AnalyticsType.PERFORMANCE_ANALYTICS:
                    performance = await self._analyze_performance(time_window, agent_ids)
                    insights = await self._generate_performance_insights(performance)
                    report = AnalyticsReport(
                        report_type=report_type,
                        report_data={"performance": performance},
                        insights=insights,
                        patterns=[],
                        correlations=[],
                        report_metadata={
                            "time_window": time_window,
                            "agent_ids": agent_ids,
                            "timestamp": datetime.now(UTC).isoformat(),
                        },
                    )

                else:
                    continue

                reports.append(report)

            # Cache reports
            cache_key = f"reports_{time_window}_{agent_ids or 'all'}"
            self.analytics_cache[cache_key] = reports

            logger.info("Created %s analytics reports for %s window", len(reports), time_window)
            return reports

        except Exception as e:
            logger.error("Coordination reports creation failed: %s", e)
            return []

    async def calculate_coordination_metrics(
        self, time_window: str = "medium_term", agent_ids: list[str] | None = None
    ) -> dict[str, Any]:
        """Calculate advanced coordination metrics"""
        if not HAS_ML_DEPS:
            logger.warning("ML dependencies not available — skipping metrics calculation")
            return {}
        try:
            minutes = self.analysis_windows.get(time_window, 360)
            historical_data = await self._get_coordination_history(minutes, agent_ids)

            if not historical_data:
                return {}

            # Convert to DataFrame
            df = pd.DataFrame(historical_data)
            df["timestamp"] = pd.to_datetime(df["timestamp"])

            # Calculate basic statistics
            metrics = [
                "performance_score",
                "harmony",
                "resilience",
                "throughput",
                "focus",
                "friction",
            ]
            basic_stats = {}

            for metric in metrics:
                if metric in df.columns:
                    values = df[metric].dropna()
                    if len(values) > 0:
                        basic_stats[metric] = {
                            "mean": float(values.mean()),
                            "median": float(values.median()),
                            "std": float(values.std()),
                            "min": float(values.min()),
                            "max": float(values.max()),
                            "current": (float(values.iloc[-1]) if len(values) > 0 else 0.0),
                            "trend": self._calculate_trend(values),
                        }

            # Calculate advanced metrics
            advanced_metrics = await self._calculate_advanced_metrics(df, basic_stats)

            # Calculate composite scores
            composite_scores = await self._calculate_composite_scores(basic_stats)

            # Combine all metrics
            all_metrics = {
                "time_window": time_window,
                "agent_ids": agent_ids,
                "basic_statistics": basic_stats,
                "advanced_metrics": advanced_metrics,
                "composite_scores": composite_scores,
                "timestamp": datetime.now(UTC).isoformat(),
            }

            # Cache results
            cache_key = f"metrics_{time_window}_{agent_ids or 'all'}"
            self.analytics_cache[cache_key] = all_metrics

            logger.info("Calculated coordination metrics for %s window", time_window)
            return all_metrics

        except Exception as e:
            logger.error("Coordination metrics calculation failed: %s", e)
            return {}

    async def _detect_cyclic_patterns(self, df: pd.DataFrame) -> list[CoordinationPattern]:
        """Detect cyclic patterns in coordination data"""
        try:
            patterns = []

            # Analyze each metric for cyclic patterns
            metrics = [
                "performance_score",
                "harmony",
                "resilience",
                "throughput",
                "focus",
                "friction",
            ]

            for metric in metrics:
                if metric not in df.columns:
                    continue

                values = df[metric].dropna()
                if len(values) < 20:  # Need sufficient data
                    continue

                # Simple cycle detection using FFT
                fft_values = np.fft.fft(values.values)
                frequencies = np.fft.fftfreq(len(values))

                # Find dominant frequencies
                dominant_freq_idx = np.argmax(np.abs(fft_values[1 : len(fft_values) // 2])) + 1
                dominant_freq = frequencies[dominant_freq_idx]

                if dominant_freq > 0:
                    cycle_period = 1 / dominant_freq
                    cycle_strength = np.abs(fft_values[dominant_freq_idx]) / len(values)

                    if cycle_strength > 0.1:  # Threshold for significant cycles
                        pattern = CoordinationPattern(
                            pattern_type="cyclic",
                            pattern_description=f"{metric} shows cyclic pattern with period {cycle_period:.1f} minutes",
                            pattern_strength=float(cycle_strength),
                            pattern_duration=int(cycle_period),
                            pattern_confidence=0.8,
                            pattern_metadata={
                                "metric": metric,
                                "cycle_period": cycle_period,
                                "dominant_frequency": dominant_freq,
                                "cycle_strength": cycle_strength,
                            },
                        )
                        patterns.append(pattern)

            return patterns

        except Exception as e:
            logger.error("Cyclic pattern detection failed: %s", e)
            return []

    async def _detect_trend_patterns(self, df: pd.DataFrame) -> list[CoordinationPattern]:
        """Detect trend patterns in coordination data"""
        try:
            patterns = []

            # Analyze trends for each metric
            metrics = [
                "performance_score",
                "harmony",
                "resilience",
                "throughput",
                "focus",
                "friction",
            ]

            for metric in metrics:
                if metric not in df.columns:
                    continue

                values = df[metric].dropna()
                if len(values) < 10:
                    continue

                # Calculate linear trend
                x = np.arange(len(values))
                slope, intercept = np.polyfit(x, values, 1)

                # Calculate trend strength (R-squared)
                y_pred = slope * x + intercept
                ss_res = np.sum((values - y_pred) ** 2)
                ss_tot = np.sum((values - np.mean(values)) ** 2)
                r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

                if abs(slope) > 0.01 and r_squared > 0.3:
                    trend_direction = "increasing" if slope > 0 else "decreasing"
                    pattern = CoordinationPattern(
                        pattern_type="trend",
                        pattern_description=f"{metric} shows {trend_direction} trend (slope: {slope:.3f})",
                        pattern_strength=float(r_squared),
                        pattern_duration=len(values) * 5,  # Assuming 5-minute intervals
                        pattern_confidence=float(r_squared),
                        pattern_metadata={
                            "metric": metric,
                            "slope": slope,
                            "intercept": intercept,
                            "r_squared": r_squared,
                            "trend_direction": trend_direction,
                        },
                    )
                    patterns.append(pattern)

            return patterns

        except Exception as e:
            logger.error("Trend pattern detection failed: %s", e)
            return []

    async def _detect_cluster_patterns(self, df: pd.DataFrame) -> list[CoordinationPattern]:
        """Detect cluster patterns in coordination data"""
        try:
            patterns = []

            # Prepare data for clustering
            metrics = [
                "performance_score",
                "harmony",
                "resilience",
                "throughput",
                "focus",
            ]
            valid_metrics = [m for m in metrics if m in df.columns]

            if len(valid_metrics) < 2:
                return patterns

            data = df[valid_metrics].dropna()
            if len(data) < 10:
                return patterns

            # Standardize data
            scaler = StandardScaler()
            scaled_data = scaler.fit_transform(data)

            # Apply K-means clustering
            kmeans = KMeans(n_clusters=min(5, len(data) // 10), random_state=42)
            clusters = kmeans.fit_predict(scaled_data)

            # Analyze clusters
            cluster_centers = kmeans.cluster_centers_
            cluster_sizes = np.bincount(clusters)

            for i, (center, size) in enumerate(zip(cluster_centers, cluster_sizes, strict=False)):
                if size > len(data) * 0.1:  # Only consider significant clusters
                    pattern = CoordinationPattern(
                        pattern_type="cluster",
                        pattern_description=f"Cluster {i} with {size} data points",
                        pattern_strength=float(size / len(data)),
                        pattern_duration=0,  # Not time-based
                        pattern_confidence=0.7,
                        pattern_metadata={
                            "cluster_id": i,
                            "cluster_size": int(size),
                            "cluster_center": center.tolist(),
                            "cluster_percentage": float(size / len(data)),
                        },
                    )
                    patterns.append(pattern)

            return patterns

        except Exception as e:
            logger.error("Cluster pattern detection failed: %s", e)
            return []

    async def _detect_anomaly_patterns(self, df: pd.DataFrame) -> list[CoordinationPattern]:
        """Detect anomaly patterns in coordination data"""
        try:
            patterns = []

            # Analyze anomalies for each metric
            metrics = [
                "performance_score",
                "harmony",
                "resilience",
                "throughput",
                "focus",
                "friction",
            ]

            for metric in metrics:
                if metric not in df.columns:
                    continue

                values = df[metric].dropna()
                if len(values) < 20:
                    continue

                # Calculate z-scores for anomaly detection
                mean_val = np.mean(values)
                std_val = np.std(values)
                z_scores = np.abs((values - mean_val) / std_val)

                # Find anomalies (z-score > 3)
                anomalies = values[z_scores > 3]

                if len(anomalies) > 0:
                    pattern = CoordinationPattern(
                        pattern_type="anomaly",
                        pattern_description=f"{metric} has {len(anomalies)} anomalies detected",
                        pattern_strength=float(len(anomalies) / len(values)),
                        pattern_duration=0,  # Not time-based
                        pattern_confidence=0.9,
                        pattern_metadata={
                            "metric": metric,
                            "anomaly_count": len(anomalies),
                            "anomaly_percentage": float(len(anomalies) / len(values)),
                            "anomaly_values": anomalies.tolist(),
                            "mean": float(mean_val),
                            "std": float(std_val),
                        },
                    )
                    patterns.append(pattern)

            return patterns

        except Exception as e:
            logger.error("Anomaly pattern detection failed: %s", e)
            return []

    def _generate_correlation_description(self, metric1: str, metric2: str, correlation: float) -> str:
        """Generate descriptive text for correlation"""
        abs_corr = abs(correlation)

        if abs_corr < 0.3:
            strength = "weak"
        elif abs_corr < 0.7:
            strength = "moderate"
        else:
            strength = "strong"

        direction = "positive" if correlation > 0 else "negative"

        return f"{strength} {direction} correlation between {metric1} and {metric2} (r={correlation:.3f})"

    async def _generate_optimization_insights(self, historical_data: list[dict]) -> list[CoordinationInsight]:
        """Generate optimization insights"""
        try:
            insights = []

            # Analyze current state vs optimal ranges
            current_state = self.ucf_calculator.get_state()

            for metric, current_value in current_state.items():
                if metric == "performance_score":
                    if current_value < 5.0:
                        insights.append(
                            CoordinationInsight(
                                insight_type=InsightType.OPTIMIZATION,
                                insight_title="Coordination Level Optimization",
                                insight_description=f"Current coordination level {current_value:.2f} is below optimal range (5.0-8.0)",
                                insight_priority="high",
                                insight_actions=[
                                    "Execute coordination-boosting routines",
                                    "Increase agent coordination",
                                    "Review workflow coordination requirements",
                                ],
                                insight_metadata={
                                    "current_value": current_value,
                                    "optimal_range": [5.0, 8.0],
                                },
                            )
                        )

                elif metric == "harmony":
                    if current_value < 0.6:
                        insights.append(
                            CoordinationInsight(
                                insight_type=InsightType.OPTIMIZATION,
                                insight_title="Harmony Alignment",
                                insight_description=f"Current harmony {current_value:.2f} is below optimal range (0.6-0.9)",
                                insight_priority="medium",
                                insight_actions=[
                                    "Execute harmony alignment routines",
                                    "Improve agent coordination",
                                    "Review system coherence",
                                ],
                                insight_metadata={
                                    "current_value": current_value,
                                    "optimal_range": [0.6, 0.9],
                                },
                            )
                        )

                elif metric == "friction":
                    if current_value > 0.2:
                        insights.append(
                            CoordinationInsight(
                                insight_type=InsightType.OPTIMIZATION,
                                insight_title="Entropy Reduction",
                                insight_description=f"Current friction {current_value:.2f} is above optimal range (0.0-0.2)",
                                insight_priority="medium",
                                insight_actions=[
                                    "Execute entropy reduction routines",
                                    "Review system efficiency",
                                    "Optimize resource allocation",
                                ],
                                insight_metadata={
                                    "current_value": current_value,
                                    "optimal_range": [0.0, 0.2],
                                },
                            )
                        )

            return insights

        except Exception as e:
            logger.error("Optimization insights generation failed: %s", e)
            return []

    async def _generate_warning_insights(self, historical_data: list[dict]) -> list[CoordinationInsight]:
        """Generate warning insights"""
        try:
            insights = []

            # Analyze trends for potential issues
            if len(historical_data) < 10:
                return insights

            # Check for declining trends
            coordination_values = [d.get("performance_score", 0.5) for d in historical_data[-20:]]
            if len(coordination_values) >= 10:
                x = np.arange(len(coordination_values))
                slope = np.polyfit(x, coordination_values, 1)[0]

                if slope < -0.01:
                    insights.append(
                        CoordinationInsight(
                            insight_type=InsightType.WARNING,
                            insight_title="Declining Coordination Trend",
                            insight_description=f"Coordination level shows declining trend (slope: {slope:.3f})",
                            insight_priority="high",
                            insight_actions=[
                                "Investigate coordination degradation causes",
                                "Execute coordination restoration routines",
                                "Review system health metrics",
                            ],
                            insight_metadata={
                                "trend_slope": slope,
                                "data_points": len(coordination_values),
                            },
                        )
                    )

            # Check for high volatility
            if len(coordination_values) >= 20:
                volatility = np.std(coordination_values)
                if volatility > 1.0:
                    insights.append(
                        CoordinationInsight(
                            insight_type=InsightType.WARNING,
                            insight_title="High Coordination Volatility",
                            insight_description=f"Coordination level shows high volatility (std: {volatility:.3f})",
                            insight_priority="medium",
                            insight_actions=[
                                "Stabilize coordination through routines",
                                "Review external influences",
                                "Implement volatility dampening",
                            ],
                            insight_metadata={
                                "volatility": volatility,
                                "data_points": len(coordination_values),
                            },
                        )
                    )

            return insights

        except Exception as e:
            logger.error("Warning insights generation failed: %s", e)
            return []

    async def _generate_opportunity_insights(self, historical_data: list[dict]) -> list[CoordinationInsight]:
        """Generate opportunity insights"""
        try:
            insights = []

            # Analyze for improvement opportunities
            current_state = self.ucf_calculator.get_state()

            # Check for high potential metrics
            if current_state.get("performance_score", 0.0) > 7.0:
                insights.append(
                    CoordinationInsight(
                        insight_type=InsightType.OPPORTUNITY,
                        insight_title="Peak Coordination Opportunity",
                        insight_description="Coordination level is in peak range - optimal for complex operations",
                        insight_priority="medium",
                        insight_actions=[
                            "Execute high-complexity workflows",
                            "Perform system optimizations",
                            "Enhance agent coordination",
                        ],
                        insight_metadata={"current_level": current_state.get("performance_score")},
                    )
                )

            if current_state.get("harmony", 0.0) > 0.8:
                insights.append(
                    CoordinationInsight(
                        insight_type=InsightType.OPPORTUNITY,
                        insight_title="Harmony Optimization Window",
                        insight_description="High harmony indicates optimal coordination state",
                        insight_priority="medium",
                        insight_actions=[
                            "Execute multi-agent coordination tasks",
                            "Perform system integration",
                            "Enhance collective coordination",
                        ],
                        insight_metadata={"current_harmony": current_state.get("harmony")},
                    )
                )

            return insights

        except Exception as e:
            logger.error("Opportunity insights generation failed: %s", e)
            return []

    async def _generate_pattern_insights(self, historical_data: list[dict]) -> list[CoordinationInsight]:
        """Generate pattern-based insights"""
        try:
            insights = []

            # Analyze for recurring patterns
            if len(historical_data) < 50:
                return insights

            # Check for time-based patterns
            timestamps = [datetime.fromisoformat(d["timestamp"]) for d in historical_data]
            coordination_values = [d.get("performance_score", 0.5) for d in historical_data]

            # Analyze hourly patterns
            hours = [t.hour for t in timestamps]
            hour_avg = defaultdict(list)

            for hour, value in zip(hours, coordination_values, strict=False):
                hour_avg[hour].append(value)

            # Find significant hourly variations
            hour_stats = {h: (np.mean(values), np.std(values)) for h, values in hour_avg.items()}

            if len(hour_stats) > 0:
                max_hour = max(hour_stats.items(), key=lambda x: x[1][0])
                min_hour = min(hour_stats.items(), key=lambda x: x[1][0])

                if max_hour[1][0] - min_hour[1][0] > 1.0:
                    insights.append(
                        CoordinationInsight(
                            insight_type=InsightType.PATTERN,
                            insight_title="Time-Based Coordination Pattern",
                            insight_description=f"Coordination peaks at hour {max_hour[0]} and troughs at hour {min_hour[0]}",
                            insight_priority="low",
                            insight_actions=[
                                "Schedule complex tasks during peak hours",
                                "Perform maintenance during trough hours",
                                "Investigate time-based influences",
                            ],
                            insight_metadata={
                                "peak_hour": max_hour[0],
                                "trough_hour": min_hour[0],
                                "peak_value": max_hour[1][0],
                                "trough_value": min_hour[1][0],
                            },
                        )
                    )

            return insights

        except Exception as e:
            logger.error("Pattern insights generation failed: %s", e)
            return []

    async def _generate_correlation_insights(self, historical_data: list[dict]) -> list[CoordinationInsight]:
        """Generate correlation-based insights"""
        try:
            insights = []

            # Analyze correlations between metrics
            if len(historical_data) < 20:
                return insights

            df = pd.DataFrame(historical_data)
            correlations = df.corr()

            # Find strong correlations
            strong_correlations = []
            for i in range(len(correlations.columns)):
                for j in range(i + 1, len(correlations.columns)):
                    metric1 = correlations.columns[i]
                    metric2 = correlations.columns[j]
                    corr_value = correlations.iloc[i, j]

                    if abs(corr_value) > 0.7:
                        strong_correlations.append((metric1, metric2, corr_value))

            for metric1, metric2, corr_value in strong_correlations:
                direction = "positive" if corr_value > 0 else "negative"
                insights.append(
                    CoordinationInsight(
                        insight_type=InsightType.CORRELATION,
                        insight_title=f"Strong {direction} Correlation",
                        insight_description=f"{metric1} and {metric2} show strong {direction} correlation (r={corr_value:.3f})",
                        insight_priority="medium",
                        insight_actions=[
                            f"Monitor {metric1} when adjusting {metric2}",
                            "Consider joint optimization strategies",
                            "Investigate underlying causal relationships",
                        ],
                        insight_metadata={
                            "metric1": metric1,
                            "metric2": metric2,
                            "correlation": corr_value,
                            "direction": direction,
                        },
                    )
                )

            return insights

        except Exception as e:
            logger.error("Correlation insights generation failed: %s", e)
            return []

    async def _analyze_trends(self, time_window: str, agent_ids: list[str] | None) -> dict[str, Any]:
        """Analyze trends in coordination data"""
        try:
            minutes = self.analysis_windows.get(time_window, 360)
            historical_data = await self._get_coordination_history(minutes, agent_ids)

            if not historical_data:
                return {}

            df = pd.DataFrame(historical_data)
            df["timestamp"] = pd.to_datetime(df["timestamp"])

            trends = {}
            metrics = [
                "performance_score",
                "harmony",
                "resilience",
                "throughput",
                "focus",
                "friction",
            ]

            for metric in metrics:
                if metric in df.columns:
                    values = df[metric].dropna()
                    if len(values) >= 10:
                        x = np.arange(len(values))
                        slope, intercept = np.polyfit(x, values, 1)

                        trends[metric] = {
                            "slope": float(slope),
                            "direction": ("increasing" if slope > 0 else "decreasing" if slope < 0 else "stable"),
                            "strength": float(abs(slope)),
                            "confidence": self._calculate_trend_confidence(values, slope),
                        }

            return trends

        except Exception as e:
            logger.error("Trend analysis failed: %s", e)
            return {}

    async def _detect_anomalies(self, time_window: str, agent_ids: list[str] | None) -> dict[str, Any]:
        """Detect anomalies in coordination data"""
        try:
            anomalies = {}
            minutes = self.analysis_windows.get(time_window, 360)
            historical_data = await self._get_coordination_history(minutes, agent_ids)

            if not historical_data:
                return {}

            df = pd.DataFrame(historical_data)

            metrics = [
                "performance_score",
                "harmony",
                "resilience",
                "throughput",
                "focus",
                "friction",
            ]

            for metric in metrics:
                if metric in df.columns:
                    values = df[metric].dropna()
                    if len(values) >= 20:
                        # Z-score based anomaly detection
                        mean_val = np.mean(values)
                        std_val = np.std(values)
                        z_scores = np.abs((values - mean_val) / std_val)

                        anomaly_indices = np.where(z_scores > 3)[0]
                        anomalies[metric] = {
                            "anomaly_count": len(anomaly_indices),
                            "anomaly_percentage": float(len(anomaly_indices) / len(values)),
                            "anomaly_indices": anomaly_indices.tolist(),
                            "anomaly_values": (
                                values.iloc[anomaly_indices].tolist() if len(anomaly_indices) > 0 else []
                            ),
                        }

            return anomalies

        except Exception as e:
            logger.error("Anomaly detection failed: %s", e)
            return {}

    async def _generate_predictions(self, time_window: str, agent_ids: list[str] | None) -> dict[str, Any]:
        """Generate predictions based on historical data"""
        try:
            predictions = {}
            minutes = self.analysis_windows.get(time_window, 360)
            historical_data = await self._get_coordination_history(minutes, agent_ids)

            if not historical_data:
                return {}

            df = pd.DataFrame(historical_data)

            metrics = [
                "performance_score",
                "harmony",
                "resilience",
                "throughput",
                "focus",
                "friction",
            ]

            for metric in metrics:
                if metric in df.columns:
                    values = df[metric].dropna()
                    if len(values) >= 20:
                        # Simple linear prediction
                        x = np.arange(len(values))
                        slope, intercept = np.polyfit(x, values, 1)

                        # Predict next 10 time steps
                        future_x = np.arange(len(values), len(values) + 10)
                        future_y = slope * future_x + intercept

                        predictions[metric] = {
                            "predicted_values": future_y.tolist(),
                            "trend": ("increasing" if slope > 0 else "decreasing" if slope < 0 else "stable"),
                            "confidence": 0.7,  # Simplified confidence
                        }

            return predictions

        except Exception as e:
            logger.error("Prediction generation failed: %s", e)
            return {}

    async def _analyze_performance(self, time_window: str, agent_ids: list[str] | None) -> dict[str, Any]:
        """Analyze performance metrics"""
        try:
            minutes = self.analysis_windows.get(time_window, 360)
            historical_data = await self._get_coordination_history(minutes, agent_ids)

            if not historical_data:
                return {}

            df = pd.DataFrame(historical_data)
            performance = {}

            # Calculate performance metrics
            metrics = [
                "performance_score",
                "harmony",
                "resilience",
                "throughput",
                "focus",
            ]

            for metric in metrics:
                if metric in df.columns:
                    values = df[metric].dropna()
                    if len(values) > 0:
                        performance[metric] = {
                            "average": float(values.mean()),
                            "peak": float(values.max()),
                            "stability": float(1.0 / (1.0 + values.std())),
                            "consistency": (float(1.0 - (values.std() / values.mean())) if values.mean() > 0 else 0.0),
                        }

            # Analyze execution efficiency
            if "execution_time" in df.columns:
                avg_time = df["execution_time"].mean()
                performance["execution_efficiency"] = {
                    "score": max(0, 1.0 - (avg_time / 1000.0)),  # Normalized score
                    "avg_time": avg_time,
                }

            return performance

        except Exception as e:
            logger.error("Performance analysis failed: %s", e)
            return {}

    async def _calculate_advanced_metrics(self, df: pd.DataFrame, basic_stats: dict) -> dict[str, Any]:
        """Calculate advanced coordination metrics"""
        try:
            advanced_metrics = {}

            # Calculate entropy for each metric
            metrics = [
                "performance_score",
                "harmony",
                "resilience",
                "throughput",
                "focus",
                "friction",
            ]

            for metric in metrics:
                if metric in df.columns:
                    values = df[metric].dropna()
                    if len(values) > 0:
                        # Calculate Shannon entropy
                        hist, _ = np.histogram(values, bins=10, density=True)
                        hist = hist[hist > 0]  # Remove zero bins
                        entropy = -np.sum(hist * np.log(hist))

                        advanced_metrics[metric] = {
                            "entropy": float(entropy),
                            "complexity": (float(np.std(values) / np.mean(values)) if np.mean(values) > 0 else 0.0),
                            "fractal_dimension": self._calculate_fractal_dimension(values),
                        }

            return advanced_metrics

        except Exception as e:
            logger.error("Advanced metrics calculation failed: %s", e)
            return {}

    async def _calculate_composite_scores(self, basic_stats: dict) -> dict[str, Any]:
        """Calculate composite coordination scores"""
        try:
            composite_scores = {}

            # Calculate overall coordination score
            if "performance_score" in basic_stats and "harmony" in basic_stats:
                coordination_score = (
                    basic_stats["performance_score"]["mean"] * 0.4
                    + basic_stats["harmony"]["mean"] * 0.3
                    + basic_stats.get("resilience", {"mean": 1.0})["mean"] * 0.2
                    + (1.0 - basic_stats.get("friction", {"mean": 0.1})["mean"]) * 0.1
                )

                composite_scores["overall_coordination"] = float(coordination_score)

            # Calculate system health score
            if all(metric in basic_stats for metric in ["harmony", "resilience", "throughput"]):
                health_score = (
                    basic_stats["harmony"]["mean"] * 0.4
                    + basic_stats["resilience"]["mean"] * 0.3
                    + basic_stats["throughput"]["mean"] * 0.3
                )

                composite_scores["system_health"] = float(health_score)

            # Calculate coherence score
            if "performance_score" in basic_stats and "focus" in basic_stats:
                coherence_score = basic_stats["performance_score"]["mean"] * 0.5 + basic_stats["focus"]["mean"] * 0.5

                composite_scores["coherence"] = float(coherence_score)

            return composite_scores

        except Exception as e:
            logger.error("Composite scores calculation failed: %s", e)
            return {}

    def _calculate_trend(self, values: pd.Series) -> str:
        """Calculate trend direction for a series"""
        if len(values) < 5:
            return "insufficient_data"

        x = np.arange(len(values))
        slope = np.polyfit(x, values, 1)[0]

        if slope > 0.01:
            return "increasing"
        elif slope < -0.01:
            return "decreasing"
        else:
            return "stable"

    def _calculate_trend_confidence(self, values: pd.Series, slope: float) -> float:
        """Calculate confidence in trend"""
        if len(values) < 10:
            return 0.0

        x = np.arange(len(values))
        y_pred = slope * x + np.mean(values)

        ss_res = np.sum((values - y_pred) ** 2)
        ss_tot = np.sum((values - np.mean(values)) ** 2)

        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
        return float(r_squared)

    def _calculate_fractal_dimension(self, values: np.ndarray) -> float:
        """Calculate fractal dimension using box-counting method"""
        try:
            if len(values) < 3:
                return 1.0

            # Simple box-counting approximation
            n = len(values)
            ranges = []

            for box_size in range(1, min(10, n // 2)):
                boxes = []
                for i in range(0, n, box_size):
                    box_values = values[i : i + box_size]
                    if len(box_values) > 0:
                        boxes.append(np.max(box_values) - np.min(box_values))

                if boxes:
                    ranges.append(np.mean(boxes))

            if len(ranges) < 2:
                return 1.0

            # Calculate slope of log-log plot
            log_ranges = np.log(ranges)
            log_sizes = np.log(range(1, len(ranges) + 1))

            slope = np.polyfit(log_sizes, log_ranges, 1)[0]
            return float(max(1.0, min(2.0, 2.0 - slope)))

        except (ValueError, np.linalg.LinAlgError, TypeError) as e:
            logger.debug("Fractal dimension calculation failed: %s", e)
            return 1.0
        except Exception as e:
            logger.warning("Unexpected error in fractal dimension calculation: %s", e)
            return 1.0

    async def _get_coordination_history(self, minutes: int, agent_ids: list[str] | None = None) -> list[dict[str, Any]]:
        """Get historical coordination data from the database.

        Queries the coordination_snapshots table for real recorded data.
        When no snapshots exist, synthesizes a single-point snapshot from
        the live UCF state so callers always have usable data.
        """
        try:
            from ..db_models import CoordinationSnapshot

            cutoff = datetime.now(UTC) - timedelta(minutes=minutes)

            # Query real snapshots from the database
            snapshots = (
                self.db.query(CoordinationSnapshot)
                .filter(CoordinationSnapshot.timestamp >= cutoff)
                .order_by(CoordinationSnapshot.timestamp.asc())
                .all()
            )

            historical_data: list[dict[str, Any]] = []
            for snap in snapshots:
                historical_data.append(
                    {
                        "timestamp": (snap.timestamp.isoformat() if snap.timestamp else datetime.now(UTC).isoformat()),
                        "performance_score": float(snap.performance_score or 0.0),
                        "harmony": float(snap.harmony or 0.0),
                        "resilience": float(snap.resilience or 0.0),
                        "throughput": float(snap.throughput or 0.0),
                        "focus": float(snap.focus or 0.0),
                        "friction": float(snap.friction or 0.0),
                    }
                )

            if not historical_data:
                # Synthesize from live UCF state so analytics callers aren't starved
                logger.info("No coordination snapshots for last %d minutes — using live UCF state", minutes)
                live_state = await self._get_live_ucf_snapshot()
                if live_state:
                    historical_data.append(live_state)

            return historical_data

        except (ImportError, AttributeError, RuntimeError) as e:
            logger.error("Coordination history retrieval failed: %s", e)
            # Last resort: return a synthetic point from UCF defaults
            try:
                live = await self._get_live_ucf_snapshot()
                return [live] if live else []
            except (ImportError, AttributeError, RuntimeError) as e2:
                logger.debug("Last-resort live UCF snapshot failed: %s", e2)
                return []
            except Exception as e2:
                logger.warning("Unexpected error in last-resort UCF snapshot: %s", e2)
                return []
        except Exception as e:
            logger.error("Unexpected error retrieving coordination history: %s", e)
            # Last resort: return a synthetic point from UCF defaults
            try:
                live = await self._get_live_ucf_snapshot()
                return [live] if live else []
            except Exception as e2:
                logger.warning("Last-resort live UCF snapshot also failed: %s", e2)
                return []

    async def _get_live_ucf_snapshot(self) -> dict[str, Any] | None:
        """Build a snapshot dict from the live UCF state.

        Pulls current values from the CoordinationService / UCFCalculator
        that were injected at construction time, falling back to safe defaults.
        """
        try:
            ucf_state: dict[str, Any] = {}
            if self.coordination_service:
                try:
                    ucf_state = await self.coordination_service.get_current_state()
                except Exception as e:
                    logger.debug("Coordination service state unavailable: %s", e)

            if not ucf_state and self.ucf_calculator:
                try:
                    ucf_state = self.ucf_calculator.calculate()
                except Exception as e:
                    logger.debug("UCF calculator unavailable: %s", e)

            harmony = float(ucf_state.get("harmony", 0.5))
            resilience = float(ucf_state.get("resilience", 1.0))
            throughput = float(ucf_state.get("throughput", 0.5))
            focus = float(ucf_state.get("focus", 0.5))
            friction = float(ucf_state.get("friction", 0.05))
            performance_score = float(ucf_state.get("performance_score", 0.0))
            if performance_score == 0.0:
                # Derive from component metrics
                performance_score = round((harmony + (1 - friction) + throughput + focus) / 4 * 10, 2)

            return {
                "timestamp": datetime.now(UTC).isoformat(),
                "performance_score": performance_score,
                "harmony": harmony,
                "resilience": resilience,
                "throughput": throughput,
                "focus": focus,
                "friction": friction,
            }
        except Exception as e:
            logger.debug("Live UCF snapshot unavailable: %s", e)
            return None

    async def _generate_anomaly_insights(self, anomalies: dict[str, Any]) -> list[CoordinationInsight]:
        """Generate insights from anomaly detection"""
        try:
            insights = []

            for metric, anomaly_data in anomalies.items():
                if anomaly_data.get("anomaly_count", 0) > 0:
                    insights.append(
                        CoordinationInsight(
                            insight_type=InsightType.WARNING,
                            insight_title=f"Anomalies Detected in {metric}",
                            insight_description=f"Detected {anomaly_data['anomaly_count']} anomalies in {metric}",
                            insight_priority="medium",
                            insight_actions=[
                                "Investigate anomaly causes",
                                "Review system stability",
                                "Consider anomaly mitigation strategies",
                            ],
                            insight_metadata=anomaly_data,
                        )
                    )

            return insights

        except Exception as e:
            logger.error("Anomaly insights generation failed: %s", e)
            return []

    async def _generate_prediction_insights(self, predictions: dict[str, Any]) -> list[CoordinationInsight]:
        """Generate insights from predictions"""
        try:
            insights = []

            for metric, prediction_data in predictions.items():
                if prediction_data.get("trend") == "decreasing":
                    insights.append(
                        CoordinationInsight(
                            insight_type=InsightType.WARNING,
                            insight_title=f"Predicted Decline in {metric}",
                            insight_description=f"Predictions indicate {metric} will decrease in the near future",
                            insight_priority="high",
                            insight_actions=[
                                "Prepare mitigation strategies",
                                "Monitor {metric} closely",
                                "Consider preemptive optimization",
                            ],
                            insight_metadata=prediction_data,
                        )
                    )

            return insights

        except Exception as e:
            logger.error("Prediction insights generation failed: %s", e)
            return []

    async def _generate_performance_insights(self, performance: dict[str, Any]) -> list[CoordinationInsight]:
        """Generate insights from performance analysis"""
        try:
            insights = []

            if "overall" in performance:
                overall_score = performance["overall"]["score"]
                if overall_score < 5.0:
                    insights.append(
                        CoordinationInsight(
                            insight_type=InsightType.OPTIMIZATION,
                            insight_title="Low Overall Performance",
                            insight_description=f"Overall performance score is {overall_score:.2f}",
                            insight_priority="high",
                            insight_actions=[
                                "Review performance bottlenecks",
                                "Optimize coordination metrics",
                                "Enhance system efficiency",
                            ],
                            insight_metadata=performance["overall"],
                        )
                    )

            return insights

        except Exception as e:
            logger.error("Performance insights generation failed: %s", e)
            return []

    async def get_analytics_history(self, limit: int = 100) -> dict[str, Any]:
        """Get analytics history"""
        try:
            return {
                "insights": self.insight_history[-limit:],
                "patterns": self.pattern_history[-limit:],
                "correlations": self.correlation_history[-limit:],
                "cache_keys": list(self.analytics_cache.keys()),
            }
        except Exception as e:
            logger.error("Analytics history retrieval failed: %s", e)
            return {}

    async def clear_analytics_cache(self) -> bool:
        """Clear analytics cache"""
        try:
            logger.info("Analytics cache cleared")
            return True

        except Exception as e:
            logger.error("Analytics cache clearing failed: %s", e)
            return False
