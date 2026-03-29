"""
Coordination State Prediction System

Advanced machine learning system for predicting coordination states and trends.
Integrates with existing UCF metrics and coordination tracking infrastructure.
"""

import logging
from collections import deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]

from sqlalchemy.orm import Session

from ..models.workflow_models import Workflow
from ..services.agent_service import AgentService
from ..services.coordination_service import CoordinationService
from ..services.ucf_calculator import UCFCalculator

logger = logging.getLogger(__name__)


class PredictionModel(str, Enum):
    LINEAR_REGRESSION = "linear_regression"
    EXPONENTIAL_SMOOTHING = "exponential_smoothing"
    NEURAL_NETWORK = "neural_network"
    SYSTEM_TIME_SERIES = "system_time_series"
    ENSEMBLE = "ensemble"


@dataclass
class CoordinationPrediction:
    """Coordination state prediction result"""

    predicted_state: dict[str, float]
    confidence: float
    prediction_model: PredictionModel
    time_horizon: int  # minutes ahead
    trend_direction: str  # "increasing", "decreasing", "stable"
    anomaly_detected: bool
    prediction_metadata: dict[str, Any]


@dataclass
class CoordinationTrend:
    """Coordination trend analysis result"""

    trend_direction: str
    trend_strength: float
    trend_duration: int  # minutes
    trend_confidence: float
    key_drivers: list[str]
    trend_metadata: dict[str, Any]


@dataclass
class CoordinationAnomaly:
    """Coordination anomaly detection result"""

    anomaly_type: str
    anomaly_severity: str  # "low", "medium", "high", "critical"
    anomaly_timestamp: datetime
    affected_metrics: list[str]
    anomaly_description: str
    recommended_actions: list[str]
    anomaly_metadata: dict[str, Any]


