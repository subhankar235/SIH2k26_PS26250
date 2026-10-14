import { readFileSync, appendFileSync } from 'node:fs';
import { randomBytes } from 'node:crypto';
if (process.argv.length !== 2) throw new Error('Usage: npm run viewer:credentials');
const content = readFileSync('.env', 'utf8');
if (/^\s*MONITOR_VIEWER_TOKEN\s*=/m.test(content)) throw new Error('Viewer configuration already exists; refusing to overwrite it.');
appendFileSync('.env', `${content.endsWith('\n') ? '' : '\n'}MONITOR_VIEWER_TOKEN=${randomBytes(36).toString('base64url')}\n`);
console.log('Separate read-only viewer credential added to .env. No secret was printed.');
