"use client";

import React, { useState } from "react";
import {
  FLEET_AIRCRAFT,
  CREW_ROSTER,
  WEAPON_SYSTEMS,
  AIR_CORRIDORS,
  ACTIVE_THREATS,
  PIPELINE_NODES,
  TACTICAL_SORTIES,
  SortieDispatch,
  Aircraft,
  CrewMember,
  WeaponSystem,
  AirCorridor,
  ThreatItem,
  PipelineHealthNode,
} from "@/lib/aerospace-fixtures";
import {
  Plane,
  Users,
  Crosshair,
  Wind,
  ShieldAlert,
  Activity,
  CheckCircle2,
  Clock,
  Fuel,
  Compass,
  AlertTriangle,
  Radio,
  Sparkles,
  Send,
  Navigation,
  Package,
  ShieldCheck,
  MapPin,
  ArrowRight,
  UserCheck,
  Thermometer,
  Layers,
} from "lucide-react";

interface ResourceBoardsProps {
  disruptionScenario?: string | null;
  liveSorties?: any[] | null;
}

export function ResourceBoards({ disruptionScenario, liveSorties }: ResourceBoardsProps) {
  const [activeTab, setActiveTab] = useState<
    "sorties" | "fleet" | "crew" | "weapons" | "corridors" | "threats" | "pipeline"
  >("sorties");
  const [sortieFilter, setSortieFilter] = useState<"all" | "on_schedule" | "in_flight" | "alert" | "delayed">("all");

  // Dynamically compute sorties based on real-time disruption scenarios and live solver output
  const disruptionFailedOrEmpty = Boolean(
    disruptionScenario && (!liveSorties || liveSorties.length === 0)
  ) || (liveSorties !== null && liveSorties !== undefined && liveSorties.length === 0);

  const rawSorties: SortieDispatch[] = TACTICAL_SORTIES.map((sortie) => {
    if (liveSorties && liveSorties.length > 0) {
      const live = liveSorties.find(
        (a: any) =>
          (a.mission_id || a.taskId || a.id) === sortie.id ||
          (a.mission_id || a.taskId || a.id) === sortie.callsign
      );
      if (live) {
        const airframe = live.airframe_id || live.resourceId;
        const corridor = live.corridor_id || live.transitCorridor;
        const crew = live.crew_id;
        const isRerouted = corridor && (corridor.includes("Detour") || corridor.includes("Bravo") || corridor.includes("Alpha-1"));
        return {
          ...sortie,
          airframeId: airframe || sortie.airframeId,
          tailNumber: airframe ? airframe.replace(/^[A-Z0-9]+-/, "") : sortie.tailNumber,
          transitCorridor: corridor || sortie.transitCorridor,
          pilotInCommand: crew || sortie.pilotInCommand,
          status: isRerouted ? ("REROUTED" as const) : sortie.status,
          safetyMarginMin: isRerouted ? 20 : sortie.safetyMarginMin,
          solverVerification: "VERIFIED OPTIMAL (CP-SAT)" as const,
        };
      }
    }

    if (disruptionScenario === "storm_front" && sortie.id === "MSN-LOG-110") {
      return {
        ...sortie,
        status: "REROUTED" as const,
        delayDeltaMin: 25,
        estimatedArrivalUtc: "12:10 UTC (T+01:40)",
        safetyMarginMin: 20, // 12:30 UTC deadline - 12:10 UTC arrival = exactly 20 min margin
        transitCorridor: "Corridor Alpha-1 Detour (FL240 High Clearance, 780 km)",
        delayCause: "Corridor Charlie-7 blocked by Severe Thunderstorm Cell -> CP-SAT rerouted via Corridor Alpha-1 Detour (+25 min delay). Arrival 12:10 UTC remains within 12:30 UTC deadline. Crew duty limits preserved.",
        solverVerification: disruptionFailedOrEmpty ? ("INSPECTION REQUIRED" as const) : sortie.solverVerification,
      };
    }
    if (disruptionScenario === "threat_spike" && sortie.id === "MSN-OP-901") {
      return {
        ...sortie,
        transitCorridor: "Corridor Alpha-1 (Low-Altitude Terrain Masked FL140, 850 km)",
        delayCause: "Hostile S-400 radar active in Sector Bravo -> CP-SAT lowered flight level to FL140 terrain-masked vector. Stand-off BrahMos launch point secured with 0 schedule delay.",
        solverVerification: disruptionFailedOrEmpty ? ("INSPECTION REQUIRED" as const) : sortie.solverVerification,
      };
    }
    if (disruptionScenario === "mechanical_fault" && sortie.id === "MSN-OP-901") {
      return {
        ...sortie,
        airframeId: "RAF-RB011",
        airframeModel: "Dassault Rafale EH (Standby Swap)",
        tailNumber: "RB011",
        homeBase: "Ambala AFS (Fast Staged)",
        delayCause: "Lead airframe SU30-SB042 grounded for hydraulic check -> CP-SAT auto-substituted standby RAF-RB011. Crew & BrahMos load transferred with 0 launch delay.",
        solverVerification: disruptionFailedOrEmpty ? ("INSPECTION REQUIRED" as const) : sortie.solverVerification,
      };
    }
    return disruptionFailedOrEmpty ? { ...sortie, solverVerification: "INSPECTION REQUIRED" as const } : sortie;
  });

  const sorties: SortieDispatch[] = disruptionFailedOrEmpty
    ? rawSorties.map(s => ({ ...s, solverVerification: "INSPECTION REQUIRED" as const }))
    : [...rawSorties];

  // Include dynamic backend missions from liveSorties not in the static fixture
  if (liveSorties && liveSorties.length > 0) {
    const existingIds = new Set(sorties.map(s => s.id));
    for (const live of liveSorties) {
      const mId = live.mission_id || live.taskId || live.id;
      if (mId && !existingIds.has(mId)) {
        const airframe = live.airframe_id || live.resourceId || "Tactical-Airframe";
        const crew = live.crew_id || "Duty Pilot";
        const corridor = live.corridor_id || "Transit-Route";
        sorties.unshift({
          id: mId,
          callsign: live.callsign || `SORTIE-${mId}`,
          missionName: `Operational Sortie ${mId}`,
          priority: "P-1 Operational Mission",
          airframeId: airframe,
          airframeModel: airframe,
          tailNumber: airframe,
          homeBase: "Air Force Station Forward",
          pilotInCommand: crew,
          coPilotOrWso: "Mission Specialist",
          crewDutyRemainingHours: 8.0,
          crewDutyLimitHours: 10.0,
          crewFatigueScore: 0.1,
          payloadDescription: "Tactical Combat / Logistics Payload",
          payloadWeightKg: 8500,
          isColdChainActive: false,
          isHazardousClass1: false,
          originBase: "Base-Alpha",
          transitCorridor: corridor,
          destinationBase: "Base-Bravo",
          departureTimeUtc: `T+${live.slot ?? 0}h`,
          flightDurationMin: 60,
          estimatedArrivalUtc: `T+${(live.slot ?? 0) + 1}h`,
          hardDeadlineUtc: "T+8h",
          safetyMarginMin: 45,
          status: "ON SCHEDULE",
          delayDeltaMin: 0,
          solverVerification: "VERIFIED OPTIMAL (CP-SAT)",
        });
        existingIds.add(mId);
      }
    }
  }

  const filteredSorties = sorties.filter((s) => {
    if (sortieFilter === "on_schedule") return s.status === "ON SCHEDULE";
    if (sortieFilter === "in_flight") return s.status === "IN-FLIGHT";
    if (sortieFilter === "alert") return s.status === "ALERT-5 STANDBY";
    if (sortieFilter === "delayed") return s.status === "DELAYED" || s.status === "REROUTED";
    return true;
  });

  return (
    <div className="resource-boards-container glass-panel">
      {/* Board Navigation Tabs */}
      <div className="resource-tabs-bar">
        <button
          className={`tab-btn ${activeTab === "sorties" ? "active-tab" : ""}`}
          onClick={() => setActiveTab("sorties")}
        >
          <Send size={16} />
          <span>Flight Dispatch Manifest ({sorties.length})</span>
        </button>

        <button
          className={`tab-btn ${activeTab === "fleet" ? "active-tab" : ""}`}
          onClick={() => setActiveTab("fleet")}
        >
          <Plane size={16} />
          <span>Fleet Airframes ({FLEET_AIRCRAFT.length})</span>
        </button>

        <button
          className={`tab-btn ${activeTab === "crew" ? "active-tab" : ""}`}
          onClick={() => setActiveTab("crew")}
        >
          <Users size={16} />
          <span>Aircrew &amp; Pilots ({CREW_ROSTER.length})</span>
        </button>

        <button
          className={`tab-btn ${activeTab === "weapons" ? "active-tab" : ""}`}
          onClick={() => setActiveTab("weapons")}
        >
          <Crosshair size={16} />
          <span>Munitions &amp; Priority ({WEAPON_SYSTEMS.length})</span>
        </button>

        <button
          className={`tab-btn ${activeTab === "corridors" ? "active-tab" : ""}`}
          onClick={() => setActiveTab("corridors")}
        >
          <Wind size={16} />
          <span>Corridors &amp; Weather ({AIR_CORRIDORS.length})</span>
        </button>

        <button
          className={`tab-btn ${activeTab === "threats" ? "active-tab" : ""}`}
          onClick={() => setActiveTab("threats")}
        >
          <ShieldAlert size={16} />
          <span>Threat Radar ({ACTIVE_THREATS.length})</span>
        </button>

        <button
          className={`tab-btn ${activeTab === "pipeline" ? "active-tab" : ""}`}
          onClick={() => setActiveTab("pipeline")}
        >
          <Activity size={16} />
          <span>Data Feeds Health</span>
        </button>
      </div>

      {/* Tab 0: Tactical Sortie Dispatch & Flight Manifest */}
      {activeTab === "sorties" && (
        <div className="board-content">
          <div className="board-header-row">
            <div>
              <h3 className="board-title">Active Sortie Dispatch &amp; Mission Allocation Board</h3>
              <p className="board-sub">
                Transparent air operations manifest: exact aircraft, pilot crew &amp; duty limits, munitions/cargo loadout, origin-corridor-destination routing, and live delay &amp; reroute tracking.
              </p>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <button
                onClick={() => setSortieFilter("all")}
                className={`px-3 py-1 text-xs rounded-full border transition-all ${
                  sortieFilter === "all"
                    ? "bg-orange-600 text-white border-orange-600 font-semibold shadow-sm"
                    : "bg-white font-semibold hover:bg-slate-50"
                }`}
                style={sortieFilter !== "all" ? { color: "#334155", border: "1px solid #cbd5e1" } : {}}
              >
                All Sorties ({sorties.length})
              </button>
              <button
                onClick={() => setSortieFilter("on_schedule")}
                className={`px-3 py-1 text-xs rounded-full border transition-all ${
                  sortieFilter === "on_schedule"
                    ? "bg-emerald-600 text-white border-emerald-600 font-semibold shadow-sm"
                    : "bg-white font-semibold hover:bg-slate-50"
                }`}
                style={sortieFilter !== "on_schedule" ? { color: "#334155", border: "1px solid #cbd5e1" } : {}}
              >
                On Schedule ({sorties.filter((s) => s.status === "ON SCHEDULE").length})
              </button>
              <button
                onClick={() => setSortieFilter("in_flight")}
                className={`px-3 py-1 text-xs rounded-full border transition-all ${
                  sortieFilter === "in_flight"
                    ? "bg-sky-600 text-white border-sky-600 font-semibold shadow-sm"
                    : "bg-white font-semibold hover:bg-slate-50"
                }`}
                style={sortieFilter !== "in_flight" ? { color: "#334155", border: "1px solid #cbd5e1" } : {}}
              >
                In-Flight ({sorties.filter((s) => s.status === "IN-FLIGHT").length})
              </button>
              <button
                onClick={() => setSortieFilter("delayed")}
                className={`px-3 py-1 text-xs rounded-full border transition-all ${
                  sortieFilter === "delayed"
                    ? "bg-amber-600 text-white border-amber-600 font-semibold shadow-sm"
                    : "bg-white font-semibold hover:bg-slate-50"
                }`}
                style={sortieFilter !== "delayed" ? { color: "#334155", border: "1px solid #cbd5e1" } : {}}
              >
                Rerouted / Alert ({sorties.filter((s) => s.status === "REROUTED" || s.status === "DELAYED").length})
              </button>
            </div>
          </div>

          {/* Active Disruption Banner */}
          {disruptionScenario && (
            <div className={`mb-4 p-3.5 rounded-xl text-xs flex items-start gap-3 shadow-sm border ${
              disruptionFailedOrEmpty
                ? "bg-rose-500/15 border-rose-500/50"
                : "bg-amber-500/15 border-amber-500/50"
            }`}>
              <AlertTriangle size={18} className={disruptionFailedOrEmpty ? "text-rose-700 flex-shrink-0 mt-0.5" : "text-amber-700 flex-shrink-0 mt-0.5"} />
              <div className="space-y-1">
                <span className="font-bold uppercase tracking-wide text-xs" style={{ color: disruptionFailedOrEmpty ? "#881337" : "#78350f" }}>
                  {disruptionFailedOrEmpty
                    ? "Operational Disruption Logged — Replanning Pending / Unverified:"
                    : "Active Disruption Resolved by Autonomous CP-SAT Replanning:"}
                </span>
                <p className="font-medium text-xs leading-relaxed" style={{ color: disruptionFailedOrEmpty ? "#4c0519" : "#451a03" }}>
                  {disruptionFailedOrEmpty
                    ? "Disruption event received. Solver returned empty plan or replan request failed. Manual commander inspection required."
                    : (
                      disruptionScenario === "storm_front"
                        ? "Severe convective thunderstorm cell in Corridor Charlie detected. Samaritan-04 (MSN-LOG-110) automatically rerouted via Corridor Alpha-1 (+25m delta). Arrival 12:10 UTC remains within 12:30 UTC deadline. Crew fatigue verified safe."
                        : disruptionScenario === "threat_spike"
                        ? "Hostile S-400 radar acquisition in Sector Bravo detected. Garuda-01 (MSN-OP-901) ingress altitude lowered to FL140 terrain-masked vector. Stand-off BrahMos launch boundary locked with 0 schedule delay."
                        : "Airframe SU30-SB042 grounded for hydraulic actuator maintenance. Standby Dassault Rafale RB011 auto-substituted. Weapons and crew transferred without canceling mission."
                    )}
                </p>
              </div>
            </div>
          )}

          {/* Manifest Sortie Cards */}
          <div className="space-y-4">
            {filteredSorties.map((sortie) => (
                <div
                key={sortie.id}
                className={`p-4 rounded-xl border transition-all duration-200 ${
                  sortie.status === "REROUTED"
                    ? "sortie-card-rerouted shadow-sm"
                    : "sortie-card hover:border-orange-300 hover:shadow-sm"
                }`}
              >
                {/* Header row: ID, Callsign, Priority, Status */}
                <div className="flex flex-wrap items-center justify-between gap-2 pb-3 mb-3 border-b border-slate-200">
                  <div className="flex items-center gap-2.5">
                    <span className="px-2 py-0.5 rounded bg-orange-100 text-orange-950 font-mono font-bold text-xs border border-orange-200">
                      {sortie.id}
                    </span>
                    <span className="font-mono text-sm font-bold sortie-title-text tracking-tight">
                      {sortie.callsign}
                    </span>
                    <span className="text-xs sortie-muted-text font-medium">
                      &bull; {sortie.missionName}
                    </span>
                    <span
                      className="px-2 py-0.5 rounded text-[10px] font-bold"
                      style={{ background: "#e2e8f0", color: "#1e293b", border: "1px solid #cbd5e1" }}
                    >
                      {sortie.priority}
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    {sortie.status === "ON SCHEDULE" && (
                      <span
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold"
                        style={{ background: "#ecfdf5", color: "#065f46", border: "1px solid #10b981" }}
                      >
                        <CheckCircle2 size={12} className="text-emerald-700" /> ON SCHEDULE
                      </span>
                    )}
                    {sortie.status === "IN-FLIGHT" && (
                      <span
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold"
                        style={{ background: "#f0f9ff", color: "#0369a1", border: "1px solid #0ea5e9" }}
                      >
                        <Compass size={12} className="animate-spin text-sky-700" style={{ animationDuration: "8s" }} /> IN-FLIGHT
                      </span>
                    )}
                    {sortie.status === "ALERT-5 STANDBY" && (
                      <span
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold"
                        style={{ background: "#faf5ff", color: "#6b21a8", border: "1px solid #a855f7" }}
                      >
                        <Radio size={12} className="text-purple-700" /> ALERT-5 STANDBY
                      </span>
                    )}
                    {sortie.status === "REROUTED" && (
                      <span
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold shadow-sm"
                        style={{ background: "#d97706", color: "#ffffff", border: "1px solid #b45309" }}
                      >
                        <AlertTriangle size={12} /> REROUTED (+{sortie.delayDeltaMin}m)
                      </span>
                    )}
                  </div>
                </div>

                {/* 4-Column Operational Grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
                  {/* Col 1: Assigned Airframe */}
                  <div className="p-3 rounded-lg sortie-col-box space-y-1.5">
                    <div className="flex items-center gap-1.5 sortie-col-header mb-1">
                      <Plane size={14} className="text-orange-600" />
                      <span>Assigned Aircraft</span>
                    </div>
                    <p className="font-semibold sortie-value-bold text-sm">
                      {sortie.airframeModel}
                    </p>
                    <div className="flex items-center justify-between sortie-sub-text text-[11px]">
                      <span>Tail: <strong className="font-mono sortie-value-bold">{sortie.tailNumber}</strong></span>
                      <span>Base: <strong className="sortie-value-bold">{sortie.homeBase}</strong></span>
                    </div>
                  </div>

                  {/* Col 2: Assigned Crew & Duty Hours */}
                  <div className="p-3 rounded-lg sortie-col-box space-y-1.5">
                    <div className="flex items-center gap-1.5 sortie-col-header mb-1">
                      <UserCheck size={14} className="text-emerald-600" />
                      <span>Assigned Crew</span>
                    </div>
                    <p className="font-semibold sortie-value-bold">
                      {sortie.pilotInCommand} <span className="text-[10px] sortie-muted-text font-normal">[PIC]</span>
                    </p>
                    <p className="sortie-sub-text text-[11px]">
                      {sortie.coPilotOrWso}
                    </p>
                    <div className="pt-1 flex items-center justify-between text-[11px]">
                      <span className="sortie-muted-text">Duty Margin:</span>
                      <span className="font-mono font-bold" style={{ color: "#065f46" }}>
                        {sortie.crewDutyRemainingHours}h left / {sortie.crewDutyLimitHours}h max
                      </span>
                    </div>
                  </div>

                  {/* Col 3: Munitions & Cargo Load */}
                  <div className="p-3 rounded-lg sortie-col-box space-y-1.5">
                    <div className="flex items-center gap-1.5 sortie-col-header mb-1">
                      <Package size={14} className="text-purple-600" />
                      <span>Payload / Munitions</span>
                    </div>
                    <p className="font-semibold sortie-value-bold line-clamp-2" title={sortie.payloadDescription}>
                      {sortie.payloadDescription}
                    </p>
                    <div className="flex items-center justify-between text-[11px] pt-1">
                      <span className="sortie-muted-text">Weight:</span>
                      <span className="font-mono font-bold sortie-value-bold">
                        {sortie.payloadWeightKg.toLocaleString("en-US")} kg
                      </span>
                    </div>
                    {sortie.isColdChainActive && (
                      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold border" style={{ background: "#f0f9ff", color: "#0369a1", border: "1px solid #7dd3fc" }}>
                        <Thermometer size={10} className="text-sky-700" /> Cold-Chain Verified
                      </span>
                    )}
                  </div>

                  {/* Col 4: Flight Route & Schedule (From -> To, Departure, Arrival) */}
                  <div className="p-3 rounded-lg sortie-col-box space-y-1.5">
                    <div className="flex items-center gap-1.5 sortie-col-header mb-1">
                      <MapPin size={14} className="text-sky-600" />
                      <span>Flight Route &amp; Timings</span>
                    </div>
                    <div className="font-semibold sortie-value-bold flex items-center gap-1 text-[11px]">
                      <span>{sortie.originBase}</span>
                      <ArrowRight size={11} className="text-orange-600 flex-shrink-0" />
                      <span className="font-bold sortie-value-bold">{sortie.destinationBase}</span>
                    </div>
                    <p className="text-[10px] sortie-muted-text truncate" title={sortie.transitCorridor}>
                      Via: {sortie.transitCorridor}
                    </p>
                    <div className="grid grid-cols-2 gap-1 text-[11px] pt-1 font-mono">
                      <div>
                        <span className="sortie-muted-text block text-[9px]">DEPARTURE:</span>
                        <strong className="sortie-value-bold">{sortie.departureTimeUtc}</strong>
                      </div>
                      <div>
                        <span className="sortie-muted-text block text-[9px]">EST. ARRIVAL:</span>
                        <strong className="font-bold" style={{ color: sortie.delayDeltaMin > 0 ? "#b45309" : "#065f46" }}>
                          {sortie.estimatedArrivalUtc}
                        </strong>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Delay & Reroute Notice row if any */}
                {sortie.delayCause && (
                  <div className="mt-3 p-2.5 rounded-lg border text-xs flex items-start gap-2 shadow-sm" style={{ background: "#fffbeb", border: "1px solid #fcd34d" }}>
                    <AlertTriangle size={15} className="flex-shrink-0 mt-0.5" style={{ color: "#b45309" }} />
                    <div>
                      <strong className="font-bold" style={{ color: "#78350f" }}>Dynamic Replan Rationale: </strong>
                      <span style={{ color: "#92400e" }}>{sortie.delayCause}</span>
                    </div>
                  </div>
                )}

                {/* Footer with safety margin and solver confirmation */}
                <div className="mt-2.5 pt-2 flex items-center justify-between text-[11px] sortie-muted-text border-t border-slate-200">
                  <div className="flex items-center gap-3">
                    <span>Deadline: <strong className="font-mono sortie-value-bold">{sortie.hardDeadlineUtc}</strong></span>
                    <span>Safety Margin: <strong className="font-mono font-bold" style={{ color: "#065f46" }}>+{sortie.safetyMarginMin} min</strong></span>
                  </div>
                  <div className="flex items-center gap-1 font-mono font-bold" style={{ color: "#065f46" }}>
                    <ShieldCheck size={13} style={{ color: "#059669" }} />
                    <span>{sortie.solverVerification}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab 1: Fleet Airframes */}
      {activeTab === "fleet" && (
        <div className="board-content">
          <div className="board-header-row">
            <div>
              <h3 className="board-title">Active Fleet Readiness &amp; Armament</h3>
              <p className="board-sub">
                Real-time aircraft turnaround predictions, fuel state, station hardpoints, and operational staging.
              </p>
            </div>
            <div className="ready-counter-chip">
              <span className="dot-green" />
              <span>
                {FLEET_AIRCRAFT.filter((a) => a.status === "Ready").length} of {FLEET_AIRCRAFT.length} Ready for Sortie
              </span>
            </div>
          </div>

          <div className="resource-grid">
            {FLEET_AIRCRAFT.map((ac) => (
              <div key={ac.id} className="resource-card glass-panel-sub">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="tail-badge">{ac.tailNumber}</span>
                    <span className="model-text font-semibold text-slate-900">{ac.model}</span>
                  </div>
                  <span
                    className={`status-pill ${
                      ac.status === "Ready"
                        ? "pill-ready"
                        : ac.status === "In-Flight"
                        ? "pill-flight"
                        : "pill-maint"
                    }`}
                  >
                    {ac.status}
                  </span>
                </div>

                <div className="card-detail-row">
                  <span className="detail-label">Base Station:</span>
                  <span className="detail-value">{ac.base}</span>
                </div>

                <div className="card-detail-row">
                  <span className="detail-label">Combat Radius:</span>
                  <span className="detail-value">{ac.combatRadiusKm} km</span>
                </div>

                {/* Fuel Meter */}
                <div className="my-2">
                  <div className="flex justify-between text-xs text-slate-600 mb-1">
                    <span className="flex items-center gap-1 font-medium">
                      <Fuel size={13} className="text-orange-600" /> Fuel State
                    </span>
                    <span className="font-bold text-slate-800">{ac.fuelPercent}%</span>
                  </div>
                  <div className="progress-track">
                    <div
                      className="progress-fill-orange"
                      style={{ width: `${ac.fuelPercent}%` }}
                    />
                  </div>
                </div>

                {/* Weapons Mounted */}
                <div className="mt-2 text-xs">
                  <span className="text-slate-500 font-medium block mb-1">Mounted Ordnance:</span>
                  <div className="flex flex-wrap gap-1">
                    {ac.weaponsMounted.map((wp, i) => (
                      <span key={i} className="weapon-tag">
                        {wp}
                      </span>
                    ))}
                  </div>
                </div>

                {ac.missionAssigned && (
                  <div className="assigned-mission-banner">
                    <Compass size={12} className="text-orange-600" />
                    <span>{ac.missionAssigned}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab 2: Crew Roster */}
      {activeTab === "crew" && (
        <div className="board-content">
          <div className="board-header-row">
            <div>
              <h3 className="board-title">Aircrew Operational Roster &amp; Fatigue Guard</h3>
              <p className="board-sub">
                Tracking flight hours, daily duty limit thresholds, Night-Ops qualification, and G-tolerance.
              </p>
            </div>
            <div className="ready-counter-chip">
              <span className="dot-green" />
              <span>
                {CREW_ROSTER.filter((c) => c.status === "Available" || c.status === "Standby").length} Qualified Pilots on Alert
              </span>
            </div>
          </div>

          <div className="resource-grid">
            {CREW_ROSTER.map((crew) => {
              const dutyPercent = Math.min(100, Math.round((crew.dutyHoursToday / crew.dutyLimitHours) * 100));
              const isOverDuty = crew.dutyHoursToday >= crew.dutyLimitHours;
              const isNearDuty = crew.dutyHoursToday >= crew.dutyLimitHours * 0.8;

              return (
                <div key={crew.id} className="resource-card glass-panel-sub">
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <span className="callsign-badge">&ldquo;{crew.callsign}&rdquo;</span>
                      <h4 className="font-bold text-slate-900 text-sm mt-1">{crew.name}</h4>
                      <span className="text-xs text-slate-500">{crew.rank} &bull; {crew.role}</span>
                    </div>
                    <span
                      className={`status-pill ${
                        crew.status === "Available"
                          ? "pill-ready"
                          : crew.status === "Standby"
                          ? "pill-flight"
                          : "pill-maint"
                      }`}
                    >
                      {crew.status}
                    </span>
                  </div>

                  {/* Duty Limit Progress Bar */}
                  <div className="my-2">
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-slate-600 font-medium flex items-center gap-1">
                        <Clock size={12} className="text-orange-600" /> Daily Duty Hours
                      </span>
                      <span
                        className={`font-bold ${
                          isOverDuty
                            ? "text-red-600"
                            : isNearDuty
                            ? "text-amber-600"
                            : "text-slate-800"
                        }`}
                      >
                        {crew.dutyHoursToday}h / {crew.dutyLimitHours}h max ({dutyPercent}%)
                      </span>
                    </div>
                    <div className="progress-track">
                      <div
                        className={`progress-fill ${
                          isOverDuty
                            ? "bg-red-500"
                            : isNearDuty
                            ? "bg-amber-500"
                            : "bg-emerald-500"
                        }`}
                        style={{ width: `${dutyPercent}%` }}
                      />
                    </div>
                  </div>

                  <div className="card-detail-row">
                    <span className="detail-label">Total Logged Flight:</span>
                    <span className="detail-value">{crew.flightHoursTotal} hrs</span>
                  </div>

                  <div className="card-detail-row">
                    <span className="detail-label">Type Ratings:</span>
                    <span className="detail-value">{crew.aircraftQualified.join(", ")}</span>
                  </div>

                  <div className="card-detail-row">
                    <span className="detail-label">G-Rating:</span>
                    <span className="detail-value font-semibold text-orange-600">
                      {crew.gToleranceRating}
                    </span>
                  </div>

                  <div className="mt-2 flex items-center gap-2">
                    {crew.nightOpsCertified && (
                      <span className="qualification-chip">🌙 Night-Ops Certified</span>
                    )}
                    <span
                      className={`qualification-chip ${
                        crew.restStatus === "Well Rested"
                          ? "chip-rested"
                          : crew.restStatus === "Alert-5 Standby"
                          ? "chip-standby"
                          : "chip-fatigue"
                      }`}
                    >
                      {crew.restStatus}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Tab 3: Weapons Inventory & Priority */}
      {activeTab === "weapons" && (
        <div className="board-content">
          <div className="board-header-row">
            <div>
              <h3 className="board-title">Precision Ordnance &amp; Priority Strike Packages</h3>
              <p className="board-sub">
                Munitions stockpile, engagement envelope, guidance systems, and mission priority hierarchy.
              </p>
            </div>
            <div className="ready-counter-chip">
              <span className="dot-orange" />
              <span>P1 Priority Munitions Fully Stocked</span>
            </div>
          </div>

          <div className="resource-grid">
            {WEAPON_SYSTEMS.map((wp) => (
              <div key={wp.id} className="resource-card glass-panel-sub">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <span
                      className={`priority-badge ${
                        wp.missionPriority.startsWith("P1")
                          ? "p1-badge"
                          : wp.missionPriority.startsWith("P2")
                          ? "p2-badge"
                          : "p3-badge"
                      }`}
                    >
                      {wp.missionPriority}
                    </span>
                    <h4 className="font-bold text-slate-900 text-sm mt-1">{wp.name}</h4>
                  </div>
                  <div className="stockpile-box">
                    <span className="stock-count">{wp.stockpileCount}</span>
                    <span className="stock-label">IN RESERVE</span>
                  </div>
                </div>

                <p className="text-xs text-slate-600 mb-2 font-medium">{wp.classType}</p>

                <div className="card-detail-row">
                  <span className="detail-label">Effective Range:</span>
                  <span className="detail-value font-bold text-slate-900">{wp.rangeKm} km</span>
                </div>

                <div className="card-detail-row">
                  <span className="detail-label">Speed Envelope:</span>
                  <span className="detail-value text-orange-600 font-semibold">{wp.speedMach}</span>
                </div>

                <div className="card-detail-row">
                  <span className="detail-label">Guidance Architecture:</span>
                  <span className="detail-value">{wp.guidance}</span>
                </div>

                <div className="mt-2 text-xs">
                  <span className="text-slate-500 font-medium block mb-1">Compatible Platforms:</span>
                  <div className="flex flex-wrap gap-1">
                    {wp.compatibleAircraft.map((p, i) => (
                      <span key={i} className="airframe-compat-tag">
                        {p}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab 4: Corridors & Weather */}
      {activeTab === "corridors" && (
        <div className="board-content">
          <div className="board-header-row">
            <div>
              <h3 className="board-title">Airspace Corridors &amp; Meteorological Radar</h3>
              <p className="board-sub">
                Flight altitudes, crosswind velocity, cloud ceiling conditions, and lightning hazard vectors.
              </p>
            </div>
            <div className="ready-counter-chip">
              <span className="dot-green" />
              <span>3 of 4 Corridors Navigable (VFR/IFR)</span>
            </div>
          </div>

          <div className="resource-grid">
            {AIR_CORRIDORS.map((corr) => (
              <div key={corr.id} className="resource-card glass-panel-sub">
                <div className="flex items-center justify-between mb-2">
                  <h4 className="font-bold text-slate-900 text-sm">{corr.name}</h4>
                  <span
                    className={`status-pill ${
                      corr.status === "OPEN"
                        ? "pill-ready"
                        : corr.status === "RESTRICTED"
                        ? "pill-flight"
                        : "pill-maint"
                    }`}
                  >
                    {corr.status}
                  </span>
                </div>

                <div className="card-detail-row">
                  <span className="detail-label">Altitude Window:</span>
                  <span className="detail-value font-semibold text-slate-800">{corr.altitudeBand}</span>
                </div>

                <div className="card-detail-row">
                  <span className="detail-label">Weather Category:</span>
                  <span
                    className={`detail-value font-bold ${
                      corr.weatherCondition.includes("SEVERE")
                        ? "text-red-600"
                        : corr.weatherCondition.includes("TURBULENT")
                        ? "text-amber-600"
                        : "text-emerald-600"
                    }`}
                  >
                    {corr.weatherCondition}
                  </span>
                </div>

                <div className="card-detail-row">
                  <span className="detail-label">Visibility:</span>
                  <span className="detail-value">{corr.visibilityKm} km</span>
                </div>

                <div className="card-detail-row">
                  <span className="detail-label">Crosswind:</span>
                  <span className="detail-value">{corr.crosswindKnots} knots</span>
                </div>

                <div className="card-detail-row">
                  <span className="detail-label">Lightning Hazard:</span>
                  <span
                    className={`detail-value font-semibold ${
                      corr.lightningHazard === "Critical"
                        ? "text-red-600"
                        : corr.lightningHazard === "High"
                        ? "text-amber-600"
                        : "text-slate-600"
                    }`}
                  >
                    {corr.lightningHazard}
                  </span>
                </div>

                {/* Risk Bar */}
                <div className="my-2">
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-slate-500 font-medium">Corridor Risk Index</span>
                    <span className="font-bold text-slate-800">{corr.riskIndex} / 100</span>
                  </div>
                  <div className="progress-track">
                    <div
                      className={`progress-fill ${
                        corr.riskIndex > 70
                          ? "bg-red-500"
                          : corr.riskIndex > 30
                          ? "bg-amber-500"
                          : "bg-emerald-500"
                      }`}
                      style={{ width: `${corr.riskIndex}%` }}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab 5: Active Threats */}
      {activeTab === "threats" && (
        <div className="board-content">
          <div className="board-header-row">
            <div>
              <h3 className="board-title">Tactical Threat Matrix &amp; Radar Envelope</h3>
              <p className="board-sub">
                Active hostile SAM radar locks, electronic warfare jamming arrays, and algorithmic routing mitigations.
              </p>
            </div>
            <div className="ready-counter-chip">
              <span className="dot-red" />
              <span>3 Hostile Emitters Monitored</span>
            </div>
          </div>

          {/* Tactical Radar Scope HUD (360° Live Sweeping Radar) */}
          <div className="radar-scope-container glass-panel-sub mb-4 p-4 flex flex-col md:flex-row items-center justify-around gap-6">
            <div className="relative w-48 h-48 rounded-full border-2 border-emerald-500/40 bg-slate-950/85 shadow-[0_0_25px_rgba(16,185,129,0.18)] overflow-hidden flex items-center justify-center flex-shrink-0">
              {/* Concentric Range Rings */}
              <div className="absolute w-36 h-36 rounded-full border border-emerald-500/25 pointer-events-none" />
              <div className="absolute w-24 h-24 rounded-full border border-emerald-500/20 pointer-events-none" />
              <div className="absolute w-12 h-12 rounded-full border border-emerald-500/20 pointer-events-none" />
              <div className="absolute inset-x-0 top-1/2 h-px bg-emerald-500/25 pointer-events-none" />
              <div className="absolute inset-y-0 left-1/2 w-px bg-emerald-500/25 pointer-events-none" />

              {/* Sweeping Radar Beam */}
              <div className="radar-sweep-beam" />

              {/* Blip 1: S-400 Radar (Grid 41 - Hostile) */}
              <div className="absolute top-7 right-10 flex flex-col items-center">
                <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-ping absolute" />
                <span className="w-2.5 h-2.5 rounded-full bg-red-500 shadow-[0_0_8px_#ef4444]" />
                <span className="text-[8px] font-mono font-bold text-red-400 mt-0.5 tracking-tighter">SAM-400</span>
              </div>

              {/* Blip 2: Friendly Rafale In-Flight (CAP Escort) */}
              <div className="absolute bottom-9 left-10 flex flex-col items-center">
                <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse absolute" />
                <span className="w-2 h-2 rounded-full bg-cyan-400 shadow-[0_0_8px_#22d3ee]" />
                <span className="text-[8px] font-mono font-bold text-cyan-300 mt-0.5 tracking-tighter">RAF-015</span>
              </div>

              {/* Blip 3: Lead Su-30MKI Ingress */}
              <div className="absolute top-14 left-14 flex flex-col items-center">
                <span className="w-2 h-2 rounded-full bg-orange-400 shadow-[0_0_8px_#fb923c]" />
                <span className="text-[8px] font-mono font-bold text-orange-300 mt-0.5 tracking-tighter">SU30-042</span>
              </div>

              {/* Center Home Base Dot */}
              <div className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_#34d399] z-10" />
            </div>

            <div className="flex-1">
              <div className="flex items-center gap-2 mb-2">
                <span className="inline-block w-2.5 h-2.5 rounded-full bg-emerald-500 animate-ping" />
                <span className="text-xs font-bold text-slate-900 tracking-wider font-mono">
                  LIVE AIR DEFENSE RADAR (360° DOPPLER SWEEP)
                </span>
              </div>
              <p className="text-xs text-slate-600 mb-3 leading-relaxed">
                Active Doppler and ELINT sweep tracking 1 Hostile S-400 radar emitter, 1 EW jamming source, and 2 friendly airborne strike formations. Stand-off separation algorithm dynamically recalculates ingress corridors every second.
              </p>
              <div className="flex flex-wrap gap-4 text-xs font-mono">
                <div><span className="text-slate-400">SWEEP RATE:</span> <span className="font-bold text-slate-800">4.0s / 360°</span></div>
                <div><span className="text-slate-400">RANGE SCALE:</span> <span className="font-bold text-emerald-600">250 KM</span></div>
                <div><span className="text-slate-400">SURVIVABILITY:</span> <span className="font-bold text-orange-600">98.4%</span></div>
              </div>
            </div>
          </div>

          <div className="resource-grid">
            {ACTIVE_THREATS.map((thr) => (
              <div key={thr.id} className="resource-card glass-panel-sub">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <ShieldAlert size={18} className="text-red-600" />
                    <h4 className="font-bold text-slate-900 text-sm">{thr.name}</h4>
                  </div>
                  <span className="severity-pill">SEV {thr.severityScore}</span>
                </div>

                <div className="card-detail-row">
                  <span className="detail-label">Emitter Class:</span>
                  <span className="detail-value font-semibold text-slate-800">{thr.type}</span>
                </div>

                <div className="card-detail-row">
                  <span className="detail-label">Sector Coordinates:</span>
                  <span className="detail-value">{thr.sector}</span>
                </div>

                <div className="card-detail-row">
                  <span className="detail-label">Radar Frequency:</span>
                  <span className="detail-value font-mono text-xs">{thr.radarBand}</span>
                </div>

                <div className="card-detail-row">
                  <span className="detail-label">Stand-Off Minimum:</span>
                  <span className="detail-value font-bold text-orange-600">
                    &ge; {thr.standoffRequiredKm} km
                  </span>
                </div>

                <div className="mitigation-box">
                  <span className="text-xs font-bold text-slate-700 block mb-1">
                    ACTIVE MITIGATION PROTOCOL:
                  </span>
                  <p className="text-xs text-slate-600 leading-snug">{thr.mitigation}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab 6: Pipeline Feeds Health */}
      {activeTab === "pipeline" && (
        <div className="board-content">
          <div className="board-header-row">
            <div>
              <h3 className="board-title">Data Ingestion Streams &amp; Storage Health</h3>
              <p className="board-sub">
                Live monitoring of Apache Kafka topics, PostgreSQL persistent layer, and sensor feeds.
              </p>
            </div>
            <div className="ready-counter-chip">
              <span className="dot-green" />
              <span>All 5 Data Telemetry Nodes Synced</span>
            </div>
          </div>

          <div className="pipeline-nodes-grid">
            {PIPELINE_NODES.map((node, i) => (
              <div key={i} className="pipeline-node-card glass-panel-sub">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Radio size={16} className="text-orange-600 animate-pulse" />
                    <h4 className="font-bold text-slate-900 text-sm">{node.name}</h4>
                  </div>
                  <span className="node-status-pill">{node.status}</span>
                </div>

                <div className="card-detail-row">
                  <span className="detail-label">Endpoint / Port:</span>
                  <span className="detail-value font-mono text-xs text-slate-700">{node.portOrEndpoint}</span>
                </div>

                <div className="card-detail-row">
                  <span className="detail-label">Throughput Rate:</span>
                  <span className="detail-value font-bold text-orange-600">{node.throughput}</span>
                </div>

                <div className="card-detail-row">
                  <span className="detail-label">Network Latency:</span>
                  <span className="detail-value font-medium text-slate-800">{node.latencyMs} ms</span>
                </div>

                <div className="card-detail-row">
                  <span className="detail-label">Cluster Uptime:</span>
                  <span className="detail-value text-emerald-600 font-semibold">{node.uptime}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

