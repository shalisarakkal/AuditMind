"use client";

import { useEffect, useId, useRef } from "react";

/** A pending finding action owns interaction until confirmed/cancelled. */
export default function FindingActionDialog({ title, orgName, onClose, children }: { title: string; orgName: string; onClose(): void; children: React.ReactNode }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const heading = useId();
  useEffect(() => {
    const node = dialog.current!;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    node.showModal();
    node.querySelector<HTMLButtonElement>('[data-confirm-cancel]')?.focus();
    return () => { node.close(); if (previous?.isConnected) previous.focus(); };
  }, []);
  return <dialog ref={dialog} aria-labelledby={heading} aria-modal="true" onCancel={event => {
    event.preventDefault();
    if (!dialog.current?.querySelector('[aria-busy="true"]')) onClose();
  }} className="m-auto max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] max-w-2xl overflow-y-auto rounded-xl border border-white/20 bg-navy p-5 text-white shadow-xl backdrop:bg-black/75">
    <h2 id={heading} className="text-lg font-semibold">{title}</h2>
    <p className="mb-4 text-sm text-white/70">{orgName}</p>
    {children}
  </dialog>;
}
