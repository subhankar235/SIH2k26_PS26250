export interface Aircraft {
  id: string;
  tailNumber: string;
  model: string;
  type: "Fighter" | "Multi-Role" | "Tactical Transport" | "Refueler" | "AEW&C";
  base: string;
  status: "Ready" | "In-Flight" | "Turnaround" | "Maintenance";
  fuelPercent: number;
  hardpoints: string;
  weaponsMounted: string[];
  turnaroundEstMin: number;
  combatRadiusKm: number;
  missionAssigned?: string;
}

export interface CrewMember {
  id: string;
  callsign: string;
  name: string;
  rank: string;
  role: string;
  aircraftQualified: string[];
  flightHoursTotal: number;
  dutyHoursToday: number;
  dutyLimitHours: number;
  restStatus: "Well Rested" | "Alert-5 Standby" | "Fatigue Alert" | "Rest Mandated";
  status: "Available" | "Dispatched" | "Standby" | "Mandatory Rest";
  nightOpsCertified: boolean;
  gToleranceRating: string;
}

export interface WeaponSystem {
  id: string;
  name: string;
  classType: string;
  rangeKm: number;
  speedMach: string;
  guidance: string;
  compatibleAircraft: string[];
  stockpileCount: number;
  missionPriority: "P1 Immediate Strike" | "P2 Air Defense Alert" | "P3 Combat Air Patrol" | "P4 Tactical Support";
  warheadType: string;
}

export interface AirCorridor {
  id: string;
  name: string;
  altitudeBand: string;
  trafficDensity: "Low" | "Moderate" | "High";
  weatherCondition: "CLEAR (VFR)" | "SCATTERED (VFR)" | "TURBULENT (IFR)" | "SEVERE STORM (NO-GO)";
  visibilityKm: number;
  crosswindKnots: number;
  lightningHazard: "None" | "Low" | "High" | "Critical";
  status: "OPEN" | "RESTRICTED" | "CLOSED";
  riskIndex: number;
}

export interface ThreatItem {
  id: string;
  name: string;
  type: "SAM Radar Lock" | "EW Jamming" | "MANPADS Sector" | "Airborne Radar Intercept";
  sector: string;
  radarBand: string;
  standoffRequiredKm: number;
  severityScore: number;
  status: "ACTIVE TRACKING" | "INTERMITTENT" | "MONITORED";
  mitigation: string;
}

export interface PipelineHealthNode {
  name: string;
  category: "Ingestion" | "Storage" | "Radar" | "Sensors" | "Defense";
  portOrEndpoint: string;
  status: "HEALTHY" | "DEGRADED" | "OFFLINE";
  throughput: string;
  latencyMs: number;
  uptime: string;
}

export interface MagiAgent {
  id: string;
  name: string;
  magiDesignation: string; // e.g., FLEET & AIRFRAME AGENT, PILOT & CREW ROSTER AGENT
  specialty: string;
  model: string;
  status: "AGREE" | "OBJECT" | "DELIBERATING" | "OPTIMIZING";
  vote: "APPROVED" | "OBJECTION" | "EVALUATING";
  confidence: number;
  rationale: string;
  constraintsEnforced: string[];
  lastBidTime: string;
}

