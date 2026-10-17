"""Operational Disruption Simulator - Scenario Injector CLI."""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
import httpx


def load_env_credentials(env_path: Path) -> dict:
    """Extract source bearer tokens from .env file."""
    tokens = {}
    if not env_path.exists():
        return tokens

    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("INGESTION_SOURCES_JSON="):
                raw_json = line.split("=", 1)[1]
                sources = json.loads(raw_json)
                for s in sources:
                    tokens[s["sourceId"]] = s["token"]
    return tokens


def main():
    parser = argparse.ArgumentParser(description="Operational Disruption Simulator - Scenario Injector CLI")
    parser.add_argument(
        "--scenario",
        type=str,
        default=None,
        help="Scenario name (threat_spike, storm_front, mechanical_fault, crew_fatigue)"
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Launch full interactive real-time telemetry HUD with keyboard hotkeys"
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default=os.getenv("INGESTION_API_URL", "http://127.0.0.1:8000"),
        help="Agent engine API base URL"
    )
    args = parser.parse_args()

    # Default to interactive simulator if no specific scenario passed or --interactive
    if args.interactive or not args.scenario:
        from .interactive_simulator import main as sim_main
        sim_main()
        return

    root_dir = Path(__file__).resolve().parent.parent.parent
    env_path = root_dir / "services" / "ingestion" / ".env"
    tokens = load_env_credentials(env_path)

    scenario_file = Path(__file__).parent / "scenarios" / f"{args.scenario}.json"
    if not scenario_file.exists():
        print(f"[ERROR] Scenario file not found: {scenario_file}", file=sys.stderr)
        sys.exit(1)

    with open(scenario_file, "r", encoding="utf-8") as f:
        scenario_data = json.load(f)

    print(f"\n========================================================")
    print(f"[*] INJECTING SCENARIO: {scenario_data.get('scenario').upper()}")
    print(f"[*] Description: {scenario_data.get('description')}")
    print(f"========================================================\n")

    now = datetime.now(timezone.utc)
    valid_until = now + timedelta(hours=2)

    with httpx.Client(timeout=10.0) as client:
        for event_template in scenario_data.get("events", []):
            source_id = event_template["sourceId"]
            token = tokens.get(source_id)

            if not token:
                print(f"[WARN] No token found for source '{source_id}', attempting with demo placeholder.")
                token = "demo-placeholder"

            event = {
                "schemaVersion": 1,
                "eventId": str(uuid.uuid4()),
                "sourceId": source_id,
                "entityId": event_template["entityId"],
                "type": event_template["type"],
                "sequence": int(event_template.get("sequence", 1)),
                "observedAt": now.isoformat().replace("+00:00", "Z"),
                "validUntil": valid_until.isoformat().replace("+00:00", "Z"),
                "data": event_template["data"]
            }

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }

            url = f"{args.api_url}/v1/events"
            try:
                response = client.post(url, json=event, headers=headers)
                status_symbol = "[OK]" if response.status_code in (200, 201) else "[FAIL]"
                print(f"{status_symbol} {event['type']} on {event['entityId']} -> HTTP {response.status_code}")
                if response.status_code not in (200, 201):
                    print(f"     Response: {response.text}")
            except Exception as e:
                print(f"[ERROR] Connection to {url} failed: {e}")

    print("\n[+] Injection batch complete. Observing dynamic adaptation.\n")


if __name__ == "__main__":
    main()

