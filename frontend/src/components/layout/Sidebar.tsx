"use client";
import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Wind,
  LayoutGrid,
  Database,
  Network,
  ShieldCheck,
  ChartNoAxesCombined,
  SlidersHorizontal,
  GitBranch,
  Box,
  Activity,
  ClipboardCheck,
  Clock3,
  ChartColumn,
  Menu,
  X,
} from "lucide-react";
import { NAVIGATION_ITEMS } from "@/lib/constants";
const icons = {
  LayoutDashboard: LayoutGrid,
  Database,
  Network,
  ShieldCheck,
  ChartNoAxesCombined,
  SlidersHorizontal,
  GitBranch,
  Box,
  Activity,
  ClipboardCheck,
  Clock3,
  ChartColumn,
};
export function Sidebar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const items = NAVIGATION_ITEMS.flatMap((group) => group.items);
  const active = [...items]
    .sort((a, b) => b.href.length - a.href.length)
    .find(
      (item) =>
        pathname === item.href ||
        (item.href !== "/" && pathname.startsWith(item.href + "/")),
    )?.href;
  return (
    <>
      <button
        className="mobile-nav-toggle"
        aria-label="Toggle navigation"
        aria-expanded={open}
        aria-controls="main-sidebar"
        onClick={() => setOpen(!open)}
      >
        {open ? <X size={20} /> : <Menu size={20} />}
      </button>
      {open && (
        <button
          className="sidebar-backdrop"
          aria-label="Close navigation"
          onClick={() => setOpen(false)}
        />
      )}
      <aside
        id="main-sidebar"
        className={`app-sidebar ${open ? "is-open" : ""}`}
        onKeyDown={(e) => {
          if (e.key === "Escape") setOpen(false);
        }}
      >
        <Link href="/" className="brand" onClick={() => setOpen(false)}>
          <Wind size={31} strokeWidth={2.4} />
          <span>
            AERONIQ
            <span className="brand-caption">DECISION INTELLIGENCE</span>
          </span>
        </Link>
        <nav aria-label="Main navigation" className="sidebar-links">
          {items.map((item) => {
            const Icon = icons[item.icon as keyof typeof icons];
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active === item.href ? "page" : undefined}
                className={`sidebar-link ${active === item.href ? "active" : ""}`}
                onClick={() => setOpen(false)}
              >
                <Icon size={20} strokeWidth={1.6} />
                <span>
                  {item.href === "/"
                    ? "Dashboard"
                    : item.label.replace(/ \(F\d+\)/, "")}
                </span>
                {item.href === "/stress-lab" && (
                  <span className="nav-tag">LAB</span>
                )}
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-bottom">
          <span className="connection-dot" /> Operations workspace
        </div>
      </aside>
    </>
  );
}
