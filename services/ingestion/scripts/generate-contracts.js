import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { eventSchemas, EVENT_TYPES } from '../src/contracts.js';
import { sampleEvent } from '../src/sample-events.js';

const schemas = eventSchemas();
const event = { oneOf: EVENT_TYPES.map((type) => ({ $ref: `#/components/schemas/${type}` })) };
const json = (schema) => ({ 'application/json': { schema } });
const response = (schema, description) => ({ description, content: json(schema) });
const receipt = { type: 'object', required: ['eventId', 'cursor', 'disposition', 'duplicate', 'delivery', 'warnings', 'receivedAt'], properties: {
  eventId: { type: 'string', format: 'uuid' }, cursor: { type: 'integer', minimum: 1 },
  disposition: { enum: ['current', 'stale', 'expired'] }, duplicate: { type: 'boolean' },
  delivery: { enum: ['queued', 'published', 'dead', 'not_queued'] }, warnings: { type: 'array', items: { type: 'string' } },
  receivedAt: { type: 'string', format: 'date-time' },
} };
const error = { type: 'object', required: ['error', 'requestId'], properties: {
  error: { type: 'object', required: ['code', 'message'], properties: { code: { type: 'string' }, message: { type: 'string' }, details: {} } },
  requestId: { type: 'string', format: 'uuid' },
} };
const errors = Object.fromEntries([400, 401, 403, 404, 409, 413, 415, 422, 429, 500, 503].map((status) => [status, response(error, 'Structured error; 429/503 may include Retry-After.') ]));
const query = (name, schema) => ({ name, in: 'query', required: false, schema });
const paging = [query('after', { type: 'integer', minimum: 0, maximum: Number.MAX_SAFE_INTEGER, default: 0 }),
  query('limit', { type: 'integer', minimum: 1, maximum: 100, default: 50 })];
const filters = ['sourceId', 'entityId'].map((name) => query(name, { type: 'string', pattern: '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$' }));
filters.push(query('type', { enum: EVENT_TYPES }));
const uuidParam = { name: 'eventId', in: 'path', required: true, schema: { type: 'string', format: 'uuid' } };
const empty = { type: 'object', additionalProperties: false };
const object = { type: 'object' };
const paths = {};
function operation(path, method, summary, { source = false, body, success = object, status = 200, parameters = [] } = {}) {
  paths[path] ??= {};
  paths[path][method] = { summary, security: [{ [source ? 'SourceBearer' : 'AdminBearer']: [] }],
    parameters, ...(body ? { requestBody: { required: true, content: json(body) } } : {}),
    responses: { [status]: response(success, 'Success. Persistence does not imply broker delivery.'), ...errors } };
}
operation('/v1/events', 'post', 'Persist one source-authorized event', { source: true, body: event, success: receipt, status: 201 });
paths['/v1/events'].post.responses[200] = response(receipt, 'Exact duplicate; no new history or outgoing work.');
operation('/v1/events/batch', 'post', 'Persist an atomic batch', { source: true,
  body: { type: 'object', required: ['events'], additionalProperties: false, properties: { events: { type: 'array', minItems: 1, maxItems: 100, items: event } } },
  success: { type: 'object', properties: { receipts: { type: 'array', items: receipt } } } });
operation('/v1/events', 'get', 'Read immutable event history', { parameters: [...paging, ...filters] });
operation('/v1/events/{eventId}', 'get', 'Read an event and its delivery state', { parameters: [uuidParam] });
operation('/v1/state', 'get', 'Read source-specific latest observations with freshness', { parameters: [...paging, ...filters] });
operation('/v1/outbox', 'get', 'Read delivery metadata', { parameters: [...paging, query('status', { enum: ['queued', 'dead', 'published'] })] });
operation('/v1/outbox/{eventId}/retry', 'post', 'Audit and requeue one dead delivery', { body: empty, parameters: [uuidParam] });
operation('/v1/outbox/flush', 'post', 'Drain bounded eligible delivery work', { body: empty });
operation('/v1/retention', 'post', 'Purge bounded eligible settled history older than retention policy', {
  body: { ...empty, properties: { limit: { type: 'integer', minimum: 1, maximum: 1000 },
    after: { type: 'integer', minimum: 0, maximum: Number.MAX_SAFE_INTEGER } } } });
operation('/v1/metrics', 'get', 'Read operational counters without payloads or credentials');
operation('/v1/schema', 'get', 'Read generated input schemas and runtime-validation caveats');
for (const path of ['/health/live', '/health/ready']) paths[path] = { get: { summary: 'Minimal local service health', security: [], responses: {
  200: response(object, 'Healthy'), 503: response(object, 'Not ready'), 429: errors[429],
} } };
const openapi = { openapi: '3.1.0', info: { title: 'Administrative Logistics Ingestion', version: '0.1.0',
  description: 'Noncombat observations only. All JSON objects are strict. Runtime enforces cross-field consistency and observation-time rules beyond JSON Schema. Accepted means durably stored; Kafka delivery is asynchronous and at least once.' },
  servers: [{ url: 'http://127.0.0.1:3100' }], paths,
  components: { securitySchemes: { SourceBearer: { type: 'http', scheme: 'bearer' }, AdminBearer: { type: 'http', scheme: 'bearer' } }, schemas } };
const samples = EVENT_TYPES.map((type, index) => ({ ...sampleEvent(type, { now: Date.parse('2026-10-15T06:00:00Z') }),
  eventId: `00000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}` }));
const artifacts = { 'docs/openapi.json': openapi, 'docs/event-schemas.json': { schemaVersion: 1, schemas }, 'docs/sample-events.json': samples };
mkdirSync('docs', { recursive: true });
for (const [path, value] of Object.entries(artifacts)) {
  const content = JSON.stringify(value, null, 2) + '\n';
  if (process.argv.includes('--check')) {
    if (readFileSync(path, 'utf8').replaceAll('\r\n', '\n') !== content) throw new Error(`Generated contract drift: ${path}`);
  } else writeFileSync(path, content);
}
console.log(process.argv.includes('--check') ? 'Generated contracts match source.' : 'Generated API, schemas, and fictional samples.');
