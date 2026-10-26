"use client";

import { useEffect, useState } from "react";

export function findingHref(orgId: string, id: string) {
  return `/findings/lookup?${new URLSearchParams({ org: orgId, finding_id: id })}`;
}

/** IDs are supplementary identifiers, never substitutes for permission checks. */
export default function FindingReference({ orgId, id, copy = false }: { orgId: string; id: string; copy?: boolean }) {
  const [feedback, setFeedback] = useState<{ message: string; success: boolean } | null>(null);
  useEffect(() => {
    if (!feedback?.success) return;
    const timer = window.setTimeout(() => setFeedback(null), 3000);
    return () => window.clearTimeout(timer);
  }, [feedback]);
  async function copyId() {
    try { await navigator.clipboard.writeText(id); setFeedback({ message: "Finding ID copied.", success: true }); }
    catch { setFeedback({ message: "Could not copy. Select and copy the Finding ID manually.", success: false }); }
  }
  return <span className="inline-flex max-w-full flex-wrap items-center gap-2 text-xs">
    <a href={findingHref(orgId, id)} className="break-all text-cyan underline" aria-label={`Find finding ${id}`}>{id}</a>
    {copy && <button type="button" onClick={copyId} className="text-cyan underline" aria-label={`Copy finding ID ${id}`}>Copy ID</button>}
    {feedback && <span role="status">{feedback.message}</span>}
  </span>;
}
