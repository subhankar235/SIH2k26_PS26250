import { DatabaseSync } from 'node:sqlite';
import { createHash } from 'node:crypto';
import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { TextDecoder } from 'node:util';
import { TOPICS, canonicalJson, validateEvent } from './contracts.js';

const topics = new Set(Object.values(TOPICS));
const decoder = new TextDecoder('utf-8', { fatal: true });
const error = (code) => Object.assign(new Error(code), { code });
function bounded(value, min, max) { return Number.isSafeInteger(value) && value >= min && value <= max; }
function coordinates({ topic, partition, message }) {
  if (!topics.has(topic) || !bounded(partition, 0, 2147483647) ||
    typeof message?.offset !== 'string' || !/^(0|[1-9][0-9]{0,18})$/.test(message.offset) ||
    BigInt(message.offset) >= 9223372036854775807n) throw error('CONSUMER_COORDINATES');
  return (BigInt(message.offset) + 1n).toString();
}
function decode(message, topic, now, maxBytes) {
  if (!Buffer.isBuffer(message.value)) return { reason: 'MISSING_VALUE' };
  if (message.value.length > maxBytes) return { reason: 'MESSAGE_TOO_LARGE' };
  let input;
  try { input = JSON.parse(decoder.decode(message.value)); } catch { return { reason: 'INVALID_JSON' }; }
  let event;
  try { event = validateEvent(input, { now }); } catch { return { reason: 'INVALID_SCHEMA' }; }
  if (TOPICS[event.type] !== topic) return { reason: 'TOPIC_MISMATCH' };
  if (!Buffer.isBuffer(message.key) || message.key.length > 129 ||
    !message.key.equals(Buffer.from(`${event.sourceId}:${event.entityId}`))) return { reason: 'KEY_MISMATCH' };
  const json = canonicalJson(event);
  return { event, json, hash: createHash('sha256').update(json).digest('hex') };
}

