"use client";

import React, { useState } from "react";
import {
  MagiAgent,
  MAGI_INITIAL_AGENTS,
} from "@/lib/aerospace-fixtures";
import {
  ShieldAlert,
  ShieldCheck,
  Cpu,
  Zap,
  RotateCcw,
  Plane,
  Users,
  Crosshair,
  Compass,
  Radar,
  CloudLightning,
  AlertTriangle,
  ChevronRight,
  Info,
} from "lucide-react";

interface MagiVisualizerProps {
  agents?: MagiAgent[];
  consensusStatus?: "CONSENSUS" | "DELIBERATING" | "BREACH";
  consensusTimeMs?: number;
  onInjectDisruption?: (scenario: string) => void;
  onResetEquilibrium?: () => void;
}

const AGENT_ICONS: Record<string, React.ReactNode> = {
  "AGENT-FLEET": <Plane size={18} className="text-orange-500" />,
  "AGENT-CREW": <Users size={18} className="text-amber-500" />,
  "AGENT-ORDNANCE": <Crosshair size={18} className="text-red-500" />,
  "AGENT-CORRIDOR": <Compass size={18} className="text-emerald-500" />,
  "AGENT-THREAT": <Radar size={18} className="text-purple-500" />,
  "AGENT-WEATHER": <CloudLightning size={18} className="text-cyan-500" />,
};

