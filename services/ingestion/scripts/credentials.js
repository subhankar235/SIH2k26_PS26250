import { randomBytes } from 'node:crypto';
import { writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { EVENT_TYPES } from '../src/contracts.js';

const arguments_ = process.argv.slice(2);
if (arguments_.length > 2 || (arguments_.length && arguments_[0] !== '--write') || arguments_.length === 1) {
  throw new Error('Usage: npm run credentials -- [--write .env]');
}
const destination = resolve(arguments_[1] ?? '.env');
const sources = EVENT_TYPES.map((type) => ({ sourceId: `demo-${type.split('.')[0]}`,
  token: randomBytes(36).toString('base64url'), types: [type] }));
const config = [`INGESTION_ADMIN_TOKEN=${randomBytes(36).toString('base64url')}`,
  `INGESTION_SOURCES_JSON=${JSON.stringify(sources)}`, 'HOST=127.0.0.1', 'PORT=3100',
  'INGESTION_DB_PATH=var/events.sqlite', 'KAFKA_BROKERS=', 'KAFKA_TLS=false', ''];
// Exclusive creation refuses to overwrite an existing credential file.
writeFileSync(destination, config.join('\n'), { flag: 'wx', mode: 0o600 });
process.stdout.write('Credential file created. Tokens were not printed. Protect this file and never commit it.\n');
