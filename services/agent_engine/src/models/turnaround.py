"""Predictive models for airframe turnaround times and maintenance delay risk."""

import numpy as np
from sklearn.linear_model import Ridge


class TurnaroundPredictor:
    """Predicts turnaround duration and maintenance delay probability."""

    def __init__(self):
        # Features: [flight_hours_logged / 1000, payload_ratio, weather_severity (0-1), age_years / 20]
        self._model = Ridge(alpha=1.0)
        # Train on synthetic historical airframe operational data
        X_train = np.array([
            [1.0, 0.5, 0.1, 0.2],
            [2.5, 0.8, 0.3, 0.4],
            [4.0, 0.9, 0.7, 0.6],
            [6.0, 1.0, 0.9, 0.8],
            [0.5, 0.2, 0.0, 0.1],
            [3.0, 0.7, 0.4, 0.5],
        ])
        # Target: Turnaround minutes (nominal 45m base)
        y_train = np.array([45.0, 58.0, 78.0, 105.0, 38.0, 62.0])
        self._model.fit(X_train, y_train)

    def predict_turnaround_mins(
        self,
        flight_hours: float,
        payload_kg: float,
        capacity_kg: float,
        weather_severity: float = 0.0,
        age_years: float = 8.0,
    ) -> float:
        """Predict expected turnaround duration in minutes."""
        payload_ratio = min(1.0, payload_kg / max(1.0, capacity_kg))
        features = np.array([[
            flight_hours / 1000.0,
            payload_ratio,
            min(1.0, max(0.0, weather_severity)),
            age_years / 20.0
        ]])
        predicted_mins = float(self._model.predict(features)[0])
        return round(max(30.0, min(180.0, predicted_mins)), 1)

    def predict_delay_probability(self, turnaround_mins: float, planned_turnaround_mins: float = 45.0) -> float:
        """Predict the probability of a departure delay given expected turnaround."""
        excess = turnaround_mins - planned_turnaround_mins
        if excess <= 0:
            return 0.05
        # Logistic curve for delay probability
        prob = 1.0 / (1.0 + np.exp(-0.08 * (excess - 15)))
        return round(float(prob), 3)

