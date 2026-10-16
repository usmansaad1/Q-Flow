"use client";
// WHAT THIS FILE IS FOR: the toolbar above the venue editor in the Lab.
// It lets users pick a venue, rename it, save it, add areas and exits,
// and use a "More" menu to download, open, reset or delete venues.

import { useEffect, useRef, useState } from "react";

import type { PresetInfo, SavedVenueSummary } from "@/lib/types";
import { Button, TextInput } from "./Field";

// Where the venue being edited came from: a built in example, one the user saved, or a brand new one.
export type VenueSource = { kind: "preset"; id: string } | { kind: "saved"; id: number } | { kind: "new" };

// Turns a venue source into one short text label, like "preset:stadium", for the drop down list.
export const sourceKey = (s: VenueSource) => (s.kind === "new" ? "new" : `${s.kind}:${s.id}`);

// Everything the toolbar needs: the venue lists, the current name and save state, and an action per button.
interface Props {
  presets: PresetInfo[];
  saved: SavedVenueSummary[];
  source: VenueSource;
  onPick: (s: VenueSource) => void;
  name: string;
  onName: (v: string) => void;
  status: "saved" | "unsaved" | "edited preset" | "new" | "unchanged preset";
  canSave: boolean;
  saveBlockedReason: string | null;
  saving: boolean;
  onSave: () => void;
  onSaveAsNew: () => void;
  onAddArea: () => void;
  onAddExit: () => void;
  onReset: () => void;
  onImport: (file: File) => void;
  onExport: () => void;
  onDelete: () => void;
}

// The small status message and its colour for each save state, shown beside the Save button.
const STATUS_TEXT: Record<Props["status"], { text: string; cls: string }> = {
  saved: { text: "Saved", cls: "text-exit" },
  unsaved: { text: "Unsaved changes", cls: "text-amber" },
  "edited preset": { text: "Edited preset, save to keep it", cls: "text-amber" },
  new: { text: "Not saved yet", cls: "text-ink-soft" },
  "unchanged preset": { text: "Preset venue", cls: "text-ink-soft" },
};

// Draws the toolbar. It also keeps track of whether the "More" menu is open.
export default function VenueBar(p: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLDetailsElement>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  // Close the venue menu when clicking anywhere else.
  useEffect(() => {
    if (!menuOpen) return;
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        menuRef.current.open = false;
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menuOpen]);

  // Closes the "More" menu first, then carries out the chosen menu action.
  const runMenu = (fn: () => void) => {
    if (menuRef.current) menuRef.current.open = false;
    setMenuOpen(false);
    fn();
  };

  const st = STATUS_TEXT[p.status];
  const isSaved = p.source.kind === "saved";

  return (
    <div className="flex flex-wrap items-center gap-2">
      {/* Venue picker: built in examples first, then the user's saved venues */}
      <select aria-label="Venue" value={sourceKey(p.source)}
        onChange={(e) => {
          const [kind, id] = e.target.value.split(":");
          p.onPick(kind === "preset" ? { kind: "preset", id } : kind === "saved" ? { kind: "saved", id: Number(id) } : { kind: "new" });
        }}
        className="w-64 rounded-[3px] border border-line bg-white px-2.5 py-1.5 text-sm text-ink focus:border-quantum focus:outline-none">
        {p.source.kind === "new" && <option value="new">Unsaved venue</option>}
        <optgroup label="Preset venues">
          {p.presets.map((v) => <option key={v.id} value={`preset:${v.id}`}>{v.name} ({v.num_qubits} qubits)</option>)}
        </optgroup>
        <optgroup label={p.saved.length ? "Your saved venues" : "Your saved venues (none yet)"}>
          {p.saved.map((v) => (
            <option key={v.id} value={`saved:${v.id}`}>{v.name}</option>
          ))}
        </optgroup>
      </select>

      {/* Venue name box, Save button and save status */}
      <div className="w-56"><TextInput aria-label="Venue name" value={p.name} onChange={(e) => p.onName(e.target.value)} /></div>

      <Button variant="primary" disabled={!p.canSave || p.saving} onClick={p.onSave}
        title={p.saveBlockedReason ?? (isSaved ? "Save changes to this venue" : "Save as a new venue")}>
        {p.saving ? "Saving…" : isSaved ? "Save" : "Save venue"}
      </Button>
      <span className={`text-xs ${st.cls}`} aria-live="polite">{st.text}</span>

      {/* Buttons to add new places to the map */}
      <span className="mx-1 h-6 w-px bg-line" />
      <Button onClick={p.onAddArea}>Add area</Button>
      <Button onClick={p.onAddExit}>Add exit</Button>

      {/* The "More" menu with less common actions */}
      <details ref={menuRef} className="relative" onToggle={(e) => setMenuOpen((e.target as HTMLDetailsElement).open)}>
        <summary className="cursor-pointer list-none rounded-[3px] border border-transparent px-3 py-1.5 text-sm font-medium text-ink-soft hover:text-ink [&::-webkit-details-marker]:hidden">
          More ▾
        </summary>
        <div className="absolute right-0 z-20 mt-1 w-56 rounded-[3px] border border-line bg-white py-1 text-sm shadow-[0_4px_16px_#15233F1A]">
          {isSaved && <MenuItem onClick={() => runMenu(p.onSaveAsNew)} disabled={!!p.saveBlockedReason}>Save as a new venue</MenuItem>}
          <MenuItem onClick={() => runMenu(p.onExport)} disabled={!!p.saveBlockedReason}>Download venue file (JSON)</MenuItem>
          <MenuItem onClick={() => runMenu(() => fileRef.current?.click())}>Open venue file…</MenuItem>
          <hr className="my-1 border-line" />
          {p.source.kind !== "new" && <MenuItem onClick={() => runMenu(p.onReset)}>Undo changes since loading</MenuItem>}
          {isSaved && <MenuItem onClick={() => runMenu(p.onDelete)} danger>Delete this saved venue</MenuItem>}
        </div>
      </details>
      {/* Hidden file picker, opened by "Open venue file" in the menu */}
      <input ref={fileRef} type="file" accept=".json,application/json" className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) p.onImport(f); e.target.value = ""; }} />
    </div>
  );
}

// One clickable line inside the "More" menu. Risky actions are shown in red.
function MenuItem({ children, onClick, disabled, danger }:
  { children: React.ReactNode; onClick: () => void; disabled?: boolean; danger?: boolean }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled}
      className={`block w-full px-3 py-1.5 text-left hover:bg-paper disabled:cursor-not-allowed disabled:opacity-45 ${danger ? "text-wine" : "text-ink"}`}>
      {children}
    </button>
  );
}
