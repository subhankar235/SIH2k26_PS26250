"""Tests for operational disruption scenario injector."""

import pytest
import json
from pathlib import Path
from simulator.injector import load_env_credentials


def test_scenario_files_exist_and_valid():
    scenarios_dir = Path(__file__).resolve().parent.parent / "scenarios"
    assert scenarios_dir.exists()

    required_scenarios = ["threat_spike.json", "storm_front.json", "mechanical_fault.json"]
    for sc_name in required_scenarios:
        sc_file = scenarios_dir / sc_name
        assert sc_file.exists()
        with open(sc_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert "scenario" in data
            assert "events" in data
            assert len(data["events"]) > 0
            for ev in data["events"]:
                assert "sourceId" in ev
                assert "entityId" in ev
                assert "type" in ev
                assert "data" in ev

