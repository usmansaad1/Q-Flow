import { LOAD_BANDS } from "@/lib/format";

export default function LoadLegend({ className = "" }: { className?: string }) {
  return (
    <div className={`flex flex-wrap items-center gap-x-3 gap-y-1 text-[11.5px] text-ink-soft ${className}`}>
      <span className="font-medium text-ink">Load on route or exit</span>
      {LOAD_BANDS.slice(1).map((b) => (
        <span key={b.label} className="flex items-center gap-1.5">
          <span className="inline-block h-[5px] w-5 rounded-full" style={{ background: b.color }} />
          {b.label}
        </span>
      ))}
    </div>
  );
}
