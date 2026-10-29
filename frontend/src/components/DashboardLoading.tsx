import LoadingIndicator from "@/components/LoadingIndicator";
import { DOMAIN_LABELS, DOMAIN_ORDER } from "@/lib/domain";

/** Preserve the Dashboard layout without suggesting that pending scores are zero. */
export default function DashboardLoading({ checking = false }: { checking?: boolean }) {
  const placeholder = "max-w-full rounded bg-white/10 motion-safe:animate-pulse";
  return <div className="space-y-8">
    <LoadingIndicator label={checking ? "Checking scoring settings…" : "Loading dashboard…"}
      detail="Preparing current scores and inventory counts. Large inventories may take a few seconds." />
    <div aria-hidden="true" className="space-y-8">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="min-h-44 rounded-xl bg-navy-cyan-gradient p-4 sm:p-6 lg:col-span-2">
          <p className="text-sm text-white/80">Overall Resilience Score</p><div className={`${placeholder} mt-4 h-12 w-24`} /><div className={`${placeholder} mt-3 h-4 w-32`} />
        </div>
        <div className="min-h-44 space-y-3 rounded-xl border border-white/10 bg-white/5 p-4 sm:p-6">
          <div className={`${placeholder} h-4 w-2/3`} />{[0, 1, 2, 3].map(i => <div key={i} className={`${placeholder} h-4 w-full`} />)}
        </div>
      </div>
      <section><h2 className="mb-3 text-lg font-medium text-white">Per-domain scores</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 lg:grid-cols-4">{DOMAIN_ORDER.map(domain => <div key={domain} className="rounded-xl border border-white/10 bg-white/5 p-5">
          <p className="text-sm text-white/60">{DOMAIN_LABELS[domain]}</p><div className={`${placeholder} mt-4 h-8 w-16`} />
        </div>)}</div>
      </section>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">{["Top issues", "Recent uploads"].map(title => <section key={title}>
        <h2 className="mb-3 text-lg font-medium text-white">{title}</h2><div className={`${placeholder} h-24 w-full`} />
      </section>)}</div>
    </div>
  </div>;
}
