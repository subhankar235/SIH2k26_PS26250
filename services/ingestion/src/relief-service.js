import { randomUUID, createHash } from 'node:crypto';
import { z } from 'zod';
import { ApiError } from './errors.js';
import { canonicalJson } from './contracts.js';
import { createReliefWorld, advanceReliefWorld, reliefEvents, RELIEF_PHASES } from './relief-world.js';
import { optimizeReliefWorld, validateReliefPlan } from './relief-planner.js';
import { trainDemandModel, forecastDemand } from './relief-models.js';

export const reliefStartSchema = z.strictObject({ scenario: z.literal('civilian-relief'), commandId: z.uuid(), replaceRunId: z.uuid().optional() });
export const reliefStepSchema = z.strictObject({ commandId: z.uuid(), runId: z.uuid(), expectedRevision: z.number().int().min(0).max(5), phase: z.enum(RELIEF_PHASES) });
function parse(schema, input) {
  const result = schema.safeParse(input);
  if (!result.success) throw new ApiError(422, 'INVALID_SIMULATION_COMMAND', 'Simulation command does not match its contract.');
  return result.data;
}

/** Fixed civilian fixtures only; all state/event changes are one synchronous DB transaction. */
export class ReliefSimulationService {
  constructor({ store, sources, now = Date.now, annotator, logger = () => {} }) {
    this.store = store; this.sources = sources; this.now = now; this.annotator = annotator; this.logger = logger;
    this.closed = false; this.pending = false; this.task = null;
    this.demandModel = trainDemandModel();
    store.db.exec(`CREATE TABLE IF NOT EXISTS relief_meta(id INTEGER PRIMARY KEY CHECK(id=1),version INTEGER NOT NULL);
      INSERT OR IGNORE INTO relief_meta VALUES(1,1);
      CREATE TABLE IF NOT EXISTS relief_state(id INTEGER PRIMARY KEY CHECK(id=1),snapshot_json TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS relief_commands(command_id TEXT PRIMARY KEY,content_hash TEXT NOT NULL,response_json TEXT NOT NULL);`);
    if (store.db.prepare('SELECT version FROM relief_meta WHERE id=1').get().version !== 1) throw new Error('Unsupported simulation schema.');
    if (this.snapshot().status === 'ready') this.queue();
  }
  snapshot() {
    const row = this.store.db.prepare('SELECT snapshot_json FROM relief_state WHERE id=1').get();
    return row ? JSON.parse(row.snapshot_json) : { status: 'idle' };
  }
  start(input) {
    const command = parse(reliefStartSchema, input);
    return this.execute('start', command, (current) => {
      if (current.status === 'ready' && command.replaceRunId !== current.world.runId) throw new ApiError(409, 'SIMULATION_EXISTS', 'Supply the current run ID to replace this fictional run.');
      if (current.status === 'idle' && command.replaceRunId) throw new ApiError(409, 'SIMULATION_RUN_MISMATCH', 'No current run matches the replacement.');
      return { world: createReliefWorld({ runId: randomUUID(), now: this.now() }), previous: [], history: [], phase: 'initial' };
    });
  }
  step(input) {
    const command = parse(reliefStepSchema, input);
    return this.execute('step', command, (current) => {
      if (current.status !== 'ready' || current.world.runId !== command.runId || current.world.revision !== command.expectedRevision || current.nextPhase !== command.phase) {
        throw new ApiError(409, 'SIMULATION_REVISION_CONFLICT', 'Run, revision or phase does not match the current fictional state.');
      }
      return { world: advanceReliefWorld(current.world, command.phase), previous: current.plan.assignments, history: current.history, phase: command.phase };
    });
  }
  execute(kind, command, transition) {
    if (this.closed) throw new ApiError(503, 'SIMULATION_UNAVAILABLE', 'Simulation service is stopping.');
    const hash = createHash('sha256').update(canonicalJson({ kind, command })).digest('hex');
    const result = this.store.transaction(() => {
      const existing = this.store.db.prepare('SELECT * FROM relief_commands WHERE command_id=?').get(command.commandId);
      if (existing) {
        if (existing.content_hash !== hash) throw new ApiError(409, 'SIMULATION_COMMAND_CONFLICT', 'Command ID already belongs to different content.');
        return { ...JSON.parse(existing.response_json), command: { id: command.commandId, replayed: true } };
      }
      if (this.store.db.prepare('SELECT COUNT(*) AS n FROM relief_commands').get().n >= 1000) throw new ApiError(503, 'SIMULATION_COMMAND_CAPACITY', 'Retained simulation command capacity is full.');
      const { world, previous, history, phase } = transition(this.snapshot());
      const plan = optimizeReliefWorld(world, { previousAssignments: previous });
      const validation = validateReliefPlan(world, plan, { previousAssignments: previous });
      if (!validation.valid) throw new Error('Simulation plan failed independent verification.');
      this.store.acceptBatch(reliefEvents(world, this.sources, this.now()));
      const forecastDay = 120 + world.tick;
      const snapshot = { status: 'ready', world, plan, validation,
        demand: { modelId: 'synthetic-demand-ols', simulation: true, forecastDay, predictedRequests: forecastDemand(this.demandModel, forecastDay),
          trainingCount: this.demandModel.trainingCount, testCount: this.demandModel.testCount, evaluation: this.demandModel.evaluation },
        annotations: { status: 'pending', runId: world.runId, revision: world.revision }, nextPhase: RELIEF_PHASES[world.revision] ?? null,
        history: [...history, { revision: world.revision, phase, servedPriority: plan.objective.servedPriority, assignedCount: plan.assignments.length, changedAssignments: plan.objective.changedAssignments }],
        generatedAt: new Date(this.now()).toISOString() };
      this.write(snapshot);
      const response = { ...snapshot, command: { id: command.commandId, replayed: false } };
      this.store.db.prepare('INSERT INTO relief_commands VALUES(?,?,?)').run(command.commandId, hash, JSON.stringify(response));
      return response;
    });
    if (!result.command.replayed) this.queue();
    return result;
  }
  write(snapshot) {
    this.store.db.prepare('INSERT INTO relief_state VALUES(1,?) ON CONFLICT(id) DO UPDATE SET snapshot_json=excluded.snapshot_json').run(JSON.stringify(snapshot));
  }
  queue() {
    if (this.closed) return;
    this.pending = true;
    if (this.task) return;
    this.task = this.drain().finally(() => { this.task = null; if (this.pending && !this.closed) this.queue(); });
    this.task.catch(() => this.logger('simulation.annotation_failed'));
  }
  async drain() {
    while (this.pending && !this.closed) {
      this.pending = false; const captured = this.snapshot(); if (captured.status !== 'ready') return;
      let annotations;
      try {
        const result = await this.annotator.annotate({ runId: captured.world.runId, revision: captured.world.revision, agentReports: captured.plan.agentReports });
        if (result.runId !== captured.world.runId || result.revision !== captured.world.revision) throw new Error('Annotation revision mismatch.');
        annotations = { ...result, status: 'ready' };
      } catch { annotations = { status: 'degraded', mode: 'deterministic', runId: captured.world.runId, revision: captured.world.revision, modelsUsed: [], highlights: [] }; }
      if (this.closed) return;
      const latest = this.snapshot();
      if (latest.world.runId !== captured.world.runId || latest.world.revision !== captured.world.revision) continue;
      // Provider results are revision-bound; only known IDs are selected by the annotator.
      latest.annotations = annotations;
      this.store.transaction(() => this.write(latest));
    }
  }
  async close() {
    if (this.closing) return this.closing;
    this.closed = true; this.pending = false;
    this.closing = (async () => { await this.annotator.close(); await this.task; })(); return this.closing;
  }
}