export function MagiVisualizer({
  agents = MAGI_INITIAL_AGENTS,
  consensusStatus = "CONSENSUS",
  consensusTimeMs = 1420,
  onInjectDisruption,
  onResetEquilibrium,
}: MagiVisualizerProps) {
  const [selectedAgent, setSelectedAgent] = useState<MagiAgent | null>(null);

  const agreementCount = agents.filter(
    (a) => a.vote === "APPROVED" || a.status === "AGREE"
  ).length;

  const leftWingAgents = agents.slice(0, 3);
  const rightWingAgents = agents.slice(3, 6);

  const renderAgentPod = (agent: MagiAgent) => {
    const isSelected = selectedAgent?.id === agent.id;
    const isObjecting = agent.status === "OBJECT" || agent.vote === "OBJECTION";
    const isDeliberating = agent.status === "DELIBERATING";

    return (
      <div
        key={agent.id}
        className={`magi-agent-pod ${
          isSelected ? "selected-pod" : ""
        } ${
          isObjecting
            ? "pod-objecting"
            : isDeliberating
            ? "pod-deliberating"
            : "pod-normal"
        }`}
        onClick={() => setSelectedAgent(agent)}
        role="button"
        tabIndex={0}
        aria-label={`View details for ${agent.name}`}
      >
        <div className="agent-pod-top">
          <div className="flex items-center gap-2">
            <div className="agent-avatar-icon">
              {AGENT_ICONS[agent.id] ?? <Cpu size={16} />}
            </div>
            <div>
              <span className="agent-designation-label">{agent.name}</span>
              <h4 className="agent-title">{agent.magiDesignation}</h4>
            </div>
          </div>

          <div
            className={`agent-vote-tag ${
              isObjecting
                ? "vote-object"
                : isDeliberating
                ? "vote-deliberating"
                : "vote-agree"
            }`}
          >
            {agent.vote}
          </div>
        </div>

        <p className="agent-rationale-snippet">
          &ldquo;{agent.rationale}&rdquo;
        </p>

        <div className="agent-pod-footer">
          <div className="agent-meta">
            <span className="meta-model">{agent.model.split(" ")[0]}</span>
            <span className="meta-conf">{agent.confidence}% conf</span>
          </div>
          <span className="click-inspect">
            Inspect <ChevronRight size={13} />
          </span>
        </div>
      </div>
    );
  };

  return (
    <div className="magi-container">
      {/* Visualizer Header */}
      <div className="magi-header">
        <div className="flex items-center gap-3">
          <div className="magi-icon-badge">
            <Cpu size={22} className="text-orange-600 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold text-slate-900 tracking-tight">
                MAGI MULTI-AGENT CONSENSUS COUNCIL
              </h2>
              <span className="magi-badge">SYSTEM V3.4</span>
            </div>
            <p className="text-xs text-slate-500">
              Autonomous Specialist Agent Consensus &amp; Google OR-Tools CP-SAT Solver Core
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div
            className={`consensus-status-pill ${
              consensusStatus === "BREACH"
                ? "status-breach"
                : consensusStatus === "DELIBERATING"
                ? "status-deliberating"
                : "status-consensus"
            }`}
          >
            {consensusStatus === "BREACH" ? (
              <>
                <ShieldAlert size={15} />
                <span>EQUILIBRIUM BREACH</span>
              </>
            ) : consensusStatus === "DELIBERATING" ? (
              <>
                <RotateCcw size={15} className="animate-spin" />
                <span>DELIBERATING ({consensusTimeMs}ms)</span>
              </>
            ) : (
              <>
                <ShieldCheck size={15} />
                <span>UNANIMOUS EQUILIBRIUM ({agreementCount}/{agents.length})</span>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Main Command Deck: Symmetrical Left Wing - Center Solver Core - Right Wing */}
      <div className="magi-command-deck">
        {/* Left Wing: Fleet, Crew, Ordnance */}
        <div className="magi-wing-column">
          <div className="wing-header">
            <span className="wing-tag">FLEET &amp; LOGISTICS WING</span>
          </div>
          {leftWingAgents.map(renderAgentPod)}
        </div>

        {/* Center Console: CP-SAT Optimization Hub & Dual Rotating Gyros */}
        <div className="magi-center-hub">
          <div className="magi-core-unit-relative">
            <div className="core-gyro-outer" />
            <div className="core-gyro-middle" />

            <div className="core-hexagon">
              <div className="core-inner-glow">
                <div className="core-pulse-beacon" />
                <Zap size={26} className="text-orange-500 animate-bounce relative z-10" />
                <span className="core-title relative z-10">CP-SAT SOLVER</span>
                <span className="core-subtitle relative z-10">OPTIMIZATION CORE</span>
                <div className="core-metric relative z-10">
                  <span className="text-[9px] text-slate-500 font-mono">LATENCY</span>
                  <span className="text-xs font-extrabold text-orange-600 font-mono">
                    {consensusTimeMs} ms
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div className="hub-details-panel glass-panel">
            <div className="flex items-center justify-between text-xs py-1 border-b border-orange-100">
              <span className="text-slate-500 font-medium">Solver Status</span>
              <span className="font-bold text-emerald-600">OPTIMAL CONVERGENCE</span>
            </div>
            <div className="flex items-center justify-between text-xs py-1 border-b border-orange-100">
              <span className="text-slate-500 font-medium">Constraints Enforced</span>
              <span className="font-mono font-semibold text-slate-800">3,290 rules</span>
            </div>
            <div className="flex items-center justify-between text-xs py-1 border-b border-orange-100">
              <span className="text-slate-500 font-medium">Decision Variables</span>
              <span className="font-mono font-semibold text-slate-800">1,840 binary</span>
            </div>
            <div className="flex items-center justify-between text-xs py-1">
              <span className="text-slate-500 font-medium">Agent Quorum</span>
              <span className="font-bold text-orange-600">
                {agreementCount} of {agents.length} Consenting
              </span>
            </div>
          </div>
        </div>

        {/* Right Wing: Airspace, Threat, Weather */}
        <div className="magi-wing-column">
          <div className="wing-header">
            <span className="wing-tag">AIRSPACE &amp; TACTICAL WING</span>
          </div>
          {rightWingAgents.map(renderAgentPod)}
        </div>
      </div>

      {/* Real-time Deliberation Ticker / Message Bus */}
      <div className="magi-ticker-deck">
        <div className="ticker-label">
          <div className="pulsing-radar-dot" />
          <span>REAL-TIME AGENT DELIBERATION STREAM</span>
        </div>

        <div className="ticker-stream">
          <div className="ticker-item">
            <span className="ticker-time">10:14:05 UTC</span>
            <span className="ticker-agent text-purple-600 font-semibold">[THREAT-INTEL-05]</span>
            <span className="ticker-msg">
              Calculated SAM S-400 radar cross-section. Recommending Corridor Alpha-1 stand-off margin &gt; 150 km.
            </span>
          </div>
          <div className="ticker-item">
            <span className="ticker-time">10:14:04 UTC</span>
            <span className="ticker-agent text-amber-600 font-semibold">[CREW-LOGISTICS-02]</span>
            <span className="ticker-msg">
              Flt Lt Chawla fatigue threshold verified at 6.8h. Alert-5 pilot Sqn Ldr Dev Nair staged as backup.
            </span>
          </div>
          <div className="ticker-item">
            <span className="ticker-time">10:14:03 UTC</span>
            <span className="ticker-agent text-red-600 font-semibold">[ARMAMENT-ALLOC-03]</span>
            <span className="ticker-msg">
              BrahMos-A supersonic cruise missile hardpoints locked. Fuel-to-payload weight ratio optimal (98.4%).
            </span>
          </div>
        </div>
      </div>

      {/* Disruption Simulation Bar */}
      <div className="magi-disruption-bar">
        <div className="flex items-center gap-2">
          <AlertTriangle size={16} className="text-orange-600" />
          <span className="text-xs font-bold text-slate-700">TEST SYSTEM ADAPTABILITY:</span>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <button
            className="disruption-btn storm"
            onClick={() => onInjectDisruption?.("storm_front")}
          >
            ⛈️ Storm Front in Corridor Charlie
          </button>
          <button
            className="disruption-btn threat"
            onClick={() => onInjectDisruption?.("threat_spike")}
          >
            🎯 Hostile SAM Radar Spike
          </button>
          <button
            className="disruption-btn mechanical"
            onClick={() => onInjectDisruption?.("mechanical_fault")}
          >
            ⚙️ Hydraulic Failure on Airframe
          </button>
          <button
            className="disruption-btn reset"
            onClick={() => onResetEquilibrium?.()}
          >
            🔄 Reset Equilibrium
          </button>
        </div>
      </div>

      {/* Modal for Selected Agent Detail */}
      {selectedAgent && (
        <div className="agent-modal-backdrop" onClick={() => setSelectedAgent(null)}>
          <div
            className="agent-modal-card glass-panel"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <div className="flex items-center gap-2">
                <div className="agent-avatar-icon">
                  {AGENT_ICONS[selectedAgent.id] ?? <Cpu size={20} />}
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900">
                    {selectedAgent.name} &mdash; {selectedAgent.magiDesignation}
                  </h3>
                  <p className="text-xs text-slate-500">{selectedAgent.specialty}</p>
                </div>
              </div>
              <button
                className="modal-close-btn"
                onClick={() => setSelectedAgent(null)}
              >
                &times;
              </button>
            </div>

            <div className="modal-body">
              <div className="modal-stat-grid">
                <div className="modal-stat-box">
                  <span className="stat-label">VOTE STATUS</span>
                  <span
                    className={`stat-val font-bold ${
                      selectedAgent.vote === "APPROVED"
                        ? "text-emerald-600"
                        : "text-red-600"
                    }`}
                  >
                    {selectedAgent.vote}
                  </span>
                </div>
                <div className="modal-stat-box">
                  <span className="stat-label">AI CONFIDENCE</span>
                  <span className="stat-val font-bold text-orange-600">
                    {selectedAgent.confidence}%
                  </span>
                </div>
                <div className="modal-stat-box">
                  <span className="stat-label">PREDICTIVE MODEL</span>
                  <span className="stat-val font-medium text-slate-700">
                    {selectedAgent.model}
                  </span>
                </div>
                <div className="modal-stat-box">
                  <span className="stat-label">LAST EVALUATION</span>
                  <span className="stat-val text-slate-600">
                    {selectedAgent.lastBidTime}
                  </span>
                </div>
              </div>

              <div className="modal-section">
                <h4 className="modal-subtitle">TACTICAL RATIONALE &amp; ASSESSMENT</h4>
                <div className="rationale-callout">
                  <p className="text-sm text-slate-800 leading-relaxed font-sans">
                    {selectedAgent.rationale}
                  </p>
                </div>
              </div>

              <div className="modal-section">
                <h4 className="modal-subtitle">MATHEMATICAL CONSTRAINTS ENFORCED</h4>
                <div className="constraints-tags">
                  {selectedAgent.constraintsEnforced.map((c, i) => (
                    <span key={i} className="constraint-tag">
                      ✓ {c}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            <div className="modal-footer">
              <button
                className="btn-primary-orange"
                onClick={() => setSelectedAgent(null)}
              >
                Close Inspector
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
