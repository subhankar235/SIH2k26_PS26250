import { randomUUID, createHash } from 'node:crypto';
import { z } from 'zod';
import { ApiError } from './errors.js';
import { canonicalJson, EVENT_TYPES, validateEvent } from './contracts.js';
import { createReliefWorld, advanceReliefWorld, RELIEF_PHASES } from './relief-world.js';
import { optimizeReliefWorld, validateReliefPlan } from './relief-planner.js';
import { trainDemandModel, forecastDemand } from './relief-models.js';

import { configurationSchema, configuredReliefWorld } from './relief-configuration.js';
import { buildReliefCoordination } from './relief-coordination.js';
import { boundEntity, applyBoundObservation, expireBoundObservations, mirroredReliefEvents } from './relief-inputs.js';
import { negotiationSettingsSchema, runReliefNegotiation, validateReliefNegotiationReport, finishReliefNegotiation } from './relief-negotiation.js';
import { weatherCommandSchema } from './relief-weather.js';
export const reliefStartSchema = z.strictObject({ scenario: z.literal('civilian-relief'), commandId: z.uuid(), replaceRunId: z.uuid().optional(), inputMode: z.enum(['scripted','gateway']).optional(), configuration: configurationSchema.optional(), negotiation: negotiationSettingsSchema.optional() }).refine(c => !c.configuration || c.inputMode === 'gateway', 'Configuration requires gateway mode');
export const reliefStepSchema = z.strictObject({ commandId: z.uuid(), runId: z.uuid(), expectedRevision: z.number().int().min(0).max(5), phase: z.enum(RELIEF_PHASES) });
function parse(schema, input) {
  const result = schema.safeParse(input);
  if (!result.success) throw new ApiError(422, 'INVALID_SIMULATION_COMMAND', 'Simulation command does not match its contract.');
  return result.data;
}