class CoordinationPredictor:
    """Advanced coordination state prediction system"""

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

        # Prediction data storage
        self.coordination_history: deque = deque(maxlen=1000)
        self.prediction_cache: dict[str, Any] = {}
        self.anomaly_history: list[CoordinationAnomaly] = []

        # Model parameters
        self.models = {
            PredictionModel.LINEAR_REGRESSION: self._linear_regression_predictor,
            PredictionModel.EXPONENTIAL_SMOOTHING: self._exponential_smoothing_predictor,
            PredictionModel.NEURAL_NETWORK: self._neural_network_predictor,
            PredictionModel.SYSTEM_TIME_SERIES: self._system_time_series_predictor,
        }

        # Anomaly detection thresholds
        self.anomaly_thresholds = {
            "performance_score": 0.15,
            "harmony": 0.2,
            "resilience": 0.25,
            "throughput": 0.2,
            "focus": 0.15,
            "friction": 0.1,
        }

    async def predict_coordination_state(
        self,
        time_horizon: int = 60,
        prediction_model: PredictionModel = PredictionModel.ENSEMBLE,
    ) -> CoordinationPrediction:
        """Predict future coordination state"""
        try:
            historical_data = await self._get_coordination_history(minutes=240)  # 4 hours

            if not historical_data:
                # Fallback to current state if no history
                current_state = self.ucf_calculator.get_state()
                return CoordinationPrediction(
                    predicted_state=current_state,
                    confidence=0.5,
                    prediction_model=prediction_model,
                    time_horizon=time_horizon,
                    trend_direction="stable",
                    anomaly_detected=False,
                    prediction_metadata={
                        "reason": "insufficient_historical_data",
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                )

            # Prepare features for prediction
            features = self._prepare_prediction_features(historical_data, time_horizon)

            # Generate prediction based on model
            if prediction_model == PredictionModel.ENSEMBLE:
                prediction = await self._ensemble_prediction(features, time_horizon)
            else:
                prediction_func = self.models.get(prediction_model)
                if prediction_func:
                    prediction = await prediction_func(features, time_horizon)
                else:
                    prediction = await self._ensemble_prediction(features, time_horizon)

            # Cache prediction
            cache_key = f"prediction_{time_horizon}_{prediction_model.value}"
            self.prediction_cache[cache_key] = prediction

            logger.info("Generated %s prediction for %s minutes ahead", prediction_model.value, time_horizon)
            return prediction

        except Exception as e:
            logger.error("Coordination state prediction failed: %s", e)
            raise

    async def analyze_coordination_trends(self, time_window: int = 120) -> list[CoordinationTrend]:  # minutes
        """Analyze coordination trends over time"""
        try:
            historical_data = await self._get_coordination_history(minutes=time_window)

            if len(historical_data) < 10:  # Need minimum data points
                return []

            trends = []

            # Analyze each UCF metric
            for metric_name in [
                "performance_score",
                "harmony",
                "resilience",
                "throughput",
                "focus",
                "friction",
            ]:
                metric_trend = await self._analyze_metric_trend(historical_data, metric_name)
                if metric_trend:
                    trends.append(metric_trend)

            # Analyze overall coordination trend
            overall_trend = await self._analyze_overall_trend(historical_data)
            if overall_trend:
                trends.append(overall_trend)

            # Cache trends
            self.prediction_cache[f"trends_{time_window}"] = trends

            logger.info("Analyzed %s coordination trends over %s minutes", len(trends), time_window)
            return trends

        except Exception as e:
            logger.error("Coordination trend analysis failed: %s", e)
            return []

    async def forecast_coordination_optimization(
        self, workflow_id: str | None = None, time_horizon: int = 120
    ) -> dict[str, Any]:
        """Forecast optimal coordination states for workflows"""
        try:
            prediction = await self.predict_coordination_state(time_horizon)

            # Get workflow-specific requirements if provided
            workflow_requirements = {}
            if workflow_id:
                workflow_requirements = await self._get_workflow_requirements(workflow_id)

            # Calculate optimal states
            optimal_states = await self._calculate_optimal_states(prediction, workflow_requirements)

            # Generate optimization recommendations
            recommendations = await self._generate_optimization_recommendations(
                prediction, optimal_states, workflow_requirements
            )

            forecast = {
                "prediction": asdict(prediction),
                "optimal_states": optimal_states,
                "recommendations": recommendations,
                "forecast_metadata": {
                    "workflow_id": workflow_id,
                    "time_horizon": time_horizon,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            }

            logger.info("Generated coordination optimization forecast for workflow %s", workflow_id)
            return forecast

        except Exception as e:
            logger.error("Coordination optimization forecasting failed: %s", e)
            raise

    async def predict_workflow_performance(
        self, workflow_id: str, input_data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Predict workflow performance based on coordination state"""
        try:
            current_state = self.ucf_calculator.get_state()
            prediction = await self.predict_coordination_state(time_horizon=30)

            # Get workflow characteristics
            workflow = self.db.query(Workflow).filter(Workflow.id == workflow_id).first()
            if not workflow:
                raise ValueError(f"Workflow not found: {workflow_id}")

            # Calculate performance metrics
            performance_metrics = await self._calculate_workflow_performance(
                workflow, current_state, prediction, input_data
            )

            # Generate performance insights
            insights = await self._generate_performance_insights(
                workflow, performance_metrics, current_state, prediction
            )

            performance_prediction = {
                "workflow_id": workflow_id,
                "current_coordination": current_state,
                "predicted_coordination": prediction.predicted_state,
                "performance_metrics": performance_metrics,
                "insights": insights,
                "prediction_metadata": {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "confidence": prediction.confidence,
                    "model": prediction.prediction_model.value,
                },
            }

            logger.info("Predicted performance for workflow %s", workflow_id)
            return performance_prediction

        except Exception as e:
            logger.error("Workflow performance prediction failed: %s", e)
            raise

    async def _linear_regression_predictor(self, features: dict[str, Any], time_horizon: int) -> CoordinationPrediction:
        """Linear regression-based coordination prediction"""
        try:
            time_series = features["time_series"]
            metrics = [
                "performance_score",
                "harmony",
                "resilience",
                "throughput",
                "focus",
                "friction",
            ]

            predicted_state = {}
            confidence = 0.0

            for metric in metrics:
                if metric in time_series:
                    values = time_series[metric]
                    if len(values) < 5:
                        predicted_state[metric] = values[-1] if values else 0.5
                        continue

                    # Simple linear regression
                    x = np.arange(len(values))
                    y = np.array(values)

                    # Calculate slope and intercept
                    n = len(x)
                    slope = (n * np.sum(x * y) - np.sum(x) * np.sum(y)) / (n * np.sum(x**2) - np.sum(x) ** 2)
                    intercept = (np.sum(y) - slope * np.sum(x)) / n

                    # Predict future value
                    future_x = len(values) + time_horizon
                    predicted_value = slope * future_x + intercept

                    # Clamp to valid range
                    if metric == "friction":
                        predicted_state[metric] = max(0.0, min(1.0, predicted_value))
                    else:
                        predicted_state[metric] = max(0.0, min(10.0, predicted_value))

                    # Calculate confidence based on R-squared
                    y_pred = slope * x + intercept
                    ss_res = np.sum((y - y_pred) ** 2)
                    ss_tot = np.sum((y - np.mean(y)) ** 2)
                    r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
                    confidence += r_squared

            confidence = confidence / len(metrics) if metrics else 0.5

            return CoordinationPrediction(
                predicted_state=predicted_state,
                confidence=confidence,
                prediction_model=PredictionModel.LINEAR_REGRESSION,
                time_horizon=time_horizon,
                trend_direction=self._determine_trend_direction(predicted_state, time_series),
                anomaly_detected=False,
                prediction_metadata={
                    "method": "linear_regression",
                    "data_points": len(time_series.get("performance_score", [])),
                },
            )

        except Exception as e:
            logger.error("Linear regression prediction failed: %s", e)
            return self._fallback_prediction(time_horizon)

    async def _exponential_smoothing_predictor(
        self, features: dict[str, Any], time_horizon: int
    ) -> CoordinationPrediction:
        """Exponential smoothing-based coordination prediction"""
        try:
            metrics = [
                "performance_score",
                "harmony",
                "resilience",
                "throughput",
                "focus",
                "friction",
            ]

            predicted_state = {}
            confidence = 0.0
            time_series = features.get("time_series", {})

            for metric in metrics:
                if metric in time_series:
                    values = time_series[metric]
                    if len(values) < 3:
                        predicted_state[metric] = values[-1] if values else 0.5
                        continue

                    # Exponential smoothing parameters
                    alpha = 0.3  # Smoothing factor
                    beta = 0.1  # Trend factor

                    # Initialize
                    level = values[0]
                    trend = values[1] - values[0] if len(values) > 1 else 0

                    # Apply exponential smoothing
                    for i in range(1, len(values)):
                        prev_level = level
                        level = alpha * values[i] + (1 - alpha) * (level + trend)
                        trend = beta * (level - prev_level) + (1 - beta) * trend

                    # Predict future value
                    predicted_value = level + trend * time_horizon

                    # Clamp to valid range
                    if metric == "friction":
                        predicted_state[metric] = max(0.0, min(1.0, predicted_value))
                    else:
                        predicted_state[metric] = max(0.0, min(10.0, predicted_value))

                    # Calculate confidence based on smoothing quality
                    mse = (
                        np.mean(
                            [
                                (values[i] - (alpha * values[i - 1] + (1 - alpha) * (level + trend))) ** 2
                                for i in range(1, len(values))
                            ]
                        )
                        if len(values) > 1
                        else 0
                    )
                    confidence += 1 / (1 + mse)

            confidence = confidence / len(metrics) if metrics else 0.5

            return CoordinationPrediction(
                predicted_state=predicted_state,
                confidence=confidence,
                prediction_model=PredictionModel.EXPONENTIAL_SMOOTHING,
                time_horizon=time_horizon,
                trend_direction=self._determine_trend_direction(predicted_state, time_series),
                anomaly_detected=False,
                prediction_metadata={
                    "method": "exponential_smoothing",
                    "alpha": 0.3,
                    "beta": 0.1,
                },
            )

        except Exception as e:
            logger.error("Exponential smoothing prediction failed: %s", e)
            return self._fallback_prediction(time_horizon)

    async def _neural_network_predictor(self, features: dict[str, Any], time_horizon: int) -> CoordinationPrediction:
        """Neural network-based coordination prediction"""
        try:
            time_series = features["time_series"]
            metrics = [
                "performance_score",
                "harmony",
                "resilience",
                "throughput",
                "focus",
                "friction",
            ]

            predicted_state = {}
            confidence = 0.0

            for metric in metrics:
                if metric in time_series:
                    values = time_series[metric]
                    if len(values) < 10:
                        predicted_state[metric] = values[-1] if values else 0.5
                        continue

                    # Create sliding window features
                    window_size = 5
                    X = []
                    y = []

                    for i in range(window_size, len(values)):
                        X.append(values[i - window_size : i])
                        y.append(values[i])

                    X = np.array(X)
                    y = np.array(y)

                    if len(X) < 5:
                        predicted_state[metric] = values[-1]
                        continue

                    # Simple neural network (single layer)
                    input_size = window_size
                    hidden_size = 3
                    output_size = 1

                    # Initialize weights
                    W1 = np.random.randn(input_size, hidden_size) * 0.1
                    b1 = np.zeros(hidden_size)
                    W2 = np.random.randn(hidden_size, output_size) * 0.1
                    b2 = np.zeros(output_size)

                    # Training (simplified)
                    learning_rate = 0.01
                    epochs = 100

                    for _ in range(epochs):
                        # Forward pass
                        hidden = np.tanh(X @ W1 + b1)
                        output = hidden @ W2 + b2

                        # Backward pass
                        loss = np.mean((output - y.reshape(-1, 1)) ** 2)
                        d_output = 2 * (output - y.reshape(-1, 1))
                        d_hidden = d_output @ W2.T * (1 - hidden**2)

                        # Update weights
                        W2 -= learning_rate * hidden.T @ d_output / len(X)
                        b2 -= learning_rate * np.mean(d_output, axis=0)
                        W1 -= learning_rate * X.T @ d_hidden / len(X)
                        b1 -= learning_rate * np.mean(d_hidden, axis=0)

                    # Predict future value
                    recent_values = np.array(values[-window_size:]).reshape(1, -1)
                    hidden = np.tanh(recent_values @ W1 + b1)
                    predicted_value = (hidden @ W2 + b2)[0, 0]

                    # Clamp to valid range
                    if metric == "friction":
                        predicted_state[metric] = max(0.0, min(1.0, predicted_value))
                    else:
                        predicted_state[metric] = max(0.0, min(10.0, predicted_value))

                    # Calculate confidence based on training loss
                    confidence += 1 / (1 + loss)

            confidence = confidence / len(metrics) if metrics else 0.5

            return CoordinationPrediction(
                predicted_state=predicted_state,
                confidence=confidence,
                prediction_model=PredictionModel.NEURAL_NETWORK,
                time_horizon=time_horizon,
                trend_direction=self._determine_trend_direction(predicted_state, time_series),
                anomaly_detected=False,
                prediction_metadata={
                    "method": "neural_network",
                    "architecture": "1-layer",
                    "window_size": 5,
                },
            )

        except Exception as e:
            logger.error("Neural network prediction failed: %s", e)
            return self._fallback_prediction(time_horizon)

    async def _system_time_series_predictor(
        self, features: dict[str, Any], time_horizon: int
    ) -> CoordinationPrediction:
        """System-inspired time series coordination prediction"""
        try:
            metrics = [
                "performance_score",
                "harmony",
                "resilience",
                "throughput",
                "focus",
                "friction",
            ]

            predicted_state = {}
            confidence = 0.0
            time_series = features.get("time_series", {})

            for metric in metrics:
                if metric in time_series:
                    values = time_series[metric]
                    if len(values) < 8:
                        predicted_state[metric] = values[-1] if values else 0.5
                        continue

                    # System-inspired superposition of multiple predictions
                    predictions = []

                    # Method 1: Linear trend
                    x = np.arange(len(values))
                    slope = np.polyfit(x, values, 1)[0]
                    linear_pred = values[-1] + slope * time_horizon
                    predictions.append(linear_pred)

                    # Method 2: Moving average
                    ma_pred = np.mean(values[-5:]) + (values[-1] - np.mean(values[-5:])) * 0.5
                    predictions.append(ma_pred)

                    # Method 3: Exponential moving average
                    ema_alpha = 2 / (len(values) + 1)
                    ema = values[0]
                    for val in values[1:]:
                        ema = ema_alpha * val + (1 - ema_alpha) * ema
                    ema_pred = ema + (values[-1] - ema) * 0.3
                    predictions.append(ema_pred)

                    # System superposition: weighted average
                    weights = [0.4, 0.3, 0.3]  # Coordination-inspired weights
                    predicted_value = sum(w * p for w, p in zip(weights, predictions, strict=False))

                    # Apply system coherence factor
                    coherence_factor = 1.0 - abs(values[-1] - np.mean(values[-10:])) * 0.1
                    predicted_value *= coherence_factor

                    # Clamp to valid range
                    if metric == "friction":
                        predicted_state[metric] = max(0.0, min(1.0, predicted_value))
                    else:
                        predicted_state[metric] = max(0.0, min(10.0, predicted_value))

                    # Calculate system confidence
                    variance = np.var(predictions)
                    system_confidence = 1 / (1 + variance * 0.1)
                    confidence += system_confidence

            confidence = confidence / len(metrics) if metrics else 0.5

            return CoordinationPrediction(
                predicted_state=predicted_state,
                confidence=confidence,
                prediction_model=PredictionModel.SYSTEM_TIME_SERIES,
                time_horizon=time_horizon,
                trend_direction=self._determine_trend_direction(predicted_state, time_series),
                anomaly_detected=False,
                prediction_metadata={
                    "method": "system_time_series",
                    "superposition_methods": 3,
                    "coherence_factor": True,
                },
            )

        except Exception as e:
            logger.error("System time series prediction failed: %s", e)
            return self._fallback_prediction(time_horizon)

    async def _ensemble_prediction(self, features: dict[str, Any], time_horizon: int) -> CoordinationPrediction:
        """Ensemble prediction combining multiple models"""
        try:
            models = [
                PredictionModel.LINEAR_REGRESSION,
                PredictionModel.EXPONENTIAL_SMOOTHING,
                PredictionModel.NEURAL_NETWORK,
                PredictionModel.SYSTEM_TIME_SERIES,
            ]

            predictions = []
            confidences = []

            for model in models:
                if model in self.models:
                    pred_func = self.models[model]
                    prediction = await pred_func(features, time_horizon)
                    predictions.append(prediction)
                    confidences.append(prediction.confidence)

            if not predictions:
                return self._fallback_prediction(time_horizon)

            # Ensemble: weighted average based on confidence
            ensemble_state = {}
            metrics = [
                "performance_score",
                "harmony",
                "resilience",
                "throughput",
                "focus",
                "friction",
            ]

            for metric in metrics:
                weighted_sum = 0.0
                weight_sum = 0.0

                for pred, conf in zip(predictions, confidences, strict=False):
                    if metric in pred.predicted_state:
                        weighted_sum += pred.predicted_state[metric] * conf
                        weight_sum += conf

                if weight_sum > 0:
                    ensemble_state[metric] = weighted_sum / weight_sum
                else:
                    ensemble_state[metric] = 0.5

            # Calculate ensemble confidence
            ensemble_confidence = np.mean(confidences)

            return CoordinationPrediction(
                predicted_state=ensemble_state,
                confidence=ensemble_confidence,
                prediction_model=PredictionModel.ENSEMBLE,
                time_horizon=time_horizon,
                trend_direction=self._determine_trend_direction(ensemble_state, features["time_series"]),
                anomaly_detected=False,
                prediction_metadata={
                    "method": "ensemble",
                    "models_used": [m.value for m in models],
                    "ensemble_confidence": ensemble_confidence,
                },
            )

        except Exception as e:
            logger.error("Ensemble prediction failed: %s", e)
            return self._fallback_prediction(time_horizon)

    def _fallback_prediction(self, time_horizon: int) -> CoordinationPrediction:
        """Fallback prediction when models fail"""
        current_state = self.ucf_calculator.get_state()
        return CoordinationPrediction(
            predicted_state=current_state,
            confidence=0.3,
            prediction_model=PredictionModel.ENSEMBLE,
            time_horizon=time_horizon,
            trend_direction="stable",
            anomaly_detected=False,
            prediction_metadata={"reason": "model_failure", "fallback_used": True},
        )

    def _prepare_prediction_features(self, historical_data: list[dict], time_horizon: int) -> dict[str, Any]:
        """Prepare features for prediction models"""
        try:
            time_series = {}
            metrics = [
                "performance_score",
                "harmony",
                "resilience",
                "throughput",
                "focus",
                "friction",
            ]

            for metric in metrics:
                time_series[metric] = [data.get(metric, 0.5) for data in historical_data]

            # Calculate additional features
            features = {
                "time_series": time_series,
                "time_horizon": time_horizon,
                "current_state": historical_data[-1] if historical_data else {},
                "trend_features": self._calculate_trend_features(time_series),
                "volatility_features": self._calculate_volatility_features(time_series),
            }

            return features

        except Exception as e:
            logger.error("Feature preparation failed: %s", e)
            return {"time_series": {}, "time_horizon": time_horizon}

    def _calculate_trend_features(self, time_series: dict[str, list[float]]) -> dict[str, float]:
        """Calculate trend features for time series"""
        try:
            trend_features = {}

            for metric, values in time_series.items():
                if len(values) < 3:
                    trend_features[f"{metric}_trend"] = 0.0
                    continue

                # Calculate linear trend
                x = np.arange(len(values))
                slope = np.polyfit(x, values, 1)[0]
                trend_features[f"{metric}_trend"] = slope

                # Calculate momentum
                momentum = values[-1] - values[-5] if len(values) >= 5 else 0.0
                trend_features[f"{metric}_momentum"] = momentum

            return trend_features

        except Exception as e:
            logger.error("Trend feature calculation failed: %s", e)
            return {}

    def _calculate_volatility_features(self, time_series: dict[str, list[float]]) -> dict[str, float]:
        """Calculate volatility features for time series"""
        try:
            volatility_features = {}

            for metric, values in time_series.items():
                if len(values) < 5:
                    volatility_features[f"{metric}_volatility"] = 0.0
                    continue

                # Calculate standard deviation
                volatility = np.std(values)
                volatility_features[f"{metric}_volatility"] = volatility

                # Calculate average true range (simplified)
                changes = [abs(values[i] - values[i - 1]) for i in range(1, len(values))]
                atr = np.mean(changes) if changes else 0.0
                volatility_features[f"{metric}_atr"] = atr

            return volatility_features

        except Exception as e:
            logger.error("Volatility feature calculation failed: %s", e)
            return {}

    def _determine_trend_direction(self, predicted_state: dict[str, float], time_series: dict[str, list[float]]) -> str:
        """Determine overall trend direction"""
        try:
            if not predicted_state or not time_series:
                return "stable"

            # Calculate average change across all metrics
            total_change = 0.0
            metric_count = 0

            for metric, values in time_series.items():
                if metric in predicted_state and values:
                    current = values[-1]
                    predicted = predicted_state[metric]
                    change = predicted - current
                    total_change += change
                    metric_count += 1

            if metric_count == 0:
                return "stable"

            avg_change = total_change / metric_count

            if avg_change > 0.1:
                return "increasing"
            elif avg_change < -0.1:
                return "decreasing"
            else:
                return "stable"

        except Exception as e:
            logger.error("Trend direction determination failed: %s", e)
            return "stable"

    async def _get_coordination_history(self, minutes: int = 240) -> list[dict[str, Any]]:
        """Get historical coordination data from DB, falling back to UCF state"""
        # Try DB first for real historical data
        try:
            from apps.backend.services.state_snapshot_service import get_snapshot_service

            service = get_snapshot_service()
            history = service.get_history(minutes=minutes, limit=500)
            if history and len(history) > 1:
                logger.debug(
                    "Loaded %d coordination snapshots from DB (last %d min)",
                    len(history),
                    minutes,
                )
                return history
        except Exception as e:
            logger.debug("DB coordination history not available: %s", e)

        # Fallback: single data point from current UCF state
        try:
            from apps.backend.coordination_engine import load_ucf_state

            ucf = load_ucf_state()
            return [
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "performance_score": ucf.get("coordination", ucf.get("harmony", 0.5)),
                    "harmony": ucf.get("harmony", 0.5),
                    "resilience": ucf.get("resilience", 0.7),
                    "throughput": ucf.get("throughput", 0.6),
                    "focus": ucf.get("focus", 0.5),
                    "friction": ucf.get("friction", 0.1),
                    "source": "ucf_state_file",
                }
            ]

        except Exception as e:
            logger.error("Coordination history retrieval failed: %s", e)
            return []

    async def _analyze_metric_trend(self, historical_data: list[dict], metric_name: str) -> CoordinationTrend | None:
        """Analyze trend for a specific metric"""
        try:
            if not historical_data:
                return None

            values = [data.get(metric_name, 0.5) for data in historical_data]

            # Calculate trend direction and strength
            x = np.arange(len(values))
            slope, intercept = np.polyfit(x, values, 1)

            # Calculate trend strength (R-squared)
            y_pred = slope * x + intercept
            ss_res = np.sum((values - y_pred) ** 2)
            ss_tot = np.sum((values - np.mean(values)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

            # Determine trend direction
            if slope > 0.01:
                trend_direction = "increasing"
            elif slope < -0.01:
                trend_direction = "decreasing"
            else:
                trend_direction = "stable"

            # Calculate trend duration (time window in minutes)
            trend_duration = len(historical_data) * 5  # Assuming 5-minute intervals

            return CoordinationTrend(
                trend_direction=trend_direction,
                trend_strength=abs(slope),
                trend_duration=trend_duration,
                trend_confidence=r_squared,
                key_drivers=[metric_name],
                trend_metadata={
                    "slope": slope,
                    "intercept": intercept,
                    "r_squared": r_squared,
                    "data_points": len(values),
                },
            )

        except Exception as e:
            logger.error("Metric trend analysis failed for %s: %s", metric_name, e)
            return None

    async def _analyze_overall_trend(self, historical_data: list[dict]) -> CoordinationTrend | None:
        """Analyze overall coordination trend"""
        try:
            if not historical_data:
                return None

            # Calculate composite coordination score
            composite_scores = []
            for data in historical_data:
                score = (
                    data.get("performance_score", 0.5) * 0.3
                    + data.get("harmony", 0.5) * 0.2
                    + data.get("resilience", 1.0) * 0.2
                    + data.get("throughput", 0.5) * 0.15
                    + data.get("focus", 0.5) * 0.1
                    + (1.0 - data.get("friction", 0.1)) * 0.05
                )
                composite_scores.append(score)

            # Analyze composite trend
            x = np.arange(len(composite_scores))
            slope, intercept = np.polyfit(x, composite_scores, 1)

            # Calculate trend strength
            y_pred = slope * x + intercept
            ss_res = np.sum((composite_scores - y_pred) ** 2)
            ss_tot = np.sum((composite_scores - np.mean(composite_scores)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

            # Determine trend direction
            if slope > 0.01:
                trend_direction = "increasing"
            elif slope < -0.01:
                trend_direction = "decreasing"
            else:
                trend_direction = "stable"

            # Identify key drivers
            key_drivers = []
            metrics = [
                "performance_score",
                "harmony",
                "resilience",
                "throughput",
                "focus",
                "friction",
            ]

            for metric in metrics:
                metric_values = [data.get(metric, 0.5) for data in historical_data]
                metric_slope = np.polyfit(x, metric_values, 1)[0]

                if abs(metric_slope) > abs(slope) * 0.5:
                    key_drivers.append(metric)

            return CoordinationTrend(
                trend_direction=trend_direction,
                trend_strength=abs(slope),
                trend_duration=len(historical_data) * 5,
                trend_confidence=r_squared,
                key_drivers=key_drivers,
                trend_metadata={
                    "composite_slope": slope,
                    "composite_intercept": intercept,
                    "r_squared": r_squared,
                    "data_points": len(composite_scores),
                },
            )

        except Exception as e:
            logger.error("Overall trend analysis failed: %s", e)
            return None

    async def _detect_anomalies(self, predicted_state: dict[str, float], historical_data: list[dict]) -> bool:
        """Detect anomalies in predicted coordination state"""
        try:
            if not predicted_state or not historical_data:
                return False

            anomaly_detected = False

            for metric, predicted_value in predicted_state.items():
                historical_values = [data.get(metric, 0.5) for data in historical_data]

                if not historical_values:
                    continue

                # Calculate statistical thresholds
                mean_val = np.mean(historical_values)
                std_val = np.std(historical_values)
                threshold = self.anomaly_thresholds.get(metric, 0.2)

                # Check for anomaly
                if abs(predicted_value - mean_val) > threshold * std_val:
                    anomaly_detected = True

                    # Create anomaly record
                    anomaly = CoordinationAnomaly(
                        anomaly_type="statistical_deviation",
                        anomaly_severity=(
                            "medium" if abs(predicted_value - mean_val) > 2 * threshold * std_val else "low"
                        ),
                        anomaly_timestamp=datetime.now(UTC),
                        affected_metrics=[metric],
                        anomaly_description=f"{metric} predicted value {predicted_value:.3f} deviates significantly from historical mean {mean_val:.3f}",
                        recommended_actions=[
                            "Monitor closely",
                            "Consider coordination adjustment",
                        ],
                        anomaly_metadata={
                            "predicted_value": predicted_value,
                            "historical_mean": mean_val,
                            "historical_std": std_val,
                            "deviation": abs(predicted_value - mean_val),
                        },
                    )

                    self.anomaly_history.append(anomaly)

            return anomaly_detected

        except Exception as e:
            logger.error("Anomaly detection failed: %s", e)
            return False

    async def _get_workflow_requirements(self, workflow_id: str) -> dict[str, float]:
        """Get workflow-specific coordination requirements"""
        try:
            workflow = self.db.query(Workflow).filter(Workflow.id == workflow_id).first()
            if not workflow:
                return {}

            return workflow.ucf_requirements or {}

        except Exception as e:
            logger.error("Workflow requirements retrieval failed: %s", e)
            return {}

    async def _calculate_optimal_states(
        self,
        prediction: CoordinationPrediction,
        workflow_requirements: dict[str, float],
    ) -> dict[str, Any]:
        """Calculate optimal coordination states for workflows"""
        try:
            optimal_states = {}

            for metric, predicted_value in prediction.predicted_state.items():
                # Base optimal state on prediction
                optimal_value = predicted_value

                # Adjust based on workflow requirements
                if metric in workflow_requirements:
                    requirement = workflow_requirements[metric]
                    optimal_value = max(optimal_value, requirement)

                # Apply optimal ranges
                if metric == "performance_score":
                    optimal_states[metric] = {
                        "current": predicted_value,
                        "optimal": max(5.0, optimal_value),
                        "range": [5.0, 8.0],
                    }
                elif metric == "harmony":
                    optimal_states[metric] = {
                        "current": predicted_value,
                        "optimal": max(0.6, optimal_value),
                        "range": [0.6, 0.9],
                    }
                elif metric == "friction":
                    optimal_states[metric] = {
                        "current": predicted_value,
                        "optimal": min(0.1, optimal_value),
                        "range": [0.0, 0.2],
                    }
                else:
                    optimal_states[metric] = {
                        "current": predicted_value,
                        "optimal": optimal_value,
                        "range": [0.0, 1.0],
                    }

            return optimal_states

        except Exception as e:
            logger.error("Optimal state calculation failed: %s", e)
            return {}

    async def _generate_optimization_recommendations(
        self,
        prediction: CoordinationPrediction,
        optimal_states: dict[str, Any],
        workflow_requirements: dict[str, float],
    ) -> list[dict[str, Any]]:
        """Generate coordination optimization recommendations"""
        try:
            recommendations = []

            for metric, optimal_info in optimal_states.items():
                current = optimal_info["current"]
                optimal = optimal_info["optimal"]

                if abs(optimal - current) > 0.1:
                    if metric == "performance_score":
                        if current < 5.0:
                            recommendations.append(
                                {
                                    "action": "Increase coordination level",
                                    "priority": "high",
                                    "description": f"Coordination level {current:.2f} below optimal {optimal:.2f}",
                                    "suggestions": [
                                        "Meditation",
                                        "Cycle execution",
                                        "Agent coordination",
                                    ],
                                }
                            )
                    elif metric == "harmony":
                        if current < 0.6:
                            recommendations.append(
                                {
                                    "action": "Improve harmony",
                                    "priority": "medium",
                                    "description": f"Harmony {current:.2f} below optimal {optimal:.2f}",
                                    "suggestions": [
                                        "Team coordination",
                                        "UCF adjustment",
                                        "Coordination alignment",
                                    ],
                                }
                            )
                    elif metric == "friction":
                        if current > 0.2:
                            recommendations.append(
                                {
                                    "action": "Reduce friction",
                                    "priority": "medium",
                                    "description": f"Friction {current:.2f} above optimal {optimal:.2f}",
                                    "suggestions": [
                                        "Entropy reduction",
                                        "System cleanup",
                                        "Coordination purification",
                                    ],
                                }
                            )

            # Add workflow-specific recommendations
            for metric, requirement in workflow_requirements.items():
                if metric in optimal_states:
                    current = optimal_states[metric]["current"]
                    if current < requirement:
                        recommendations.append(
                            {
                                "action": f"Meet {metric} requirement for workflow",
                                "priority": "high",
                                "description": f"{metric} {current:.2f} below workflow requirement {requirement:.2f}",
                                "suggestions": [
                                    "Workflow optimization",
                                    "Coordination adjustment",
                                    "Resource allocation",
                                ],
                            }
                        )

            return recommendations

        except Exception as e:
            logger.error("Optimization recommendations generation failed: %s", e)
            return []

    async def _calculate_workflow_performance(
        self,
        workflow: Workflow,
        current_state: dict[str, float],
        prediction: CoordinationPrediction,
        input_data: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Calculate workflow performance metrics"""
        try:
            performance_score = current_state.get("performance_score", 0.5)
            harmony = current_state.get("harmony", 0.5)
            resilience = current_state.get("resilience", 1.0)

            # Calculate performance score
            performance_score = (
                performance_score * 0.3
                + harmony * 0.25
                + resilience * 0.2
                + prediction.confidence * 0.15
                + workflow.min_performance_score * 0.1
            )

            # Calculate efficiency
            efficiency = performance_score * (1.0 - current_state.get("friction", 0.1))

            # Calculate risk
            risk_score = 1.0 - efficiency

            return {
                "performance_score": min(max(performance_score, 0.0), 10.0),
                "efficiency": min(max(efficiency, 0.0), 1.0),
                "risk_score": min(max(risk_score, 0.0), 1.0),
                "confidence": prediction.confidence,
                "predicted_performance": self._calculate_predicted_performance(prediction),
                "workflow_alignment": self._calculate_workflow_alignment(workflow, current_state),
            }

        except Exception as e:
            logger.error("Workflow performance calculation failed: %s", e)
            return {}

    def _calculate_predicted_performance(self, prediction: CoordinationPrediction) -> float:
        """Calculate predicted performance based on future coordination state"""
        try:
            predicted_state = prediction.predicted_state
            predicted_score = (
                predicted_state.get("performance_score", 0.5) * 0.3
                + predicted_state.get("harmony", 0.5) * 0.25
                + predicted_state.get("resilience", 1.0) * 0.2
                + prediction.confidence * 0.15
            )
            return min(max(predicted_score, 0.0), 10.0)

        except Exception as e:
            logger.error("Predicted performance calculation failed: %s", e)
            return 0.0

    def _calculate_workflow_alignment(self, workflow: Workflow, current_state: dict[str, float]) -> float:
        """Calculate alignment between current state and workflow requirements"""
        try:
            alignment_score = 0.0
            requirement_count = 0

            for metric, requirement in workflow.ucf_requirements.items():
                if metric in current_state:
                    current_value = current_state[metric]
                    if metric == "friction":
                        # For friction, lower is better
                        alignment = max(0.0, 1.0 - abs(current_value - requirement))
                    else:
                        alignment = min(1.0, current_value / requirement) if requirement > 0 else 0.5

                    alignment_score += alignment
                    requirement_count += 1

            return alignment_score / requirement_count if requirement_count > 0 else 0.5

        except Exception as e:
            logger.error("Workflow alignment calculation failed: %s", e)
            return 0.5

    async def _generate_performance_insights(
        self,
        workflow: Workflow,
        performance_metrics: dict[str, Any],
        current_state: dict[str, float],
        prediction: CoordinationPrediction,
    ) -> list[dict[str, Any]]:
        """Generate performance insights and recommendations"""
        try:
            insights = []

            performance_score = performance_metrics.get("performance_score", 0.0)
            efficiency = performance_metrics.get("efficiency", 0.0)
            risk_score = performance_metrics.get("risk_score", 0.0)

            # Performance insights
            if performance_score > 7.0:
                insights.append(
                    {
                        "type": "positive",
                        "category": "performance",
                        "message": "Excellent performance expected",
                        "details": "Coordination alignment is optimal for workflow execution",
                    }
                )
            elif performance_score > 5.0:
                insights.append(
                    {
                        "type": "neutral",
                        "category": "performance",
                        "message": "Good performance expected",
                        "details": "Minor coordination adjustments may improve results",
                    }
                )
            else:
                insights.append(
                    {
                        "type": "warning",
                        "category": "performance",
                        "message": "Performance may be suboptimal",
                        "details": "Coordination optimization recommended before execution",
                    }
                )

            # Efficiency insights
            if efficiency > 0.8:
                insights.append(
                    {
                        "type": "positive",
                        "category": "efficiency",
                        "message": "High efficiency expected",
                        "details": "Low entropy and high coherence detected",
                    }
                )
            elif efficiency > 0.6:
                insights.append(
                    {
                        "type": "neutral",
                        "category": "efficiency",
                        "message": "Moderate efficiency expected",
                        "details": "Some optimization opportunities identified",
                    }
                )
            else:
                insights.append(
                    {
                        "type": "warning",
                        "category": "efficiency",
                        "message": "Low efficiency expected",
                        "details": "High entropy or low coherence detected",
                    }
                )

            # Risk insights
            if risk_score > 0.7:
                insights.append(
                    {
                        "type": "critical",
                        "category": "risk",
                        "message": "High risk detected",
                        "details": "Coordination state may impact workflow success",
                        "recommendations": [
                            "Delay execution",
                            "Coordination optimization",
                            "Risk mitigation",
                        ],
                    }
                )
            elif risk_score > 0.4:
                insights.append(
                    {
                        "type": "warning",
                        "category": "risk",
                        "message": "Moderate risk detected",
                        "details": "Monitor coordination state during execution",
                        "recommendations": ["Close monitoring", "Contingency planning"],
                    }
                )

            return insights

        except Exception as e:
            logger.error("Performance insights generation failed: %s", e)
            return []

    async def get_prediction_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get prediction history"""
        try:
            history = []
            for key, value in self.prediction_cache.items():
                if key.startswith("prediction_"):
                    history.append(
                        {
                            "cache_key": key,
                            "prediction": asdict(value),
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    )

            return history[-limit:]

        except Exception as e:
            logger.error("Prediction history retrieval failed: %s", e)
            return []

    async def get_anomaly_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get anomaly history"""
        try:
            return [
                {
                    "timestamp": anomaly.timestamp.isoformat(),
                    "metric": anomaly.metric,
                    "expected_value": anomaly.expected_value,
                    "actual_value": anomaly.actual_value,
                    "severity": anomaly.severity,
                    "description": anomaly.description,
                }
                for anomaly in self.anomaly_history[-limit:]
            ]

        except Exception as e:
            logger.error("Anomaly history retrieval failed: %s", e)
            return []

    async def clear_prediction_cache(self) -> bool:
        """Clear prediction cache"""
        try:
            logger.info("Prediction cache cleared")
            return True

        except Exception as e:
            logger.error("Cache clearing failed: %s", e)
            return False
