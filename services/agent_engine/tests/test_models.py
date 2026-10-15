"""Tests for domain predictive models."""

import pytest
from models.turnaround import TurnaroundPredictor
from models.weather_trend import WeatherTrendPredictor
from models.threat_scorer import ThreatRiskScorer


def test_turnaround_predictor():
    predictor = TurnaroundPredictor()
    # Light aircraft, light load, clear weather
    mins_light = predictor.predict_turnaround_mins(
        flight_hours=500.0,
        payload_kg=3000.0,
        capacity_kg=20000.0,
        weather_severity=0.0
    )
    assert 30.0 <= mins_light <= 60.0

    # Heavy hours, full payload, severe weather
    mins_heavy = predictor.predict_turnaround_mins(
        flight_hours=5000.0,
        payload_kg=20000.0,
        capacity_kg=20000.0,
        weather_severity=0.8
    )
    assert mins_heavy > mins_light

    prob_low = predictor.predict_delay_probability(turnaround_mins=40.0)
    prob_high = predictor.predict_delay_probability(turnaround_mins=85.0)
    assert prob_low < prob_high


def test_weather_trend_predictor():
    predictor = WeatherTrendPredictor()
    # Clear weather
    risk_clear = predictor.predict_degradation_risk("clear", wind_speed_mps=4.0, visibility_m=10000.0, temperature_c=25.0)
    assert risk_clear < 0.2

    # High winds, low visibility
    risk_deteriorating = predictor.predict_degradation_risk("rain", wind_speed_mps=28.0, visibility_m=1200.0, temperature_c=18.0)
    assert risk_deteriorating > 0.6

    # Active storm
    risk_storm = predictor.predict_degradation_risk("storm", wind_speed_mps=30.0, visibility_m=500.0, temperature_c=15.0)
    assert risk_storm == 1.0


def test_threat_risk_scorer():
    scorer = ThreatRiskScorer()
    low_alert = {"threatLevel": "low", "threatType": "electronic_warfare", "confidence": 0.8}
    score_low = scorer.compute_risk(low_alert)
    assert score_low < 0.35

    critical_sam = {"threatLevel": "critical", "threatType": "sam", "confidence": 1.0}
    score_critical = scorer.compute_risk(critical_sam)
    assert score_critical > 0.9