export const FLEET_AIRCRAFT: Aircraft[] = [
  {
    id: "AC-01",
    tailNumber: "SU30-SB042",
    model: "Su-30MKI Super Flanker",
    type: "Multi-Role",
    base: "Bareilly AFS",
    status: "Ready",
    fuelPercent: 94,
    hardpoints: "12 / 12 Loaded",
    weaponsMounted: ["2x BrahMos-A", "4x Astra Mk-1", "2x R-73"],
    turnaroundEstMin: 22,
    combatRadiusKm: 3000,
    missionAssigned: "MSN-OP-901 (Deep Strike Corridor Alpha)",
  },
  {
    id: "AC-02",
    tailNumber: "RAF-RB011",
    model: "Dassault Rafale EH",
    type: "Fighter",
    base: "Ambala AFS",
    status: "Ready",
    fuelPercent: 91,
    hardpoints: "14 / 14 Loaded",
    weaponsMounted: ["2x SCALP EG", "4x Meteor BVR", "2x MICA IR"],
    turnaroundEstMin: 18,
    combatRadiusKm: 3700,
    missionAssigned: "MSN-OP-902 (Air Superiority Sweep)",
  },
  {
    id: "AC-03",
    tailNumber: "RAF-RB015",
    model: "Dassault Rafale EH",
    type: "Fighter",
    base: "Ambala AFS",
    status: "In-Flight",
    fuelPercent: 64,
    hardpoints: "10 / 14 Loaded",
    weaponsMounted: ["4x Meteor BVR", "2x MICA IR"],
    turnaroundEstMin: 42,
    combatRadiusKm: 3700,
    missionAssigned: "MSN-CAP-404 (Combat Air Patrol)",
  },
  {
    id: "AC-04",
    tailNumber: "TEJ-LA008",
    model: "HAL Tejas Mk-1A",
    type: "Fighter",
    base: "Sulur AFS",
    status: "Ready",
    fuelPercent: 100,
    hardpoints: "8 / 8 Loaded",
    weaponsMounted: ["2x Astra Mk-1", "2x ASRAAM", "Drop Tanks"],
    turnaroundEstMin: 15,
    combatRadiusKm: 1850,
    missionAssigned: "MSN-DEF-301 (Base Perimeter Intercept)",
  },
  {
    id: "AC-05",
    tailNumber: "TEJ-LA012",
    model: "HAL Tejas Mk-1A",
    type: "Fighter",
    base: "Naliya AFS",
    status: "Turnaround",
    fuelPercent: 48,
    hardpoints: "4 / 8 Staged",
    weaponsMounted: ["2x ASRAAM"],
    turnaroundEstMin: 28,
    combatRadiusKm: 1850,
  },
  {
    id: "AC-06",
    tailNumber: "C130-KC382",
    model: "C-130J Super Hercules",
    type: "Tactical Transport",
    base: "Hindon AFS",
    status: "Ready",
    fuelPercent: 96,
    hardpoints: "Internal Cargo Bay",
    weaponsMounted: ["Tactical Supply Pod", "Medical Evac Kit"],
    turnaroundEstMin: 35,
    combatRadiusKm: 3800,
    missionAssigned: "MSN-LOG-110 (Forward Base Resupply)",
  },
  {
    id: "AC-07",
    tailNumber: "IL78-RK3451",
    model: "Ilyushin IL-78 MKI",
    type: "Refueler",
    base: "Agra AFS",
    status: "Ready",
    fuelPercent: 98,
    hardpoints: "3x UPAZ Refueling Pods",
    weaponsMounted: ["110,000 kg Transferable Fuel"],
    turnaroundEstMin: 30,
    combatRadiusKm: 7300,
    missionAssigned: "MSN-AAR-202 (Orbit Charlie Refueling)",
  },
  {
    id: "AC-08",
    tailNumber: "EMB-AW145",
    model: "DRDO Netra AEW&C",
    type: "AEW&C",
    base: "Bhatinda AFS",
    status: "In-Flight",
    fuelPercent: 72,
    hardpoints: "Active AESA Dome",
    weaponsMounted: ["240° Active Radar & EW Suite"],
    turnaroundEstMin: 55,
    combatRadiusKm: 4500,
    missionAssigned: "MSN-ISR-001 (Airborne Early Warning)",
  },
];

