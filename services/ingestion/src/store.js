import { DatabaseSync } from 'node:sqlite';
import { createHash } from 'node:crypto';
import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';
import { ApiError } from './errors.js';
import { canonicalJson, TOPICS } from './contracts.js';

const MAX_PAGE = 100;
function pageOptions({ after = 0, limit = 50 } = {}) {
  if (!Number.isSafeInteger(after) || after < 0 || !Number.isInteger(limit) || limit < 1 || limit > MAX_PAGE) {
    throw new ApiError(422, 'INVALID_QUERY', 'Pagination requires a nonnegative cursor and limit from 1 to 100.');
  }
  return { after, limit };
}
function pagination(rows, limit, map) {
  const hasMore = rows.length > limit;
  const items = rows.slice(0, limit).map(map);
  return { items, nextCursor: hasMore ? items.at(-1).cursor : null };
}

/** Transactional history and outbox for one service process per local database. */
export class EventStore {
  constructor({ path, now = Date.now, maxPending = 10000 }) {
    if (!path || !Number.isInteger(maxPending) || maxPending < 1) throw new Error('Invalid store configuration.');
    this.now = now;
    this.maxPending = maxPending;
    if (path !== ':memory:') mkdirSync(dirname(path), { recursive: true });
    this.db = new DatabaseSync(path);
    try {
      this.db.exec('PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000; PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;');
      const version = this.db.prepare('PRAGMA user_version').get().user_version;
      if (version > 1) throw new Error('Unsupported database schema version.');
      this.db.exec(`
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE,
          source_id TEXT NOT NULL, event_type TEXT NOT NULL, entity_id TEXT NOT NULL,
          sequence INTEGER NOT NULL, observed_ms INTEGER NOT NULL, valid_until_ms INTEGER NOT NULL,
          received_ms INTEGER NOT NULL, event_json TEXT NOT NULL, content_hash TEXT NOT NULL,
          disposition TEXT NOT NULL, warnings_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS events_stream ON events(source_id,event_type,entity_id,id);
        CREATE TABLE IF NOT EXISTS projections (
          source_id TEXT NOT NULL,event_type TEXT NOT NULL,entity_id TEXT NOT NULL,
          event_cursor INTEGER NOT NULL REFERENCES events(id),
          PRIMARY KEY(source_id,event_type,entity_id)
        );
        CREATE TABLE IF NOT EXISTS outbox (
          event_cursor INTEGER PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE,
          topic TEXT NOT NULL,message_key TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'queued',
          attempts INTEGER NOT NULL DEFAULT 0,next_attempt_ms INTEGER NOT NULL,
          updated_ms INTEGER NOT NULL,last_error_code TEXT
        );
        CREATE INDEX IF NOT EXISTS outbox_due ON outbox(status,next_attempt_ms,event_cursor);
        CREATE TABLE IF NOT EXISTS audit (
          id INTEGER PRIMARY KEY AUTOINCREMENT,action TEXT NOT NULL,event_id TEXT,occurred_ms INTEGER NOT NULL
        );
        PRAGMA user_version=1;
      `);
    } catch (error) { this.db.close(); throw error; }
  }

  transaction(action) {
    this.db.exec('BEGIN IMMEDIATE');
    try { const result = action(); this.db.exec('COMMIT'); return result; }
    catch (error) { this.db.exec('ROLLBACK'); throw error; }
  }

  receipt(row, duplicate = false) {
    const outbox = this.db.prepare('SELECT status FROM outbox WHERE event_cursor=?').get(row.id);
    return { eventId: row.event_id, cursor: row.id, disposition: row.disposition, duplicate,
      delivery: outbox?.status ?? 'not_queued', warnings: JSON.parse(row.warnings_json),
      receivedAt: new Date(row.received_ms).toISOString() };
  }

  record(row) {
    return { ...this.receipt(row), event: JSON.parse(row.event_json) };
  }

