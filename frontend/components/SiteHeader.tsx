"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Overview" },
  { href: "/lab", label: "Venue lab" },
  { href: "/experiments", label: "Experiments" },
];

export default function SiteHeader() {
  const path = usePathname();
  return (
    <header className="border-b border-line bg-panel">
      <div className="mx-auto flex h-14 max-w-[1440px] items-center gap-8 px-5">
        <Link href="/" className="flex items-center" aria-label="Q-Flow home">
          {/* Styled after an exit sign: white condensed lettering on safety green. */}
          <span className="rounded-[2px] bg-exit px-2.5 py-0.5 font-display text-lg font-bold tracking-wide text-white">
            Q-Flow
          </span>
        </Link>
        <nav className="flex h-full items-stretch gap-6 text-sm">
          {LINKS.map((l) => {
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