/** Bounded civilian fictional scenarios only; all state/event changes are one synchronous DB transaction. */
export class ReliefSimulationService {
  constructor({ store, sources, now = Date.now, annotator, weatherProvider, negotiator = runReliefNegotiation, logger = () => {} }) {
    this.store = store; this.sources = sources; this.now = now; this.annotator = annotator; this.logger = logger; this.weatherProvider = weatherProvider; this.weatherTask = null; this.negotiator = negotiator;
    this.closed = false; this.pending = false; this.task = null;
    this.demandModel = trainDemandModel();
    store.db.exec(`CREATE TABLE IF NOT EXISTS relief_meta(id INTEGER PRIMARY KEY CHECK(id=1),version INTEGER NOT NULL);
      INSERT OR IGNORE INTO relief_meta VALUES(1,1);
      CREATE TABLE IF NOT EXISTS relief_state(id INTEGER PRIMARY KEY CHECK(id=1),snapshot_json TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS relief_commands(command_id TEXT PRIMARY KEY,content_hash TEXT NOT NULL,response_json TEXT NOT NULL);`);
    if (store.db.prepare('SELECT version FROM relief_meta WHERE id=1').get().version !== 1) throw new Error('Unsupported simulation schema.');
    const recovered=this.snapshot();
    if(recovered.status==='ready') {
      if(recovered.weatherFeed?.status==='pending') {
        recovered.weatherFeed={...recovered.weatherFeed,status:'degraded',errorCode:'WEATHER_INTERRUPTED',generatedAt:new Date(this.now()).toISOString()};
        store.transaction(()=>this.write(recovered));
      }
      // Start the publisher even if an expiry transaction cannot yet fit the outbox.
      // snapshot() marks overdue evidence historical; the server timer retries after drain.
      try { this.expireInputs(); } catch { this.logger('simulation.expiry_deferred'); }
      this.queue();
    }
  }
  snapshot() {
    const row = this.store.db.prepare('SELECT snapshot_json FROM relief_state WHERE id=1').get();
    if(!row)return {status:'idle'};
    const snapshot=JSON.parse(row.snapshot_json);
    if(snapshot.inputs?.mode==='gateway') {
      const pending=snapshot.inputs.bindings.filter(b=>!b.expired&&Date.parse(b.validUntil)<=this.now()).length;
      const expired=snapshot.inputs.bindings.filter(b=>b.expired).length;
      snapshot.inputFreshness={status:pending||expired?'expired':'current',expiredCount:pending+expired,replanPending:pending>0};
      snapshot.planUsable=pending===0;
    }
    return snapshot;
  }
  start(input) {
    const command = parse(reliefStartSchema, input);
    return this.execute('start', command, (current) => {
      if (current.status === 'ready' && command.replaceRunId !== current.world.runId) throw new ApiError(409, 'SIMULATION_EXISTS', 'Supply the current run ID to replace this fictional run.');
      if (current.status === 'idle' && command.replaceRunId) throw new ApiError(409, 'SIMULATION_RUN_MISMATCH', 'No current run matches the replacement.');
      const options={runId:randomUUID(),now:this.now()};
      const world=command.configuration?configuredReliefWorld(command.configuration,options):createReliefWorld(options);
      const mode=command.inputMode??'scripted';
      const authorities=Object.fromEntries(EVENT_TYPES.map(type=>[type,this.sources.find(s=>s.types.includes(type))?.sourceId]));
      if(Object.values(authorities).some(id=>!id))throw new ApiError(503,'SIMULATION_SOURCES_MISSING','Configure an authorized source for every civilian data type.');
      return { world, previous: [], history: [], phase: 'initial', negotiationSettings: command.negotiation, inputs:{mode,namespace:`input-${world.runId}-`,authorities,bindings:[]} };
    });
  }
  step(input) {
    const command = parse(reliefStepSchema, input);
    return this.execute('step', command, (current) => {
      if (current.inputs?.mode === 'gateway' || current.status !== 'ready' || current.world.runId !== command.runId || current.world.revision !== command.expectedRevision || current.nextPhase !== command.phase) {
        throw new ApiError(409, 'SIMULATION_REVISION_CONFLICT', 'Run, revision or phase does not match the current fictional state.');
      }
      return { world: advanceReliefWorld(current.world, command.phase), previous: current.plan.assignments, history: current.history, phase: command.phase, negotiationSettings: current.negotiation?.settings, inputs: current.inputs };
    });
  }
  execute(kind, command, transition) {
    if (this.closed) throw new ApiError(503, 'SIMULATION_UNAVAILABLE', 'Simulation service is stopping.');
    if(this.weatherTask&&command.commandId===this.weatherCommandId)throw new ApiError(409,'SIMULATION_COMMAND_CONFLICT','Command ID belongs to a pending weather refresh.');
    const hash = createHash('sha256').update(canonicalJson({ kind, command })).digest('hex');
    const result = this.store.transaction(() => {
      const existing = this.store.db.prepare('SELECT * FROM relief_commands WHERE command_id=?').get(command.commandId);
      if (existing) {
        if (existing.content_hash !== hash) throw new ApiError(409, 'SIMULATION_COMMAND_CONFLICT', 'Command ID already belongs to different content.');
        return { ...JSON.parse(existing.response_json), command: { id: command.commandId, replayed: true } };
      }
      if (this.store.db.prepare('SELECT COUNT(*) AS n FROM relief_commands').get().n >= 1000) throw new ApiError(503, 'SIMULATION_COMMAND_CAPACITY', 'Retained simulation command capacity is full.');
      const snapshot = this.persistTransition(transition(this.snapshot()));
      const response = { ...snapshot, command: { id: command.commandId, replayed: false } };
      this.store.db.prepare('INSERT INTO relief_commands VALUES(?,?,?)').run(command.commandId, hash, JSON.stringify(response));
      return response;
    });
    if (!result.command.replayed) this.queue();
    return result;
  }
  commandReplay(command,hash) {
    const row=this.store.db.prepare('SELECT * FROM relief_commands WHERE command_id=?').get(command.commandId);
    if(!row)return null;
    if(row.content_hash!==hash)throw new ApiError(409,'SIMULATION_COMMAND_CONFLICT','Command ID already belongs to different content.');
    const saved=JSON.parse(row.response_json);
    if(saved.errorReceipt)throw new ApiError(saved.errorReceipt.status,saved.errorReceipt.code,saved.errorReceipt.message,{command:{id:command.commandId,replayed:true}});
    return {...saved,command:{id:command.commandId,replayed:true}};
  }
  weatherCurrent(command) {
    const current=this.snapshot();
    if(current.status!=='ready'||current.inputs?.mode!=='gateway'||current.world.runId!==command.runId||current.world.revision!==command.expectedRevision)
      throw new ApiError(409,'SIMULATION_REVISION_CONFLICT','Run or revision does not match the current gateway scenario.');
    if(!this.sources.some(s=>s.sourceId===current.inputs.authorities['weather.observation']&&s.types.includes('weather.observation')))throw new ApiError(503,'SIMULATION_SOURCE_AUTHORITY_CHANGED','Start a new run after changing its weather source authority.');
    if(!current.world.weather.some(w=>w.airportId===command.airportId))throw new ApiError(422,'SIMULATION_INPUT_INCOMPATIBLE','Weather target must be an existing fictional airport.');
    return current;
  }
  async weather(input) {
    const command=parse(weatherCommandSchema,input);
    if(this.closed||!this.weatherProvider)throw new ApiError(503,'WEATHER_UNAVAILABLE','Weather integration is unavailable.');
    const hash=createHash('sha256').update(canonicalJson({kind:'weather',command})).digest('hex');
    const replay=this.commandReplay(command,hash);if(replay)return replay;
    if(this.weatherTask) {
      if(this.weatherHash===hash)return this.weatherTask;
      throw new ApiError(409,'WEATHER_BUSY','A weather refresh is already running.');
    }
    this.weatherCurrent(command);
    this.weatherHash=hash;this.weatherCommandId=command.commandId;
    this.weatherTask=this.refreshWeather(command,hash).finally(()=>{this.weatherTask=null;this.weatherHash=null;this.weatherCommandId=null;});
    return this.weatherTask;
  }
  async refreshWeather(command,hash) {
    const feed=(status,extra={})=>({status,runId:command.runId,revision:command.expectedRevision,commandId:command.commandId,airportId:command.airportId,location:command.location,generatedAt:new Date(this.now()).toISOString(),...extra});
    this.store.transaction(()=>{
      this.checkCommandCapacity();
      const current=this.weatherCurrent(command);current.weatherFeed=feed('pending');this.write(current);
    });
    let observation,errorCode;
    try {observation=await this.weatherProvider.fetch(command.location);}
    catch(error){errorCode=/^WEATHER_[A-Z_]+$/.test(error.code??'')?error.code:'WEATHER_UNAVAILABLE';}
    if(this.closed)throw new ApiError(503,'SIMULATION_UNAVAILABLE','Simulation service is stopping.');
    try {
      const result=this.store.transaction(()=>{
        this.checkCommandCapacity();
        let current=this.weatherCurrent(command);
        if(!errorCode) {
          const entityId=`${current.inputs.namespace}${command.airportId}`;
          const sourceId=current.inputs.authorities['weather.observation'];
          const sequence=this.store.db.prepare("SELECT e.sequence FROM projections p JOIN events e ON e.id=p.event_cursor WHERE p.source_id=? AND p.event_type='weather.observation' AND p.entity_id=?").get(sourceId,entityId)?.sequence??0;
          const event=validateEvent({schemaVersion:1,eventId:randomUUID(),sourceId,type:'weather.observation',entityId,sequence:sequence+1,observedAt:observation.observedAt,validUntil:observation.validUntil,data:observation.data},{now:this.now()});
          if(Date.parse(event.validUntil)<=this.now())throw new ApiError(422,'WEATHER_INVALID_RESPONSE','Weather observation is already expired.');
          const receipts=this.acceptEvents([event],{queue:false});
          if(receipts[0].disposition!=='current')throw new ApiError(409,'WEATHER_OBSERVATION_STALE','Provider observation is older than the current input.');
          current=this.snapshot();current.weatherFeed=feed('ready',{revision:current.world.revision,provenance:observation.provenance,eventId:event.eventId});
        } else current.weatherFeed=feed('degraded',{errorCode});
        this.write(current);
        const response={...current,command:{id:command.commandId,replayed:false}};
        this.store.db.prepare('INSERT INTO relief_commands VALUES(?,?,?)').run(command.commandId,hash,JSON.stringify(response));return response;
      });
      if(!errorCode)this.queue();return result;
    } catch(error) {
      // A superseded fetch cannot apply its observation to another revision or run.
      this.store.transaction(()=>{
        const current=this.snapshot();
        const failure=error instanceof ApiError?error:new ApiError(500,'INTERNAL_ERROR','Weather refresh could not be committed.');
        if(current.status==='ready'&&current.world.runId===command.runId&&current.weatherFeed?.commandId===command.commandId){
          current.weatherFeed=feed('degraded',{errorCode:failure.code});this.write(current);
        }
        this.checkCommandCapacity();
        this.store.db.prepare('INSERT INTO relief_commands VALUES(?,?,?)').run(command.commandId,hash,JSON.stringify({errorReceipt:{status:failure.status,code:failure.code,message:failure.message}}));
      });
      if(error instanceof ApiError)error.details={command:{id:command.commandId,replayed:false}};
      throw error;
    }
  }
  checkCommandCapacity() {
    if(this.store.db.prepare('SELECT COUNT(*) AS n FROM relief_commands').get().n>=1000)throw new ApiError(503,'SIMULATION_COMMAND_CAPACITY','Retained simulation command capacity is full.');
  }
  persistTransition({world,previous,history,phase,inputs,weatherFeed,negotiationSettings}) {
    const settings=negotiationSettingsSchema.parse(negotiationSettings ?? {});
    let negotiation;
    try {
      negotiation=this.negotiator(structuredClone(world),{previousAssignments:structuredClone(previous),settings:{...settings}});
      if(negotiation?.then) { Promise.resolve(negotiation).catch(()=>{}); throw new TypeError('Negotiation must be synchronous.'); }
      if(!validateReliefNegotiationReport(world,negotiation,{previousAssignments:previous}).valid || JSON.stringify(negotiation.settings)!==JSON.stringify(settings)) throw new Error('Invalid negotiation report.');
    } catch {
      this.logger('simulation.negotiation_failed');
      negotiation={version:1,runId:world.runId,revision:world.revision,mode:'deterministic-autonomous',topology:'fully-connected-peers',settings,previousAssignments:structuredClone(previous),status:'failed',roundsCompleted:0,requests:[],agentStates:[],messages:[],assignments:[],errorCode:'NEGOTIATION_FAILED'};
    }
    const plan=optimizeReliefWorld(world,{previousAssignments:previous,initialAssignments:negotiation.assignments});
    const validation=validateReliefPlan(world,plan,{previousAssignments:previous});
    if(!validation.valid)throw new Error('Simulation plan failed independent verification.');
    const events=mirroredReliefEvents(world,this.sources,inputs,this.now());
    const receipts=events.length?this.store.acceptBatch(events):[];
    if(receipts.some(r=>r.disposition!=='current'||r.delivery!=='queued'||r.duplicate))throw new ApiError(409,'SIMULATION_FIXTURE_CONFLICT','A fictional source stream conflicts; no changes were committed.');
    const forecastDay=120+world.tick;
    const snapshot={status:'ready',world,plan,validation,inputs,
      coordination:buildReliefCoordination(world,plan,validation),
      negotiation:finishReliefNegotiation(negotiation,world,plan,validation,{previousAssignments:previous}),
      evidence:events.map((event,i)=>({eventId:event.eventId,cursor:receipts[i].cursor,type:event.type,entityId:event.entityId,sourceId:event.sourceId})),
      demand:{modelId:'synthetic-demand-ols',simulation:true,forecastDay,predictedRequests:forecastDemand(this.demandModel,forecastDay),trainingCount:this.demandModel.trainingCount,testCount:this.demandModel.testCount,evaluation:this.demandModel.evaluation},
      annotations:{status:'pending',runId:world.runId,revision:world.revision},
      nextPhase:inputs?.mode==='gateway'?null:RELIEF_PHASES[world.revision]??null,
      history:[...history,{revision:world.revision,phase,servedPriority:plan.objective.servedPriority,assignedCount:plan.assignments.length,changedAssignments:plan.objective.changedAssignments}],
      generatedAt:new Date(this.now()).toISOString(),...(weatherFeed?{weatherFeed}:{})};
    this.write(snapshot);return snapshot;
  }
  /** Inputs and their verified revision share a transaction with gateway history/outbox. */
  acceptEvents(events,{queue=true}={}) {
    if(this.closed)throw new ApiError(503,'SIMULATION_UNAVAILABLE','Simulation service is stopping.');
    let changed=false;
    const receipts=this.store.transaction(()=>{
      const result=this.store.acceptBatch(events);
      const current=this.snapshot();
      const applied=events.filter((e,i)=>!result[i].duplicate&&result[i].disposition==='current'&&boundEntity(current,e));
      if(!applied.length)return result;
      if(current.world.revision>=19)throw new ApiError(503,'SIMULATION_REVISION_CAPACITY','Start a new fictional run to accept further bound inputs.');
      const previous=current.plan.assignments;
      for(const event of applied)applyBoundObservation(current,event,this.now());
      current.world.revision++;
      this.persistTransition({world:current.world,previous,history:current.history,phase:'gateway-update',negotiationSettings:current.negotiation?.settings,inputs:current.inputs,weatherFeed:current.weatherFeed});changed=true;
      return result;
    });
    if(changed&&queue)this.queue();return receipts;
  }
  expireInputs() {
    if(this.closed)return;
    let changed=false;
    this.store.transaction(()=>{
      const current=this.snapshot();
      if(current.status!=='ready'||current.inputs?.mode!=='gateway'||current.world.revision>=20)return;
      if(!expireBoundObservations(current,this.now()))return;
      current.world.revision++;
      this.persistTransition({world:current.world,previous:current.plan.assignments,history:current.history,phase:'input-expiry',negotiationSettings:current.negotiation?.settings,inputs:current.inputs,weatherFeed:current.weatherFeed});changed=true;
    });
    if(changed)this.queue();
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
    this.closing = (async () => { await Promise.all([this.annotator.close(),this.weatherProvider?.close()]); await Promise.allSettled([this.task,this.weatherTask]); })(); return this.closing;
  }
}
