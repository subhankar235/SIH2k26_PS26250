"""Dynamic corridor threat risk assessment model."""

from typing import Dict, Any


class ThreatRiskScorer:
    """Computes normalized threat risk scores for flight corridors."""

    SEVERITY_WEIGHTS = {
        "low": 0.15,
        "medium": 0.45,
        "high": 0.80,
        "critical": 0.98,
    }

    THREAT_TYPE_WEIGHTS = {
        "sam": 1.0,                 # Surface-to-Air Missile umbrella
        "hostile_aircraft": 0.9,    # Interceptor CAP
        "electronic_warfare": 0.6,  # GPS/comm jamming
        "anti_air_artillery": 0.4,  # Low-altitude AAA
    }

    def compute_risk(self, threat_alert: Dict[str, Any]) -> float:
        """Compute normalized risk score (0.0 to 1.0) from a raw threat report."""
        level = threat_alert.get("threatLevel", "medium").lower()
        level_score = self.SEVERITY_WEIGHTS.get(level, 0.45)

        threat_type = threat_alert.get("threatType", "sam").lower()
        type_weight = self.THREAT_TYPE_WEIGHTS.get(threat_type, 0.7)

        confidence = float(threat_alert.get("confidence", 0.9))

        composite = (level_score * 0.7 + type_weight * 0.3) * confidence
        return round(float(min(1.0, max(0.0, composite))), 3)

