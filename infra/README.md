# Infrastructure

`docker-compose.yml` starts the local PostgreSQL, Kafka (KRaft), and MLflow services. The initial PostgreSQL schema is in `db/init.sql`; place versioned migrations in `db/migrations/` as the schema evolves. Container definitions live under `docker/`.
