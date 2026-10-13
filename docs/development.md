# Development

## Services

Copy `.env.example` to `.env`, then run `docker compose up --build`. The API is at `localhost:8000`, dashboard at `localhost:3000`, PostgreSQL at `localhost:5432`, and MLflow at `localhost:5000`. Kafka is available to containers as `kafka:9092`.

`docker-compose.override.yml` is automatically applied by Docker Compose for reload-friendly development. Stop the stack with `docker compose down`; add `-v` only when you intend to remove persistent database and MLflow data.

## Checks

Install Python dependencies with `python -m pip install -e ".[dev]"`, then run `python -m pytest` and `python -m ruff check backend streaming ml optimisation simulation evaluation data tests`. Frontend checks are `cd frontend && npm install && npm run lint && npm run build`.

## Extending the starter

Keep API request/response contracts typed, make generated datasets reproducible with fixed seeds, and record benchmark data/configuration alongside metrics. Avoid treating the included static KPI payload or simple baselines as operational grid recommendations.
