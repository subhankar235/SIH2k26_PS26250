# Durable administrative Kafka reader

The standalone reader projects reported administrative facts into its own SQLite database. It uses the gateway's canonical event validator and five topic contracts. It does not compute readiness, assign resources, schedule missions, assess threats or make operational decisions.

Run from `services/ingestion` after configuring the existing `.env`:

```powershell
node --env-file-if-exists=.env src/transport/consumer-cli.js
```

The CLI reuses `loadConfig` for broker/TLS/SASL validation, so existing `INGESTION_ADMIN_TOKEN` and `INGESTION_SOURCES_JSON` configuration must be valid even though the reader does not use bearer credentials. `KAFKA_BROKERS` is required. Plaintext brokers must be loopback; remote brokers require TLS; SASL also requires TLS. Logs contain only static lifecycle codes, never broker error text or credentials.

| Variable | Default | Bounds |
| --- | --- | --- |
| `CONSUMER_GROUP_ID` | `logistics-read-model-v1` | 1–128 identifier characters |
| `CONSUMER_DB_PATH` | `var/read-model.sqlite` | Resolved relative to service directory; must differ from ingestion DB |
| `CONSUMER_MAX_EVENTS` | 100000 | 1–1000000 |
| `CONSUMER_MAX_QUARANTINE` | 1000 | 1–100000 |
| `CONSUMER_MAX_CHECKPOINTS` | 10000 | 1–100000 |
| `CONSUMER_MAX_MESSAGE_BYTES` | 65536 | 1024–1048576 |
| `CONSUMER_MAX_DB_BYTES` | 268435456 | 1048576–2147483648 |

One process owns one local database per consumer group. SQLite exclusive locking refuses concurrent owners, and the database records its group/schema identity. An existing ingestion or other application's database is rejected. The gateway and reader must use separate paths. This is a local development design, without high availability or shared network filesystem support. Give the database directory the same restricted permissions as ingestion storage.

Each message atomically updates validated history, event-ID/content dedupe, source/type/entity projection, and the next broker offset in SQLite before broker acknowledgment. Offset identity is topic plus partition; decimal strings and BigInt preserve signed 64-bit Kafka precision. The broker is immutable per topic/partition/offset: topic deletion/recreation requires a fresh group and database, otherwise old checkpoints could suppress unrelated offsets.

Delivery remains at least once. A crash after database commit but before broker acknowledgment replays safely against the durable checkpoint. Repeated event IDs with identical canonical content do not duplicate history; conflicting IDs are quarantined. Lower sequence, older observation and expired updates cannot replace a current projection. Different sources retain independent assertions. Reading `latest({limit})` reports current TTL expiry without deleting evidence or selecting a source as truth. Results are bounded to 1–1000 rows; `quarantined({limit})` has the same bounds, and `stats()` returns stored row counts.

Invalid JSON/UTF-8, invalid schema, wrong topic/key, missing value, oversized payload and conflicting IDs are quarantined. Quarantine stores only known topic, partition, decimal offset, static reason, byte lengths and receipt time. It never stores raw payloads, headers, keys, validation paths or credential strings. Unusable broker coordinates fail consumption because no trustworthy checkpoint identity can be recorded.

History/dedupe and quarantine evidence are append-only within their explicit capacities. There is no automatic TTL deletion: removing dedupe while Kafka can replay would lose the idempotency guarantee. A full row capacity, checkpoint capacity, physical database page limit or database error rolls back the message and prevents its acknowledgment. KafkaJS automatic commit and automatic crash restart are disabled. Operators must investigate capacity failures and deliberately raise limits or archive/rebuild; the worker does not silently discard evidence to resume.

SQLite uses synchronous FULL and DELETE journal mode. The database file is capped to page-rounded `CONSUMER_MAX_DB_BYTES`; transient rollback journal storage can additionally approach the database size, so reserve roughly twice that capacity plus filesystem overhead. Free disk exhaustion also fails without acknowledgment. A database lost/restored independently of a broker group cannot reconstruct already committed broker records automatically: stop the worker and explicitly reset the group's broker offsets to retained history before rebuilding. Kafka retention can prevent complete reconstruction; do not claim complete replay when records are no longer retained.

To archive/rebuild: stop the reader, archive the entire database outside the active path using normal backup procedures, retain evidence as required, then start a fresh database and fresh group to read retained topic history. Resetting broker offsets with the existing database deliberately exercises checkpoint replay, but does not clear its history. Do not manually delete rows or modify checkpoints to bypass saturation. `SIGINT`/`SIGTERM` stop/disconnect the consumer before closing SQLite; processing failures terminate with exit status 1. CLI shutdown has a hard 15-second failure deadline if broker cleanup never settles.

Verification:

```powershell
node --test test/consumer*.test.js
$env:KAFKA_TEST_BROKERS='localhost:29092'
node --test integration/consumer.test.js
```

The integration test requires a real broker and fails when none is configured. It verifies restart, deliberate broker rewind, dedupe, projection, durable quarantine and acknowledged offsets. Consumer semantics were checked against [KafkaJS consumption documentation](https://kafka.js.org/docs/consuming) and [Node 24 SQLite documentation](https://nodejs.org/docs/latest-v24.x/api/sqlite.html), retrieved through Context7.
