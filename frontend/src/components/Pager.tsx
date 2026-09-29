"use client";

import { useEffect } from "react";

/** "Showing 101–200 of 12,674" with Previous / Next. A page that no longer
 * exists (e.g. an old link, after rows went away) moves to the last page. */
export default function Pager({
  offset,
  limit,
  total,
  onChange,
}: {
  offset: number;
  limit: number;
  total: number;
  onChange(offset: number): void;
}) {
  const pastTheEnd = offset > 0 && offset >= total;
  useEffect(() => {
    if (pastTheEnd) onChange(total > 0 ? Math.floor((total - 1) / limit) * limit : 0);
  }, [pastTheEnd, total, limit, onChange]);

  if (pastTheEnd || (total <= limit && offset === 0)) return null;
  const last = Math.min(offset + limit, total);
  const button =
    "rounded-md border border-white/15 px-3 py-1 text-sm text-white/80 hover:border-cyan hover:text-cyan disabled:opacity-40 disabled:hover:border-white/15 disabled:hover:text-white/80";

  return (
    <nav aria-label="Pages" className="flex items-center justify-between gap-4 text-sm text-white/60">
      <span>
        Showing {total ? (offset + 1).toLocaleString("en-US") : 0}–{last.toLocaleString("en-US")} of{" "}
        {total.toLocaleString("en-US")}
      </span>
      <span className="flex gap-2">
        <button type="button" className={button} disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>
          Previous
        </button>
        <button type="button" className={button} disabled={last >= total} onClick={() => onChange(offset + limit)}>
          Next
        </button>
      </span>
    </nav>
  );
}
