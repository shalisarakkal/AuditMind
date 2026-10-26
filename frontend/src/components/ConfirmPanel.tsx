"use client";

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
      className={`flex flex-wrap items-center gap-2 rounded-lg border p-3 text-sm ${
        danger ? "border-red-400/30 bg-red-400/5" : "border-cyan/30 bg-cyan/5"
      }`}
    >
      <div className="text-white">{message}</div>
      <button
        type="button"
        disabled={busy}
        onClick={onConfirm}
        className={`rounded-md px-3 py-1 font-medium text-navy disabled:opacity-60 ${danger ? "bg-red-400/80" : "bg-cyan"}`}
      >
        {confirmLabel}
      </button>
      <button type="button" data-confirm-cancel disabled={busy} onClick={onCancel} className="text-xs text-white/60 hover:text-white disabled:opacity-50">
        Cancel
      </button>
    </div>
  );
}