export const CREW_ROSTER: CrewMember[] = [
  {
    id: "CRW-01",
    callsign: "Viper",
    name: "Wg Cdr Aarav Rathore",
    rank: "Wing Commander",
    role: "Lead Strike Pilot",
    aircraftQualified: ["Su-30MKI", "Rafale"],
    flightHoursTotal: 2480,
    dutyHoursToday: 3.2,
    dutyLimitHours: 8.0,
    restStatus: "Well Rested",
    status: "Available",
    nightOpsCertified: true,
    gToleranceRating: "9.0G Combat Rated",
  },
  {
    id: "CRW-02",
    callsign: "Garuda",
    name: "Sqn Ldr Dev Nair",
    rank: "Squadron Leader",
    role: "Interceptor Pilot",
    aircraftQualified: ["Rafale", "Tejas Mk-1A"],
    flightHoursTotal: 1840,
    dutyHoursToday: 4.1,
    dutyLimitHours: 8.0,
    restStatus: "Alert-5 Standby",
    status: "Standby",
    nightOpsCertified: true,
    gToleranceRating: "9.0G Combat Rated",
  },
  {
    id: "CRW-03",
    callsign: "Thunder",
    name: "Flt Lt Tara Chawla",
    rank: "Flight Lieutenant",
    role: "Combat Air Patrol",
    aircraftQualified: ["Tejas Mk-1A"],
    flightHoursTotal: 920,
    dutyHoursToday: 6.8,
    dutyLimitHours: 8.0,
    restStatus: "Fatigue Alert",
    status: "Available",
    nightOpsCertified: false,
    gToleranceRating: "8.5G Certified",
  },
  {
    id: "CRW-04",
    callsign: "Spectre",
    name: "Wg Cdr Kabir Sen",
    rank: "Wing Commander",
    role: "Tactical Airlift Commander",
    aircraftQualified: ["C-130J", "IL-76"],
    flightHoursTotal: 3200,
    dutyHoursToday: 2.1,
    dutyLimitHours: 10.0,
    restStatus: "Well Rested",
    status: "Available",
    nightOpsCertified: true,
    gToleranceRating: "Standard Transport",
  },
  {
    id: "CRW-05",
    callsign: "Azure",
    name: "Sqn Ldr Rohan Mehra",
    rank: "Squadron Leader",
    role: "WSO / Electronic Warfare",
    aircraftQualified: ["Su-30MKI"],
    flightHoursTotal: 1450,
    dutyHoursToday: 7.5,
    dutyLimitHours: 8.0,
    restStatus: "Rest Mandated",
    status: "Mandatory Rest",
    nightOpsCertified: true,
    gToleranceRating: "9.0G Combat Rated",
  },
  {
    id: "CRW-06",
    callsign: "Phoenix",
    name: "Flt Lt Sneha Kulkarni",
    rank: "Flight Lieutenant",
    role: "Aerial Tanker Specialist",
    aircraftQualified: ["IL-78 MKI"],
    flightHoursTotal: 1120,
    dutyHoursToday: 1.5,
    dutyLimitHours: 10.0,
    restStatus: "Well Rested",
    status: "Available",
    nightOpsCertified: true,
    gToleranceRating: "Standard Tanker",
  },
];

export const WEAPON_SYSTEMS: WeaponSystem[] = [
  {
    id: "WPN-01",
    name: "Astra Mk-1",
    classType: "BVR Air-to-Air Missile",
    rangeKm: 110,
    speedMach: "Mach 4.5",
    guidance: "Active Radar Homing",
    compatibleAircraft: ["Su-30MKI", "Tejas Mk-1A", "Rafale"],
    stockpileCount: 48,
    missionPriority: "P1 Immediate Strike",
    warheadType: "15 kg High Explosive Pre-fragmented",
  },
  {
    id: "WPN-02",
    name: "BrahMos-A",
    classType: "Air-Launched Supersonic Cruise",
    rangeKm: 450,
    speedMach: "Mach 3.0",
    guidance: "INS/GPS + Active Radar Seeker",
    compatibleAircraft: ["Su-30MKI"],
    stockpileCount: 16,
    missionPriority: "P1 Immediate Strike",
    warheadType: "300 kg Semi-Armor Piercing",
  },
  {
    id: "WPN-03",
    name: "Meteor",
    classType: "Ramjet BVR Air-to-Air",
    rangeKm: 200,
    speedMach: "Mach 4+",
    guidance: "Active Radar + 2-Way Data Link",
    compatibleAircraft: ["Rafale"],
    stockpileCount: 24,
    missionPriority: "P2 Air Defense Alert",
    warheadType: "Proximity Blast-Fragmentation",
  },
  {
    id: "WPN-04",
    name: "Spice-2000",
    classType: "Precision Guided Glide Bomb",
    rangeKm: 60,
    speedMach: "Glide Subsonic",
    guidance: "CCD/IIR Dual Electro-Optical / GPS",
    compatibleAircraft: ["Su-30MKI", "Rafale"],
    stockpileCount: 32,
    missionPriority: "P2 Air Defense Alert",
    warheadType: "900 kg Bunker Buster / Blast Penetrator",
  },
  {
    id: "WPN-05",
    name: "R-73 & ASRAAM",
    classType: "Short Range Within Visual Range (WVR)",
    rangeKm: 30,
    speedMach: "Mach 3.5",
    guidance: "Infrared High Off-Boresight",
    compatibleAircraft: ["Su-30MKI", "Tejas Mk-1A", "Rafale"],
    stockpileCount: 68,
    missionPriority: "P3 Combat Air Patrol",
    warheadType: "7.4 kg Continuous Rod Fragmenting",
  },
  {
    id: "WPN-06",
    name: "CBU-105 Sensor Fuzed Weapon",
    classType: "Anti-Armor Cluster Munition",
    rangeKm: 15,
    speedMach: "Free-fall Ballistic",
    guidance: "Infrared Target Discriminator Skeets",
    compatibleAircraft: ["Su-30MKI", "C-130J"],
    stockpileCount: 20,
    missionPriority: "P4 Tactical Support",
    warheadType: "40x Armor Piercing Explosively Formed Projectiles",
  },
];