  acceptBatch(events) {
    if (!Array.isArray(events) || events.length < 1 || events.length > 100) {
      throw new ApiError(422, 'INVALID_BATCH', 'A batch must contain 1 to 100 events.');
    }
    return this.transaction(() => {
      const now = this.now();
      let backlog = this.db.prepare("SELECT COUNT(*) AS count FROM outbox WHERE status IN ('queued','dead')").get().count;
      return events.map((event) => {
        const serialized = canonicalJson(event);
        const hash = createHash('sha256').update(serialized).digest('hex');
        const existing = this.db.prepare('SELECT * FROM events WHERE event_id=?').get(event.eventId);
        if (existing) {
          if (existing.content_hash !== hash) throw new ApiError(409, 'EVENT_ID_CONFLICT', 'Event ID already belongs to different content.');
          return this.receipt(existing, true);
        }
        const latest = this.db.prepare(`SELECT e.* FROM projections p JOIN events e ON e.id=p.event_cursor
          WHERE p.source_id=? AND p.event_type=? AND p.entity_id=?`).get(event.sourceId, event.type, event.entityId);
        const observed = Date.parse(event.observedAt);
        const expires = Date.parse(event.validUntil);
        let disposition = 'current';
        if (expires <= now) disposition = 'expired';
        else if (latest && (event.sequence <= latest.sequence || observed < latest.observed_ms)) disposition = 'stale';
        const warnings = latest && event.sequence > latest.sequence + 1 ? ['sequence_gap'] : [];
        if (disposition === 'current' && backlog >= this.maxPending) {
          throw new ApiError(503, 'BACKLOG_FULL', 'Delivery backlog is full; retry later.');
        }
        const inserted = this.db.prepare(`INSERT INTO events(event_id,source_id,event_type,entity_id,sequence,
          observed_ms,valid_until_ms,received_ms,event_json,content_hash,disposition,warnings_json)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?)`).run(event.eventId, event.sourceId, event.type, event.entityId,
          event.sequence, observed, expires, now, serialized, hash, disposition, JSON.stringify(warnings));
        const cursor = Number(inserted.lastInsertRowid);
        if (disposition === 'current') {
          this.db.prepare(`INSERT INTO projections(source_id,event_type,entity_id,event_cursor) VALUES(?,?,?,?)
            ON CONFLICT(source_id,event_type,entity_id) DO UPDATE SET event_cursor=excluded.event_cursor`)
            .run(event.sourceId, event.type, event.entityId, cursor);
          this.db.prepare('INSERT INTO outbox(event_cursor,topic,message_key,next_attempt_ms,updated_ms) VALUES(?,?,?,?,?)')
            .run(cursor, TOPICS[event.type], `${event.sourceId}:${event.entityId}`, now, now);
          backlog++;
        }
        return this.receipt(this.db.prepare('SELECT * FROM events WHERE id=?').get(cursor));
      });
    });
  }

  getEvent(eventId) {
    const row = this.db.prepare('SELECT * FROM events WHERE event_id=?').get(eventId);
    return row ? this.record(row) : null;
  }

  filters(options, alias = 'e') {
    const clauses = []; const values = [];
    for (const [key, column] of [['sourceId', 'source_id'], ['type', 'event_type'], ['entityId', 'entity_id']]) {
      if (options[key] !== undefined) { clauses.push(`${alias}.${column}=?`); values.push(options[key]); }
    }
    return { clauses, values };
  }

  listEvents(options = {}) {
    const { after, limit } = pageOptions(options);
    const { clauses, values } = this.filters(options);
    const rows = this.db.prepare(`SELECT e.* FROM events e WHERE e.id>? ${clauses.length ? `AND ${clauses.join(' AND ')}` : ''}
      ORDER BY e.id LIMIT ?`).all(after, ...values, limit + 1);
    return pagination(rows, limit, (row) => this.record(row));
  }

  listState(options = {}) {
    const { after, limit } = pageOptions(options); const { clauses, values } = this.filters(options);
    const rows = this.db.prepare(`SELECT e.* FROM projections p JOIN events e ON e.id=p.event_cursor
      WHERE e.id>? ${clauses.length ? `AND ${clauses.join(' AND ')}` : ''} ORDER BY e.id LIMIT ?`)
      .all(after, ...values, limit + 1);
    const now = this.now();
    return pagination(rows, limit, (row) => ({ ...this.record(row),
      freshness: row.valid_until_ms > now ? 'current' : 'expired', ageMs: Math.max(0, now - row.observed_ms) }));
  }

  listOutbox(options = {}) {
    const { after, limit } = pageOptions(options);
    const status = options.status;
    if (status && !['queued', 'dead', 'published'].includes(status)) throw new ApiError(422, 'INVALID_QUERY', 'Invalid delivery status.');
    const rows = this.db.prepare(`SELECT o.*,e.event_id FROM outbox o JOIN events e ON e.id=o.event_cursor
      WHERE o.event_cursor>? ${status ? 'AND o.status=?' : ''} ORDER BY o.event_cursor LIMIT ?`)
      .all(after, ...(status ? [status] : []), limit + 1);
    return pagination(rows, limit, (row) => ({ cursor: row.event_cursor, eventId: row.event_id, topic: row.topic,
      key: row.message_key, status: row.status, attempts: row.attempts,
      nextAttemptAt: new Date(row.next_attempt_ms).toISOString(), lastErrorCode: row.last_error_code }));
  }

