export const APP_NAME = "AIR POWER";
export const APP_SUBTITLE = "DECISION INTELLIGENCE";

export const NAVIGATION_ITEMS = [
  { group: "PLATFORM OVERVIEW", items: [
    { href: "/", label: "Overview", icon: "LayoutDashboard" },
  ]},
  { group: "DATA INTELLIGENCE", items: [
    { href: "/ingestion", label: "Ingestion (F1)", icon: "Database" },
    { href: "/evidence", label: "Evidence (F2)", icon: "Network", count: 7 },
    { href: "/validity", label: "Decision Validity (F3)", icon: "ShieldCheck" },
  ]},
  { group: "PREDICTION & PLANNING", items: [
    { href: "/forecasts", label: "Forecasts (F4)", icon: "ChartNoAxesCombined" },
    { href: "/planning", label: "Planning (F5)", icon: "SlidersHorizontal" },
    { href: "/planning/compare", label: "Replanning Diff (F6)", icon: "GitBranch" },
  ]},
  { group: "EXPERIMENTATION", items: [
    { href: "/stress-lab", label: "Stress Lab (F7)", icon: "Box", badge: "LAB" },
    { href: "/explanations", label: "Agent Explanations (F8)", icon: "Activity" },
  ]},
  { group: "GOVERNANCE", items: [
    { href: "/approvals", label: "Approval Queue (F9)", icon: "ClipboardCheck" },
    { href: "/audit", label: "Audit Log (F9)", icon: "Clock3" },
    { href: "/benchmarks", label: "Benchmarks (F10)", icon: "ChartColumn" },
  ]},
];