export const AIR_CORRIDORS: AirCorridor[] = [
  {
    id: "CORR-01",
    name: "Corridor Alpha-1 (Northern Transit)",
    altitudeBand: "FL240 - FL380",
    trafficDensity: "Low",
    weatherCondition: "CLEAR (VFR)",
    visibilityKm: 12,
    crosswindKnots: 8,
    lightningHazard: "None",
    status: "OPEN",
    riskIndex: 12,
  },
  {
    id: "CORR-02",
    name: "Corridor Bravo-3 (Western Flank)",
    altitudeBand: "FL180 - FL300",
    trafficDensity: "Moderate",
    weatherCondition: "SCATTERED (VFR)",
    visibilityKm: 9,
    crosswindKnots: 16,
    lightningHazard: "Low",
    status: "OPEN",
    riskIndex: 28,
  },
  {
    id: "CORR-03",
    name: "Corridor Charlie-7 (Central Valley)",
    altitudeBand: "FL220 - FL360",
    trafficDensity: "Low",
    weatherCondition: "SEVERE STORM (NO-GO)",
    visibilityKm: 2.1,
    crosswindKnots: 44,
    lightningHazard: "Critical",
    status: "CLOSED",
    riskIndex: 89,
  },
  {
    id: "CORR-04",
    name: "Corridor Zulu-9 (Tactical Ingress)",
    altitudeBand: "FL150 - FL260",
    trafficDensity: "High",
    weatherCondition: "TURBULENT (IFR)",
    visibilityKm: 6.5,
    crosswindKnots: 22,
    lightningHazard: "Low",
    status: "RESTRICTED",
    riskIndex: 58,
  },
];

export const ACTIVE_THREATS: ThreatItem[] = [
  {
    id: "THR-01",
    name: "Sector Bravo Long-Range SAM (S-400)",
    type: "SAM Radar Lock",
    sector: "North-West Border Grid 41",
    radarBand: "X/S-Band Track Radar",
    standoffRequiredKm: 180,
    severityScore: 88,
    status: "ACTIVE TRACKING",
    mitigation: "Terrain Masking below FL160 + Electronic Jamming Pod Active",
  },
  {
    id: "THR-02",
    name: "Corridor Charlie GPS/VHF Spoofing Array",
    type: "EW Jamming",
    sector: "Valley Central Sector",
    radarBand: "L-Band GPS L1/L2 Jamming",
    standoffRequiredKm: 45,
    severityScore: 54,
    status: "INTERMITTENT",
    mitigation: "Auto-switched to Ring Laser Gyro INS & NavIC military signal",
  },
  {
    id: "THR-03",
    name: "Ridge Crest MANPADS Threat Zone",
    type: "MANPADS Sector",
    sector: "Pass Alpha Low Altitude",
    radarBand: "Passive Dual-Color IR Seeker",
    standoffRequiredKm: 15,
    severityScore: 42,
    status: "MONITORED",
    mitigation: "Enforcing minimum operational floor > FL150 for all strike packages",
  },
];

