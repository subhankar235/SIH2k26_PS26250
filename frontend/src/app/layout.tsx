import type { Metadata } from 'next';
import './globals.css';
import { Sidebar, Navbar } from '@/components/layout';

export const metadata: Metadata = {
  title: 'AIR POWER — Decision Intelligence',
  description: 'Operational decision intelligence, evidence autopsy, and grid resilience verification platform.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-slate-950 text-slate-100 min-h-screen flex">
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0 lg:pl-64">
          <Navbar />
          <main className="flex-1 p-4 md:p-6 lg:p-8 max-w-[1600px] w-full mx-auto">
            {children}
          </main>
          <footer className="border-t border-slate-800/80 px-6 py-4 text-xs text-slate-500 flex flex-col sm:flex-row items-center justify-between gap-2">
            <div>
              AIR POWER · Decision Intelligence Platform · Synthetic Operations Environment
            </div>
            <div className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              <span>All deterministic verification engines active</span>
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}