  pending({ limit = 50 } = {}) {
    pageOptions({ limit });
    return this.db.prepare(`SELECT o.*,e.event_id,e.event_json FROM outbox o JOIN events e ON e.id=o.event_cursor
      WHERE o.status='queued' AND o.next_attempt_ms<=? ORDER BY o.event_cursor LIMIT ?`).all(this.now(), limit)
      .map((row) => ({ cursor: row.event_cursor, eventId: row.event_id, topic: row.topic,
        key: row.message_key, attempts: row.attempts, event: JSON.parse(row.event_json) }));
  }

  markPublished(cursor) {
    this.db.prepare("UPDATE outbox SET status='published',updated_ms=?,last_error_code=NULL WHERE event_cursor=? AND status='queued'")
      .run(this.now(), cursor);
  }

  markFailed(cursor, { maxAttempts, baseDelayMs, maxDelayMs, code = 'PUBLISH_FAILED' }) {
    const row = this.db.prepare("SELECT * FROM outbox WHERE event_cursor=? AND status='queued'").get(cursor);
    if (!row) return;
    const attempts = row.attempts + 1;
    const delay = Math.min(maxDelayMs, baseDelayMs * 2 ** Math.min(attempts - 1, 30));
    this.db.prepare('UPDATE outbox SET status=?,attempts=?,next_attempt_ms=?,updated_ms=?,last_error_code=? WHERE event_cursor=?')
      .run(attempts >= maxAttempts ? 'dead' : 'queued', attempts, this.now() + delay, this.now(), code, cursor);
  }

  retryDead(eventId) {
    return this.transaction(() => {
      const row = this.db.prepare('SELECT o.* FROM outbox o JOIN events e ON e.id=o.event_cursor WHERE e.event_id=?').get(eventId);
      if (!row) throw new ApiError(404, 'NOT_FOUND', 'Delivery record not found.');
      if (row.status !== 'dead') throw new ApiError(409, 'OUTBOX_NOT_DEAD', 'Only dead delivery records can be retried.');
      this.db.prepare("UPDATE outbox SET status='queued',attempts=0,next_attempt_ms=?,updated_ms=?,last_error_code=NULL WHERE event_cursor=?")
        .run(this.now(), this.now(), row.event_cursor);
      this.db.prepare("INSERT INTO audit(action,event_id,occurred_ms) VALUES('outbox.retry',?,?)").run(eventId, this.now());
      return { eventId, delivery: 'queued' };
    });
  }

  purge({ before, limit = 1000 }) {
    if (!Number.isSafeInteger(before) || !Number.isInteger(limit) || limit < 1 || limit > 1000) {
      throw new ApiError(422, 'INVALID_RETENTION', 'Invalid retention bounds.');
    }
    return this.transaction(() => {
      const rows = this.db.prepare(`SELECT e.id FROM events e WHERE received_ms<?
        AND NOT EXISTS(SELECT 1 FROM projections p WHERE p.event_cursor=e.id)
        AND NOT EXISTS(SELECT 1 FROM outbox o WHERE o.event_cursor=e.id AND o.status!='published')
        ORDER BY e.id LIMIT ?`).all(before, limit);
      const remove = this.db.prepare('DELETE FROM events WHERE id=?');
      for (const row of rows) remove.run(row.id);
      this.db.prepare('DELETE FROM audit WHERE occurred_ms<? AND id IN (SELECT id FROM audit ORDER BY id LIMIT ?)').run(before, limit);
      this.db.prepare("INSERT INTO audit(action,occurred_ms) VALUES('retention.purge',?)").run(this.now());
      return { deleted: rows.length };
    });
  }

  metrics() {
    const counts = { queued: 0, dead: 0, published: 0 };
    for (const row of this.db.prepare('SELECT status,COUNT(*) AS count FROM outbox GROUP BY status').all()) counts[row.status] = row.count;
    return { events: this.db.prepare('SELECT COUNT(*) AS count FROM events').get().count,
      projectedEntities: this.db.prepare('SELECT COUNT(*) AS count FROM projections').get().count,
      audits: this.db.prepare('SELECT COUNT(*) AS count FROM audit').get().count,
      outbox: counts, maxPending: this.maxPending };
  }

  ready() { return this.db.prepare('SELECT 1 AS ready').get().ready === 1; }
  close() { this.db.close(); }
}
