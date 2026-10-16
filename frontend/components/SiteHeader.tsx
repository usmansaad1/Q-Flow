"use client";
// WHAT THIS FILE IS FOR: the top bar shown on every page of the website.
// It holds the Q-Flow logo and the links to the main sections.

import Link from "next/link";
import { usePathname } from "next/navigation";

// The pages listed in the top menu, in the order they appear.
const LINKS = [
  { href: "/", label: "Overview" },
  { href: "/lab", label: "Venue lab" },
  { href: "/experiments", label: "Experiments" },
  { href: "/methodology", label: "Methodology" },
];

// Draws the header and underlines the link for the page the visitor is on now.
export default function SiteHeader() {
  const path = usePathname();
  return (
    <header className="border-b border-line bg-panel">
      <div className="mx-auto flex h-14 max-w-[1440px] items-center gap-4 px-4 sm:gap-8 sm:px-5">
        <Link href="/" className="flex shrink-0 items-center" aria-label="Q-Flow home">
          {/* Styled after an exit sign: white condensed lettering on safety green. */}
          <span className="rounded-[2px] bg-exit px-2.5 py-0.5 font-display text-lg font-bold tracking-wide text-white">
            Q-Flow
          </span>
        </Link>
        {/* Scrolls sideways on narrow phones instead of widening the page. */}
        <nav className="flex h-full min-w-0 items-stretch gap-4 overflow-x-auto whitespace-nowrap text-sm sm:gap-6">
          {LINKS.map((l) => {
            // The home link only counts as current on the home page itself; others match sub pages too.
            const active = l.href === "/" ? path === "/" : path.startsWith(l.href);
            return (
              <Link key={l.href} href={l.href}
                className={`flex items-center border-b-2 pt-0.5 ${active ? "border-ink font-semibold text-ink" : "border-transparent text-ink-soft hover:text-ink"}`}>
                {l.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
