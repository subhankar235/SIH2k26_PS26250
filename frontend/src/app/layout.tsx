import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "Air Power | Grid Operations",
  description: "Grid resilience and energy operations dashboard",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
