"use client";

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

const inputCls =
  "w-full rounded-[3px] border border-line bg-white px-2.5 py-1.5 text-sm text-ink num focus:border-quantum focus:outline-none";

export function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${inputCls} ${props.className ?? ""}`} />;
}

export function NumberInput({ value, onChange, min = 0, step = 1, ...rest }:
  { value: number; onChange: (v: number) => void; min?: number; step?: number } &
  Omit<React.InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "min" | "step">) {
  return (
    <input type="number" inputMode="numeric" value={Number.isFinite(value) ? value : ""} min={min} step={step}
      onChange={(e) => onChange(e.target.value === "" ? 0 : Number(e.target.value))}
      className={inputCls} {...rest} />
  );
}

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

export function Button({ variant = "secondary", className = "", ...props }:
  React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "ghost" }) {
  const styles = {
    primary: "bg-ink text-white hover:bg-ink/90 border-ink",
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