/** Append-only local read model. Retaining every dedupe ID avoids unsafe replay after TTL deletion. */
export class ConsumerStore {
  constructor({ path, groupId, now = Date.now, maxEvents = 100000, maxQuarantine = 1000,
    maxCheckpoints = 10000, maxMessageBytes = 65536, maxDatabaseBytes = 268435456 }) {
    if (typeof path !== 'string' || !path || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(groupId ?? '') ||
      !bounded(maxEvents, 1, 1000000) || !bounded(maxQuarantine, 1, 100000) ||
      !bounded(maxCheckpoints, 1, 100000) || !bounded(maxMessageBytes, 1024, 1048576) ||
      !bounded(maxDatabaseBytes, 1048576, 2147483648) || typeof now !== 'function') throw error('CONSUMER_CONFIG');
    Object.assign(this, { now, maxEvents, maxQuarantine, maxCheckpoints, maxMessageBytes });
    if (path !== ':memory:') mkdirSync(dirname(path), { recursive: true });
    this.db = new DatabaseSync(path);
    try {
      // Holding SQLite's exclusive lock also prevents a second process owning this read model.
      // DELETE journal mode bounds temporary journal growth to approximately the database size.
      this.db.exec('PRAGMA busy_timeout=0; PRAGMA locking_mode=EXCLUSIVE; BEGIN EXCLUSIVE; COMMIT;');
      const tables = this.db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").all();
      const allowed = new Set(['consumer_meta', 'consumer_events', 'consumer_latest', 'consumer_quarantine', 'consumer_checkpoints']);
      if (tables.some(({ name }) => !allowed.has(name))) throw error('CONSUMER_DATABASE_NOT_OWNED');
      if (tables.length) {
        const meta = this.db.prepare('SELECT group_id,version FROM consumer_meta').get();
        if (meta?.version !== 1 || meta.group_id !== groupId) throw error('CONSUMER_DATABASE_NOT_OWNED');
      }
      this.db.exec('PRAGMA foreign_keys=ON; PRAGMA journal_mode=DELETE; PRAGMA synchronous=FULL;');
      const pageSize = this.db.prepare('PRAGMA page_size').get().page_size;
      const maxPages = Math.floor(maxDatabaseBytes / pageSize);
      if (this.db.prepare('PRAGMA page_count').get().page_count > maxPages) throw error('CONSUMER_CAPACITY');
      this.db.exec(`PRAGMA max_page_count=${maxPages}`);
      this.db.exec('BEGIN IMMEDIATE');
      this.db.exec(`
        CREATE TABLE IF NOT EXISTS consumer_meta(group_id TEXT PRIMARY KEY,version INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS consumer_events(
          id INTEGER PRIMARY KEY,event_id TEXT NOT NULL UNIQUE,source_id TEXT NOT NULL,event_type TEXT NOT NULL,
          entity_id TEXT NOT NULL,sequence INTEGER NOT NULL,observed_ms INTEGER NOT NULL,valid_until_ms INTEGER NOT NULL,
          received_ms INTEGER NOT NULL,event_json TEXT NOT NULL,content_hash TEXT NOT NULL,disposition TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS consumer_latest(source_id TEXT NOT NULL,event_type TEXT NOT NULL,entity_id TEXT NOT NULL,
          event_cursor INTEGER NOT NULL REFERENCES consumer_events(id),PRIMARY KEY(source_id,event_type,entity_id));
        CREATE TABLE IF NOT EXISTS consumer_quarantine(id INTEGER PRIMARY KEY,topic TEXT NOT NULL,partition_id INTEGER NOT NULL,
          broker_offset TEXT NOT NULL,reason TEXT NOT NULL,value_bytes INTEGER NOT NULL,key_bytes INTEGER NOT NULL,
          received_ms INTEGER NOT NULL,UNIQUE(topic,partition_id,broker_offset));
        CREATE TABLE IF NOT EXISTS consumer_checkpoints(topic TEXT NOT NULL,partition_id INTEGER NOT NULL,next_offset TEXT NOT NULL,
          PRIMARY KEY(topic,partition_id));
      `);
      this.db.prepare('INSERT OR IGNORE INTO consumer_meta(group_id,version) VALUES(?,1)').run(groupId);
      this.db.exec('COMMIT');
    } catch (failure) {
      try { this.db.exec('ROLLBACK'); } catch { /* no transaction may have started */ }
      this.db.close(); throw failure;
    }
  }

  checkpoint(topic, partition) {
    return this.db.prepare('SELECT next_offset FROM consumer_checkpoints WHERE topic=? AND partition_id=?').get(topic, partition)?.next_offset ?? null;
  }

