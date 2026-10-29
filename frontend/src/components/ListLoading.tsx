import LoadingIndicator from "@/components/LoadingIndicator";

/** Initial list placeholder; refreshes keep the previous rows visible. */
export default function ListLoading({ label, initial }: { label: string; initial: boolean }) {
  return <div className="min-w-0 space-y-4">
    <LoadingIndicator label={`${initial ? "Loading" : "Updating"} ${label}…`}
      detail={initial ? "Preparing the current list and counts. Large inventories may take a few seconds." : "Fetching results for the current filters. Previous results remain visible until loading finishes."} />
    {initial && <div aria-hidden="true" className="overflow-hidden rounded-xl border border-white/10 bg-white/5">
      <div className="h-12 border-b border-white/10 bg-white/5" />
      {[0, 1, 2, 3, 4].map(row => <div key={row} className="grid min-w-0 grid-cols-3 gap-4 border-b border-white/5 p-4">
        {[0, 1, 2].map(column => <div key={column} className="h-4 min-w-0 rounded bg-white/10 motion-safe:animate-pulse" />)}
      </div>)}
    </div>}
  </div>;
}
