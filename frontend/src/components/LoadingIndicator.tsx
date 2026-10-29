/** Indeterminate progress: no fabricated percentage; respects reduced motion. */
export default function LoadingIndicator({ label, detail }: { label: string; detail?: string }) {
  return <div role="status" className="flex items-start gap-3 text-sm text-white/80">
    <span aria-hidden="true" className="mt-0.5 h-5 w-5 shrink-0 rounded-full border-2 border-white/20 border-t-cyan motion-safe:animate-spin" />
    <div className="min-w-0 [overflow-wrap:anywhere]"><p className="font-medium">{label}</p>{detail && <p className="mt-1 text-xs text-white/60">{detail}</p>}</div>
  </div>;
}