export const PIPELINE_NODES: PipelineHealthNode[] = [
  {
    name: "Kafka Event Broker",
    category: "Ingestion",
    portOrEndpoint: "127.0.0.1:29092",
    status: "HEALTHY",
    throughput: "1,420 msgs/s",
    latencyMs: 1.8,
    uptime: "99.98%",
  },
  {
    name: "PostgreSQL Storage Store",
    category: "Storage",
    portOrEndpoint: "127.0.0.1:5432",
    status: "HEALTHY",
    throughput: "185 commits/s",
    latencyMs: 3.2,
    uptime: "100.0%",
  },
  {
    name: "ADS-B Radar Telemetry",
    category: "Radar",
    portOrEndpoint: "Sensors Grid Bus",
    status: "HEALTHY",
    throughput: "24 updates/s",
    latencyMs: 4.1,
    uptime: "99.95%",
  },
  {
    name: "Doppler Meteorological Feed",
    category: "Sensors",
    portOrEndpoint: "Doppler-Net API",
    status: "HEALTHY",
    throughput: "1 radar sweep/min",
    latencyMs: 8.5,
    uptime: "99.89%",
  },
  {
    name: "SAM Threat Intel Intercept",
    category: "Defense",
    portOrEndpoint: "Tactical Defense Network",
    status: "HEALTHY",
    throughput: "Live EW stream",
    latencyMs: 2.4,
    uptime: "99.99%",
  },
];

export const MAGI_INITIAL_AGENTS: MagiAgent[] = [
  {
    id: "AGENT-FLEET",
    name: "AERO-FLEET-01",
    magiDesignation: "FLEET READINESS & AIRFRAME AGENT",
    specialty: "Airframe Health, Turnaround Prediction, Fuel & Maintenance Reserves",
    model: "RandomForestTurnaroundRegressor (RMSE: 3.2m)",
    status: "AGREE",
    vote: "APPROVED",
    confidence: 98.6,
    rationale: "All primary strike airframes verified ready. Turnaround predictions for SU-30 and Rafale cohorts meet mission launch windows with a 24-minute safety margin.",
    constraintsEnforced: ["Capacity >= Required", "TurnaroundBuffer >= 15m", "FuelReserve >= 25%"],
    lastBidTime: "10:14:02 UTC",
  },
  {
    id: "AGENT-CREW",
    name: "CREW-LOGISTICS-02",
    magiDesignation: "PILOT & CREW ROSTER AGENT",
    specialty: "Crew Duty Limits, Fatigue Guard, Night Ops Qualifications",
    model: "CrewFatigueRiskClassifier (AUC: 0.991)",
    status: "AGREE",
    vote: "APPROVED",
    confidence: 97.4,
    rationale: "Crew flight hours comply with 8.0h daily limit. Flt Lt Chawla at 6.8h is flagged for relief; Sqn Ldr Dev Nair staged on Alert-5 backup.",
    constraintsEnforced: ["MaxDutyHours <= 8.0h", "NightOpsQualified == True", "RestPeriod >= 12h"],
    lastBidTime: "10:14:04 UTC",
  },
  {
    id: "AGENT-ORDNANCE",
    name: "ARMAMENT-ALLOC-03",
    magiDesignation: "MUNITIONS & WEAPONS AGENT",
    specialty: "Hardpoint Loading, Weapon-to-Target Matching, P1 Strike Packages",
    model: "OrdnanceCompatibilityMatrix (100% Rule Enforced)",
    status: "AGREE",
    vote: "APPROVED",
    confidence: 99.2,
    rationale: "Munition configurations balanced: dual BrahMos-A and Astra Mk-1 loadouts verified within Max Take-Off Weight (MTOW) envelope.",
    constraintsEnforced: ["HardpointWeight <= MaxStationWeight", "BrahMosOnlySu30", "SufficientStockpile"],
    lastBidTime: "10:14:03 UTC",
  },
  {
    id: "AGENT-CORRIDOR",
    name: "AIRSPACE-VECTOR-04",
    magiDesignation: "AIRSPACE & CORRIDOR AGENT",
    specialty: "Civil Air Traffic Deconfliction, Transit Flight Levels, Airway Saturation",
    model: "AirspaceDeconflictionModel (99.4% Safety Gate)",
    status: "AGREE",
    vote: "APPROVED",
    confidence: 97.8,
    rationale: "Corridor Alpha-1 and Bravo-3 transit lanes open with FL280 to FL340 altitude clearance. Low civilian congestion confirmed.",
    constraintsEnforced: ["CivilSeparation >= 10nm", "CorridorCapacity <= MaxRate", "NoRestrictedZoneIncursion"],
    lastBidTime: "10:14:03 UTC",
  },
  {
    id: "AGENT-THREAT",
    name: "THREAT-INTEL-05",
    magiDesignation: "ELECTRONIC WARFARE & THREAT AGENT",
    specialty: "SAM Radar Locks, EW Jamming Analysis, Corridor Survivability",
    model: "GradientBoostedRiskScorer (ROC-AUC: 0.968)",
    status: "AGREE",
    vote: "APPROVED",
    confidence: 96.1,
    rationale: "Threat index quantified at 14.2 / 100. Stand-off corridors planned outside S-400 envelope; low-altitude ingress masked by valley terrain.",
    constraintsEnforced: ["ThreatRiskThreshold <= 35.0", "StandoffDistance >= 150km"],
    lastBidTime: "10:14:05 UTC",
  },
  {
    id: "AGENT-WEATHER",
    name: "MET-ATMOSPHERE-06",
    magiDesignation: "METEOROLOGY & STORM AGENT",
    specialty: "Corridor Cloud Ceilings, Crosswinds, Convective Thunderstorm Cells",
    model: "MicroburstNowcastModel (Accuracy: 97.8%)",
    status: "AGREE",
    vote: "APPROVED",
    confidence: 98.0,
    rationale: "Corridor Alpha-1 weather is clear VFR. Central Valley thunderstorm cell in Corridor Charlie is isolated and rerouted around.",
    constraintsEnforced: ["Crosswind <= 25kts", "Visibility >= 5km", "NoConvectiveCellInPath"],
    lastBidTime: "10:14:01 UTC",
  },
];

