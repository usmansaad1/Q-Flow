"use client";

// WHAT THIS FILE IS FOR: a friendly "Are you sure?" pop up box used across the website.
// Pages show it before deleting or discarding something, instead of the browser's plain box.

import { useCallback, useEffect, useId, useRef, useState } from "react";

import { Button } from "@/components/lab/Field";

// What a page can set on the box: the question, extra detail, and the button labels.
export interface ConfirmOptions {
  title: string;
  message?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Red confirm button, for actions that delete or discard something. */
  danger?: boolean;
}

// The question currently on screen, plus the way to hand the user's answer back to the page.
type Pending = ConfirmOptions & { resolve: (ok: boolean) => void };

/**
 * An in app replacement for the browser's confirm() box.
 *   const [ask, confirmDialog] = useConfirm();
 *   if (!(await ask({ title: "Delete run #3?", danger: true }))) return;
 *   ...and render {confirmDialog} once in the page.
 */
// A React hook (a reusable piece of page logic) that gives a page an "ask" function and the box to show.
// The page waits on "ask", which answers yes or no once the user clicks a button.
export function useConfirm() {
  const [pending, setPending] = useState<Pending | null>(null);
  const ask = useCallback(
    (options: ConfirmOptions) => new Promise<boolean>((resolve) => setPending({ ...options, resolve })),
    [],
  );
  // Passes the answer back to the waiting page and hides the box.
  const close = (ok: boolean) => {
    pending?.resolve(ok);
    setPending(null);
  };
  const dialog = pending ? <ConfirmDialog {...pending} onClose={close} /> : null;
  return [ask, dialog] as const;
}

// The box itself: a dimmed backdrop, the question, and Cancel and Confirm buttons.
// Pressing Escape or clicking outside the box counts as Cancel.
function ConfirmDialog({ title, message, confirmLabel = "Confirm", cancelLabel = "Cancel", danger, onClose }:
  ConfirmOptions & { onClose: (ok: boolean) => void }) {
  const titleId = useId();
  const messageId = useId();
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    // Cancel has focus first, so pressing Enter by habit never deletes anything.
    cancelRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // The dimmed backdrop covers the page; the white card in the middle holds the question.
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 px-4"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(false); }}>
      <div role="alertdialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={message ? messageId : undefined}
        className="w-full max-w-[440px] rounded-[4px] border border-line bg-panel p-5 shadow-lg">
        <h2 id={titleId} className="font-display text-lg font-bold">{title}</h2>
        {message && <p id={messageId} className="mt-2 text-sm text-ink-soft">{message}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <Button ref={cancelRef} onClick={() => onClose(false)}>{cancelLabel}</Button>
          <Button variant={danger ? "destructive" : "primary"} onClick={() => onClose(true)}>{confirmLabel}</Button>
        </div>
      </div>
    </div>
  );
}
