.PHONY: up down test lint seed bench

up:
	docker compose up --build

down:
	docker compose down

test:
	python -m pytest

lint:
	python -m ruff check backend streaming ml optimisation simulation evaluation data tests
	cd frontend && npm run lint

seed:
	python -m data.generate_synthetic_data --output data/generated/grid.json --nodes 12 --hours 24

bench:
	python -m evaluation.benchmark
