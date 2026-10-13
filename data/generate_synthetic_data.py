"""Generate a small deterministic grid asset and load dataset."""

import argparse
import json
import random
from pathlib import Path


def generate(nodes: int, hours: int, seed: int = 42) -> dict[str, object]:
    """Build synthetic assets and hourly demand observations."""
    if nodes <= 0 or hours <= 0:
        raise ValueError("nodes and hours must be positive")
    randomizer = random.Random(seed)
    assets = [
        {
            "asset_id": f"asset-{index:03d}",
            "asset_type": "solar" if index % 3 == 0 else "substation",
            "capacity_mw": round(randomizer.uniform(10, 150), 2),
        }
        for index in range(nodes)
    ]
    demand = [
        {"hour": hour, "demand_mw": round(1000 + 180 * randomizer.random(), 2)}
        for hour in range(hours)
    ]
    return {"seed": seed, "assets": assets, "demand": demand}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/generated/grid.json"))
    parser.add_argument("--nodes", type=int, default=12)
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(generate(args.nodes, args.hours, args.seed), indent=2) + "\n"
    args.output.write_text(payload, encoding="utf-8")
    print(f"Wrote synthetic grid data to {args.output}")


if __name__ == "__main__":
    main()