export const SYSTEM_KPIS = {
  timeSavedPercent: 94.2,
  timeSavedDescription: "1.4s dynamic replanning vs 45 min manual staff coordination",
  conflictsPreventedCount: 18,
  conflictsPreventedBreakdown: "8 Crew duty overages, 6 Corridor weather breaches, 4 Incompatible loadouts prevented",
  operationalRiskIndex: 14.2,
  operationalRiskMax: 100,
  operationalRiskLevel: "LOW RISK",
  fleetReadyPercent: 81.8,
  activeAirframesReady: 18,
  totalFleetCount: 22,
  consensusRatePercent: 100,
  solverLatencyMs: 1420,
};

export interface SortieDispatch {
  id: string;
  callsign: string;
  missionName: string;
  priority: "P-1 Urgent Strike" | "P-2 Air Superiority" | "P-3 Tactical Airlift" | "P-4 Combat Air Patrol" | "P-5 Strategic Support";
  airframeId: string;
  airframeModel: string;
  tailNumber: string;
  homeBase: string;
  pilotInCommand: string;
  coPilotOrWso: string;
  crewDutyRemainingHours: number;
  crewDutyLimitHours: number;
  crewFatigueScore: number;
  payloadDescription: string;
  payloadWeightKg: number;
  isColdChainActive: boolean;
  isHazardousClass1: boolean;
  originBase: string;
  transitCorridor: string;
  destinationBase: string;
  departureTimeUtc: string;
  flightDurationMin: number;
  estimatedArrivalUtc: string;
  hardDeadlineUtc: string;
  safetyMarginMin: number;
  status: "ON SCHEDULE" | "IN-FLIGHT" | "ALERT-5 STANDBY" | "DELAYED" | "REROUTED";
  delayDeltaMin: number;
  delayCause?: string;
  solverVerification: "VERIFIED OPTIMAL (CP-SAT)" | "INSPECTION REQUIRED";
}

