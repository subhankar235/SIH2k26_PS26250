"use client";
import { useDataMode } from "@/lib/data-mode";
import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Search, Bell, MessageCircle, Settings2, X } from "lucide-react";
import { NAVIGATION_ITEMS } from "@/lib/constants";
export function Navbar() {
  const { mode, setMode, resetDemo } = useDataMode();
  const pathname = usePathname();
  const [query, setQuery] = useState("");
  const [settings, setSettings] = useState(false);
  const items = NAVIGATION_ITEMS.flatMap((group) => group.items);
  const active = [...items]
    .sort((a, b) => b.href.length - a.href.length)
    .find(
      (item) =>
        pathname === item.href ||
        (item.href !== "/" && pathname.startsWith(item.href + "/")),
    );
  const results = query.trim()
    ? items.filter((item) =>
        item.label.toLowerCase().includes(query.toLowerCase()),
      )
    : [];
  const Title = pathname === "/" ? "h1" : "div";
  return (
    <header className="app-navbar">
      <Title className="nav-page-title">
        {pathname === "/"
          ? "Dashboard"
          : (active?.label.replace(/ \(F\d+\)/, "") ?? "Dashboard")}
      </Title>
      <div className="navbar-tools">
        <select
          aria-label="Workspace data source"
          className="workspace-mode"
          value={mode}
          onChange={(e) => setMode(e.target.value as "demo" | "live")}
        >
          <option value="demo">Demo workspace</option>
          <option value="live">Live API</option>
        </select>
        <div className="route-search">
          <input
            aria-label="Search routes"
            placeholder="Search your workspace"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") setQuery("");
            }}
          />
          <Search size={18} />
          {query && (
            <div className="search-results">
              {results.length ? (
                results.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setQuery("")}
                  >
                    {item.label}
                  </Link>
                ))
              ) : (
                <p>No matching pages</p>
              )}
            </div>
          )}
        </div>
        <div className="quick-actions">
          <Link href="/approvals" aria-label="Approval queue">
            <Bell size={17} />
          </Link>
          <Link href="/explanations" aria-label="Agent explanations">
            <MessageCircle size={17} />
          </Link>
          <button
            aria-label="Workspace settings"
            aria-expanded={settings}
            onClick={() => setSettings(!settings)}
          >
            <Settings2 size={17} />
          </button>
        </div>
        <div className="profile-chip">
          <span className="profile-avatar">KD</span>
          <span>
            <strong>Kathakali Das</strong>
            <small>Analyst</small>
          </span>
        </div>
      </div>
      {settings && (
        <div className="workspace-popover">
          <button
            aria-label="Close settings"
            onClick={() => setSettings(false)}
          >
            <X size={16} />
          </button>
          <strong>Workspace settings</strong>
          <p>AERONIQ operations</p>
          <p>Demo actions are saved in this browser.</p>
          <button
            className="reset-demo"
            onClick={() => {
              resetDemo();
              setSettings(false);
            }}
          >
            Reset demo data
          </button>
          <Link href="/audit" onClick={() => setSettings(false)}>
            View workspace activity
          </Link>
        </div>
      )}
    </header>
  );
}