  process(record) {
    const nextOffset = coordinates(record); const { topic, partition, message } = record;
    const now = this.now(); if (!Number.isFinite(now)) throw error('CONSUMER_CLOCK');
    this.db.exec('BEGIN IMMEDIATE');
    try {
      const checkpoint = this.checkpoint(topic, partition);
      if (checkpoint !== null && BigInt(nextOffset) <= BigInt(checkpoint)) {
        this.db.exec('COMMIT'); return { disposition: 'replayed', nextOffset: checkpoint };
      }
      if (checkpoint === null && this.#count('consumer_checkpoints') >= this.maxCheckpoints) throw error('CONSUMER_CAPACITY');
      const parsed = decode(message, topic, now, this.maxMessageBytes);
      let disposition; let reason = parsed.reason;
      if (!reason) {
        const prior = this.db.prepare('SELECT content_hash FROM consumer_events WHERE event_id=?').get(parsed.event.eventId);
        if (prior) { if (prior.content_hash !== parsed.hash) reason = 'EVENT_ID_CONFLICT'; else disposition = 'duplicate'; }
      }
      if (reason) {
        if (this.#count('consumer_quarantine') >= this.maxQuarantine) throw error('CONSUMER_CAPACITY');
        // Only allowlisted broker coordinates, byte lengths, static reason and receipt time; never keys, headers or payloads.
        this.db.prepare(`INSERT INTO consumer_quarantine(topic,partition_id,broker_offset,reason,value_bytes,key_bytes,received_ms)
          VALUES(?,?,?,?,?,?,?)`).run(topic, partition, message.offset, reason,
          Buffer.isBuffer(message.value) ? message.value.length : 0, Buffer.isBuffer(message.key) ? message.key.length : 0, now);
        disposition = 'quarantined';
      } else if (!disposition) {
        if (this.#count('consumer_events') >= this.maxEvents) throw error('CONSUMER_CAPACITY');
        const { event, json, hash } = parsed; const observed = Date.parse(event.observedAt); const expiry = Date.parse(event.validUntil);
        const latest = this.db.prepare(`SELECT e.* FROM consumer_latest p JOIN consumer_events e ON e.id=p.event_cursor
          WHERE p.source_id=? AND p.event_type=? AND p.entity_id=?`).get(event.sourceId, event.type, event.entityId);
        disposition = expiry <= now ? 'expired' : latest && (event.sequence <= latest.sequence || observed < latest.observed_ms) ? 'stale' : 'current';
        const result = this.db.prepare(`INSERT INTO consumer_events(event_id,source_id,event_type,entity_id,sequence,
          observed_ms,valid_until_ms,received_ms,event_json,content_hash,disposition) VALUES(?,?,?,?,?,?,?,?,?,?,?)`)
          .run(event.eventId, event.sourceId, event.type, event.entityId, event.sequence, observed, expiry, now, json, hash, disposition);
        if (disposition === 'current') this.db.prepare(`INSERT INTO consumer_latest(source_id,event_type,entity_id,event_cursor) VALUES(?,?,?,?)
          ON CONFLICT(source_id,event_type,entity_id) DO UPDATE SET event_cursor=excluded.event_cursor`)
          .run(event.sourceId, event.type, event.entityId, Number(result.lastInsertRowid));
      }
      this.db.prepare(`INSERT INTO consumer_checkpoints(topic,partition_id,next_offset) VALUES(?,?,?)
        ON CONFLICT(topic,partition_id) DO UPDATE SET next_offset=excluded.next_offset`).run(topic, partition, nextOffset);
      this.db.exec('COMMIT'); return { disposition, ...(reason ? { reason } : {}), nextOffset };
    } catch (failure) {
      try { this.db.exec('ROLLBACK'); } catch { /* SQLITE_FULL can already roll back; preserve original failure. */ }
      throw failure;
    }
  }

  #count(table) { return this.db.prepare(`SELECT COUNT(*) AS count FROM ${table}`).get().count; }
  stats() { return { events: this.#count('consumer_events'), quarantine: this.#count('consumer_quarantine'), checkpoints: this.#count('consumer_checkpoints') }; }
  latest({ limit = 100 } = {}) {
    if (!bounded(limit, 1, 1000)) throw error('CONSUMER_QUERY');
    return this.db.prepare(`SELECT e.* FROM consumer_latest p JOIN consumer_events e ON e.id=p.event_cursor ORDER BY e.id LIMIT ?`).all(limit)
      .map((row) => ({ cursor: row.id, event: JSON.parse(row.event_json), receivedAt: new Date(row.received_ms).toISOString(),
        disposition: row.valid_until_ms <= this.now() ? 'expired' : row.disposition }));
  }
  quarantined({ limit = 100 } = {}) {
    if (!bounded(limit, 1, 1000)) throw error('CONSUMER_QUERY');
    return this.db.prepare('SELECT * FROM consumer_quarantine ORDER BY id DESC LIMIT ?').all(limit).map((row) => ({
      cursor: row.id, topic: row.topic, partition: row.partition_id, offset: row.broker_offset,
      reason: row.reason, valueBytes: row.value_bytes, keyBytes: row.key_bytes, receivedAt: new Date(row.received_ms).toISOString(),
    }));
  }
  close() { if (!this.closed) { this.db.close(); this.closed = true; } }
}
