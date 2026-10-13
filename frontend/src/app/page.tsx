type Metric = {
  label: string;
  value: string;
  detail: string;
  tone: "green" | "blue" | "amber" | "violet";
};

const metrics: Metric[] = [
  { label: "Assets online", value: "119 / 128", detail: "92.9% fleet availability", tone: "green" },
  { label: "Active alerts", value: "03", detail: "1 requires attention", tone: "amber" },
  { label: "Renewable share", value: "42.0%", detail: "+4.8% vs. last week", tone: "blue" },
  { label: "Reserve margin", value: "16.0%", detail: "Target: 15.0%", tone: "violet" },
];

const alerts = [
  { severity: "Critical", title: "North Ridge substation", detail: "Transformer temperature above operating threshold", time: "4 min ago" },
  { severity: "Warning", title: "East solar cluster", detail: "Output variance detected against day-ahead forecast", time: "18 min ago" },
  { severity: "Warning", title: "Line 08 · Central region", detail: "Scheduled maintenance window begins in 42 minutes", time: "32 min ago" },
];

export default function Home() {
  return (
    <main className="shell">
      <aside className="sidebar">
        <a className="brand" href="#overview"><span className="brand-mark">A</span><span>AIR<span className="brand-light">POWER</span></span></a>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          <a className="nav-item active" href="#overview"><span>◫</span> Overview</a>
          <a className="nav-item" href="#grid"><span>⌁</span> Grid assets</a>
          <a className="nav-item" href="#alerts"><span>◉</span> Alerts <span className="nav-count">3</span></a>
          <a className="nav-item" href="#forecasts"><span>↗</span> Forecasts</a>
          <a className="nav-item" href="#dispatch"><span>⌘</span> Dispatch plans</a>
        </nav>
        <div className="sidebar-bottom"><div className="status-dot" /> All systems operational <small>Platform status</small></div>
      </aside>

      <section className="main-panel" id="overview">
        <header className="topbar"><div><span className="eyebrow">MONDAY, OCTOBER 13, 2026</span><h1>Grid overview</h1></div><div className="topbar-right"><span className="live"><i /> LIVE DATA</span><button className="profile" aria-label="User profile">OP</button></div></header>
        <div className="content">
          <section className="welcome-row"><div><h2>Good morning, Operator</h2><p>Here&apos;s the latest status across your power network.</p></div><button className="outline-button">⌄ &nbsp; All regions</button></section>

          <section className="metric-grid" aria-label="Grid key performance indicators">
            {metrics.map((metric) => <article className="metric-card" key={metric.label}><div className="metric-top"><span>{metric.label}</span><span className={`metric-icon ${metric.tone}`}>↗</span></div><strong>{metric.value}</strong><small>{metric.detail}</small></article>)}
          </section>

          <section className="middle-grid">
            <article className="panel chart-panel" id="grid"><div className="panel-heading"><div><span className="eyebrow">NETWORK PERFORMANCE</span><h3>Demand &amp; generation</h3></div><button className="period-button">Last 24 hours　⌄</button></div><div className="chart-legend"><span><i className="legend-demand" /> Demand</span><span><i className="legend-generation" /> Generation</span></div><div className="chart-wrap"><div className="y-labels"><span>2,000</span><span>1,500</span><span>1,000</span><span>500</span><span>0 MW</span></div><div className="chart"><div className="gridline g1"/><div className="gridline g2"/><div className="gridline g3"/><div className="gridline g4"/><svg viewBox="0 0 700 210" preserveAspectRatio="none" role="img" aria-label="Demand and generation trend over the last 24 hours"><defs><linearGradient id="area" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#328b76" stopOpacity=".18"/><stop offset="100%" stopColor="#328b76" stopOpacity="0"/></linearGradient></defs><path d="M0 132 C35 120 42 142 75 128 S125 99 150 112 S195 132 225 105 S270 81 300 96 S340 117 375 90 S425 70 450 88 S500 112 525 79 S570 54 600 68 S660 82 700 43 L700 210 L0 210Z" fill="url(#area)"/><path d="M0 132 C35 120 42 142 75 128 S125 99 150 112 S195 132 225 105 S270 81 300 96 S340 117 375 90 S425 70 450 88 S500 112 525 79 S570 54 600 68 S660 82 700 43" fill="none" stroke="#328b76" strokeWidth="3"/><path d="M0 161 C40 153 52 168 82 156 S128 139 158 147 S205 163 232 136 S272 121 304 132 S345 146 380 121 S425 103 456 117 S500 136 532 109 S575 91 608 102 S663 112 700 77" fill="none" stroke="#8da5bb" strokeWidth="2.5" strokeDasharray="5 5"/></svg><div className="x-labels"><span>00:00</span><span>04:00</span><span>08:00</span><span>12:00</span><span>16:00</span><span>20:00</span><span>24:00</span></div></div></div></article>
            <article className="panel region-panel"><div className="panel-heading"><div><span className="eyebrow">NETWORK HEALTH</span><h3>By region</h3></div><a className="text-link" href="#grid">View all →</a></div><div className="region-list"><div className="region-row"><span className="region-badge green-bg">N</span><div className="region-info"><strong>North</strong><small>42 assets</small></div><span className="region-health"><i className="status-dot"/> 98%</span></div><div className="region-row"><span className="region-badge blue-bg">C</span><div className="region-info"><strong>Central</strong><small>36 assets</small></div><span className="region-health"><i className="status-dot"/> 94%</span></div><div className="region-row"><span className="region-badge amber-bg">E</span><div className="region-info"><strong>East</strong><small>28 assets</small></div><span className="region-health warning"><i className="status-dot"/> 86%</span></div><div className="region-row"><span className="region-badge violet-bg">S</span><div className="region-info"><strong>South</strong><small>22 assets</small></div><span className="region-health"><i className="status-dot"/> 96%</span></div></div></article>
          </section>

          <section className="panel alerts-panel" id="alerts"><div className="panel-heading"><div><span className="eyebrow">NEEDS ATTENTION</span><h3>Recent alerts <span className="alert-pill">3</span></h3></div><a className="text-link" href="#alerts">View all alerts →</a></div><div className="alert-list">{alerts.map((alert) => <article className="alert-row" key={alert.title}><span className={`severity ${alert.severity.toLowerCase()}`}><i />{alert.severity}</span><div className="alert-copy"><strong>{alert.title}</strong><small>{alert.detail}</small></div><time>{alert.time}</time><span className="chevron">›</span></article>)}</div></section>
          <footer>Air Power Operations Platform <span>API connection · Demo data</span></footer>
        </div>
      </section>
    </main>
  );
}
