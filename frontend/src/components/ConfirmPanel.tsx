"use client";
import { DIALOG_FOOTER, DIALOG_NEUTRAL, DIALOG_PRIMARY, DIALOG_DANGER } from "./DialogActions";

/** An inline "are you sure?" panel (the app avoids browser dialogs). `danger`
 * for what can't be undone. */
export default function ConfirmPanel({
  label,
  message,
  confirmLabel,
  onConfirm,
  onCancel,
  busy = false,
  danger = false,
}: {
  label: string;
  message: React.ReactNode;
  confirmLabel: string;
  onConfirm(): void;
  onCancel(): void;
  busy?: boolean;
  danger?: boolean;
}) {
  return (
    <div
      role="group"
      aria-busy={busy}
      aria-label={label}
      className={`rounded-lg border p-3 text-sm ${
        danger ? "border-red-400/30 bg-red-400/5" : "border-cyan/30 bg-cyan/5"
      }`}
    >
      <div className="text-white">{message}</div>
      <footer className={DIALOG_FOOTER}>
        <button type="button" data-confirm-cancel disabled={busy} onClick={onCancel} className={DIALOG_NEUTRAL}>Cancel</button>
        <button
          type="button"
          disabled={busy}
          onClick={onConfirm}
          className={danger ? DIALOG_DANGER : DIALOG_PRIMARY}
        >
          {confirmLabel}
        </button>
      </footer>
    </div>
  );
}
