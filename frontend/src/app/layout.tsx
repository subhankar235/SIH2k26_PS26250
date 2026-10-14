import { DataModeBoundary } from "@/components/layout/DataModeBoundary";
import type { Metadata } from "next";
import "./globals.css";
import { Sidebar, Navbar } from "@/components/layout";
export const metadata: Metadata = {
  title: "AERONIQ | Decision Intelligence",
  description:
    "Evidence, planning, and operational intelligence in one workspace.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <a href="#main-content" className="skip-link">
          Skip to content
        </a>
        <Sidebar />
        <div className="app-shell">
          <Navbar />
          <main id="main-content" tabIndex={-1} className="app-content">
            <DataModeBoundary>{children}</DataModeBoundary>
          </main>
          <footer className="app-footer">
            <span>AERONIQ &middot; Decision intelligence</span>
            <span>Every decision. Clear evidence.</span>
          </footer>
        </div>
      </body>
    </html>
  );
}
