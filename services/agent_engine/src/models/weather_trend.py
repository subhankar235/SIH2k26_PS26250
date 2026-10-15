"""Weather degradation trend predictor for destination airbases."""

import numpy as np


class WeatherTrendPredictor:
    """Predicts weather degradation probability at arrival airbases."""

    def predict_degradation_risk(
        self,
        current_condition: str,
        wind_speed_mps: float,
        visibility_m: float,
        temperature_c: float,
        hours_ahead: float = 2.0,
    ) -> float:
        """Estimate the probability (0.0 to 1.0) of weather deteriorating to storm/no-fly status."""
        base_risk = 0.05
        if current_condition == "storm":
            return 1.0
        elif current_condition in ("rain", "fog", "snow"):
            base_risk = 0.35

        # Wind factor: speeds > 15 m/s increase degradation probability
        wind_factor = max(0.0, (wind_speed_mps - 10.0) / 25.0)

        # Visibility factor: visibility < 3000m indicates rapid fog/cloud drop
        vis_factor = max(0.0, (4000.0 - visibility_m) / 4000.0) if visibility_m < 4000.0 else 0.0

        # Time horizon extrapolation
        time_growth = 1.0 + (0.15 * min(6.0, hours_ahead))

        composite_risk = (base_risk + 0.3 * wind_factor + 0.35 * vis_factor) * time_growth
        return round(float(np.clip(composite_risk, 0.0, 1.0)), 3)

