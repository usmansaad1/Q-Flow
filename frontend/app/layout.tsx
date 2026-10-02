import type { Metadata } from "next";
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-sans-condensed/600.css";
import "@fontsource/ibm-plex-sans-condensed/700.css";
import "@xyflow/react/dist/style.css";
import "./globals.css";

import SiteHeader from "@/components/SiteHeader";

export const metadata: Metadata = {
  title: "Q-Flow: Benchmarking quantum optimisation for crowd flow planning",
  description:
    "Model a venue, route its crowd to the exits, and compare classical optimisation with QAOA on ideal, noisy and real quantum hardware.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <SiteHeader />
        {children}
      </body>
    </html>
  );
}
