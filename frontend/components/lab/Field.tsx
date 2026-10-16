"use client";
// WHAT THIS FILE IS FOR: the shared building blocks for forms in the Lab.
// Text boxes, number boxes, drop down lists, sliders and buttons all live here,
// so every Lab panel looks and behaves the same way.

// Wraps any form control with a label above it and an optional help note below.
/** Small labelled form controls shared by the Lab panels. */
export function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-[13px] font-medium text-ink">{label}</span>
      <div className="mt-1">{children}</div>
      {hint && <span className="mt-1 block text-xs text-ink-soft">{hint}</span>}
    </label>
  );
}

// The common look shared by all input boxes: thin border, white fill, purple outline when in focus.
const inputCls =
  "w-full rounded-[3px] border border-line bg-white px-2.5 py-1.5 text-sm text-ink num focus:border-quantum focus:outline-none";

// A plain text box with the shared look; it passes every setting straight through.
export function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${inputCls} ${props.className ?? ""}`} />;
}

// A box for whole numbers such as head counts. Clearing it counts as zero.
export function NumberInput({ value, onChange, min = 0, step = 1, ...rest }:
  { value: number; onChange: (v: number) => void; min?: number; step?: number } &
  Omit<React.InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "min" | "step">) {
  return (
    <input type="number" inputMode="numeric" value={Number.isFinite(value) ? value : ""} min={min} step={step}
      onChange={(e) => onChange(e.target.value === "" ? 0 : Number(e.target.value))}
      className={inputCls} {...rest} />
  );
}

// Used where a blank has its own meaning, such as "work out the travel time for me".
/** A number box that can be left empty, meaning "no value" (null). */
export function OptionalNumberInput({ value, onChange, placeholder, min = 0, step = 1 }:
  { value: number | null; onChange: (v: number | null) => void; placeholder?: string; min?: number; step?: number }) {
  return (
    <input type="number" inputMode="decimal" value={value ?? ""} min={min} step={step} placeholder={placeholder}
      onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
      className={`${inputCls} placeholder:text-ink-soft/70`} />
  );
}

// A drop down list. It hands back a number or text, matching the kind of value it was given.
export function Select<T extends string | number>({ value, onChange, options, disabled }:
  { value: T; onChange: (v: T) => void; options: { value: T; label: string }[]; disabled?: boolean }) {
  return (
    <select value={value} disabled={disabled}
      onChange={(e) => {
        const raw = e.target.value;
        onChange((typeof value === "number" ? Number(raw) : raw) as T);
      }}
      className={`${inputCls} disabled:opacity-50`}>
      {options.map((o) => <option key={String(o.value)} value={o.value}>{o.label}</option>)}
    </select>
  );
}

// A sliding control with the current value printed beside it, optionally formatted.
export function Slider({ value, onChange, min, max, step, format }:
  { value: number; onChange: (v: number) => void; min: number; max: number; step: number; format?: (v: number) => string }) {
  return (
    <div className="flex items-center gap-3">
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))} className="flex-1 accent-quantum" />
      <span className="num w-12 text-right text-sm">{format ? format(value) : value}</span>
    </div>
  );
}

// A button in one of several colour styles: main action, warning, green go, plain or faint.
// Disabled buttons fade out and show a "not allowed" pointer.
export function Button({ variant = "secondary", className = "", ...props }:
  React.ComponentProps<"button"> & { variant?: "primary" | "secondary" | "danger" | "destructive" | "ghost" | "green" }) {
  const styles = {
    primary: "bg-ink text-white hover:bg-ink/90 border-ink",
    destructive: "bg-wine text-white hover:bg-wine/90 border-wine",
    green: "bg-exit text-white hover:bg-exit/90 border-exit",
    secondary: "bg-white text-ink border-line hover:border-ink/50",
    danger: "bg-white text-wine border-line hover:border-wine",
    ghost: "bg-transparent text-ink-soft border-transparent hover:text-ink",
  }[variant];
  return (
    <button {...props}
      className={`inline-flex items-center justify-center gap-1.5 rounded-[3px] border px-3 py-1.5 text-sm font-medium
        transition-colors disabled:cursor-not-allowed disabled:opacity-45 ${styles} ${className}`} />
  );
}