export const TACTICAL_SORTIES: SortieDispatch[] = [
  {
    id: "MSN-OP-901",
    callsign: "GARUDA-01",
    missionName: "Deep Strike Alpha (Forward Deterrence)",
    priority: "P-1 Urgent Strike",
    airframeId: "SU30-SB042",
    airframeModel: "Sukhoi Su-30MKI Flanker-H",
    tailNumber: "SB042",
    homeBase: "Bareilly AFS (Base-A)",
    pilotInCommand: "Wg Cdr Vikram Joshi",
    coPilotOrWso: "Sqn Ldr Dev Nair (WSO)",
    crewDutyRemainingHours: 1.2,
    crewDutyLimitHours: 8.0,
    crewFatigueScore: 0.12,
    payloadDescription: "2x BrahMos-A Supersonic Cruise + 4x Astra Mk-1 BVR + 2x R-73",
    payloadWeightKg: 9400,
    isColdChainActive: false,
    isHazardousClass1: true,
    originBase: "Bareilly AFS",
    transitCorridor: "Corridor Alpha-1 (Direct FL320, 850 km)",
    destinationBase: "Leh Forward AFS (Base-B)",
    departureTimeUtc: "10:00 UTC (T+00:00)",
    flightDurationMin: 75,
    estimatedArrivalUtc: "11:15 UTC (T+01:15)",
    hardDeadlineUtc: "12:00 UTC",
    safetyMarginMin: 45,
    status: "ON SCHEDULE",
    delayDeltaMin: 0,
    solverVerification: "VERIFIED OPTIMAL (CP-SAT)",
  },
  {
    id: "MSN-OP-902",
    callsign: "TIGER-SWEEP-2",
    missionName: "Air Superiority BVR Combat Patrol",
    priority: "P-2 Air Superiority",
    airframeId: "RAF-RB011",
    airframeModel: "Dassault Rafale EH",
    tailNumber: "RB011",
    homeBase: "Ambala AFS",
    pilotInCommand: "Wg Cdr Arjun Rathore",
    coPilotOrWso: "Single Seat (Integrated SPECTRA EW)",
    crewDutyRemainingHours: 3.4,
    crewDutyLimitHours: 8.0,
    crewFatigueScore: 0.18,
    payloadDescription: "2x SCALP-EG Cruise + 4x Meteor Long-Range BVR + 2x MICA IR",
    payloadWeightKg: 8200,
    isColdChainActive: false,
    isHazardousClass1: true,
    originBase: "Ambala AFS",
    transitCorridor: "Corridor Alpha-1 (FL340 High Transit, 720 km)",
    destinationBase: "Udhampur Sector Base",
    departureTimeUtc: "10:15 UTC (T+00:15)",
    flightDurationMin: 65,
    estimatedArrivalUtc: "11:20 UTC (T+01:20)",
    hardDeadlineUtc: "12:15 UTC",
    safetyMarginMin: 55,
    status: "IN-FLIGHT",
    delayDeltaMin: 0,
    solverVerification: "VERIFIED OPTIMAL (CP-SAT)",
  },
  {
    id: "MSN-LOG-110",
    callsign: "SAMARITAN-04",
    missionName: "Forward Base Resupply & Critical Medical Evac",
    priority: "P-3 Tactical Airlift",
    airframeId: "C130-KC382",
    airframeModel: "Lockheed C-130J Super Hercules",
    tailNumber: "KC382",
    homeBase: "Hindon AFS",
    pilotInCommand: "Sqn Ldr Priya Sharma",
    coPilotOrWso: "Flt Lt Rohit Varma (Co-Pilot)",
    crewDutyRemainingHours: 2.8,
    crewDutyLimitHours: 10.0,
    crewFatigueScore: 0.22,
    payloadDescription: "14,500 kg High-Altitude Combat Rations + Cold-Chain Blood Plasma Units",
    payloadWeightKg: 14500,
    isColdChainActive: true,
    isHazardousClass1: false,
    originBase: "Hindon AFS",
    transitCorridor: "Corridor Charlie-7 (Direct Low Valley FL220, 640 km)",
    destinationBase: "Nyoma Advanced Landing Ground (ALG)",
    departureTimeUtc: "10:30 UTC (T+00:30)",
    flightDurationMin: 75,
    estimatedArrivalUtc: "11:45 UTC (T+01:45)",
    hardDeadlineUtc: "12:30 UTC",
    safetyMarginMin: 45,
    status: "ON SCHEDULE",
    delayDeltaMin: 0,
    solverVerification: "VERIFIED OPTIMAL (CP-SAT)",
  },
  {
    id: "MSN-DEF-301",
    callsign: "LIGHTNING-01",
    missionName: "Base Quick-Reaction Intercept Alert",
    priority: "P-4 Combat Air Patrol",
    airframeId: "TEJ-LA008",
    airframeModel: "HAL Tejas Mk-1 FOC",
    tailNumber: "LA008",
    homeBase: "Sulur AFS",
    pilotInCommand: "Sqn Ldr Kabir Bedi",
    coPilotOrWso: "Single Seat (Uttam AESA Radar)",
    crewDutyRemainingHours: 4.5,
    crewDutyLimitHours: 8.0,
    crewFatigueScore: 0.08,
    payloadDescription: "2x Astra Mk-1 BVR + 2x ASRAAM + 2x 1200L Drop Fuel Tanks",
    payloadWeightKg: 4800,
    isColdChainActive: false,
    isHazardousClass1: true,
    originBase: "Sulur AFS",
    transitCorridor: "Coastal Intercept Vector (FL240, 450 km)",
    destinationBase: "Thanjavur Forward Base",
    departureTimeUtc: "11:00 UTC (T+01:00)",
    flightDurationMin: 50,
    estimatedArrivalUtc: "11:50 UTC (T+01:50)",
    hardDeadlineUtc: "12:30 UTC",
    safetyMarginMin: 40,
    status: "ALERT-5 STANDBY",
    delayDeltaMin: 0,
    solverVerification: "VERIFIED OPTIMAL (CP-SAT)",
  },
  {
    id: "MSN-AAR-202",
    callsign: "VALIANT-TANKER",
    missionName: "Airborne Tanker Orbit Replenishment",
    priority: "P-5 Strategic Support",
    airframeId: "IL78-RK3451",
    airframeModel: "Ilyushin Il-78 MKI Tanker",
    tailNumber: "RK3451",
    homeBase: "Agra AFS",
    pilotInCommand: "Gp Capt S. Bannerjee",
    coPilotOrWso: "Sqn Ldr Manoj Kulkarni + MWO D. Roy (Eng)",
    crewDutyRemainingHours: 5.2,
    crewDutyLimitHours: 12.0,
    crewFatigueScore: 0.15,
    payloadDescription: "110,000 kg Transferable Aviation Turbine Fuel (ATF JP-8)",
    payloadWeightKg: 110000,
    isColdChainActive: false,
    isHazardousClass1: true,
    originBase: "Agra AFS",
    transitCorridor: "Refueling Corridor Tango (FL260 Orbit, 900 km)",
    destinationBase: "Orbit Station Charlie",
    departureTimeUtc: "09:30 UTC (T-00:30)",
    flightDurationMin: 70,
    estimatedArrivalUtc: "10:40 UTC (On Orbit)",
    hardDeadlineUtc: "14:00 UTC",
    safetyMarginMin: 200,
    status: "IN-FLIGHT",
    delayDeltaMin: 0,
    solverVerification: "VERIFIED OPTIMAL (CP-SAT)",
  },
  {
    id: "MSN-ISR-001",
    callsign: "NETRA-EYE-1",
    missionName: "Airborne Early Warning & Battle Direction",
    priority: "P-5 Strategic Support",
    airframeId: "EMB-AW145",
    airframeModel: "Embraer Netra AEW&C",
    tailNumber: "AW145",
    homeBase: "Bhatinda AFS",
    pilotInCommand: "Wg Cdr Ananya Sen",
    coPilotOrWso: "4x Tactical Air Traffic Radar Controllers",
    crewDutyRemainingHours: 6.0,
    crewDutyLimitHours: 10.0,
    crewFatigueScore: 0.10,
    payloadDescription: "AESA Primary Radar 240° Beam + IFF Mark XII + EW Jamming Pods",
    payloadWeightKg: 8500,
    isColdChainActive: false,
    isHazardousClass1: false,
    originBase: "Bhatinda AFS",
    transitCorridor: "Northern Surveillance Vector (FL300, 550 km)",
    destinationBase: "Airborne Orbit Bravo",
    departureTimeUtc: "09:00 UTC (T-01:00)",
    flightDurationMin: 45,
    estimatedArrivalUtc: "09:45 UTC (On Orbit)",
    hardDeadlineUtc: "15:00 UTC",
    safetyMarginMin: 315,
    status: "IN-FLIGHT",
    delayDeltaMin: 0,
    solverVerification: "VERIFIED OPTIMAL (CP-SAT)",
  },
];


