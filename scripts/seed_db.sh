#!/usr/bin/env sh
set -eu
python -m data.generate_synthetic_data --output data/generated/grid.json --nodes 12 --hours 24
echo "Synthetic seed data generated at data/generated/grid.json."
