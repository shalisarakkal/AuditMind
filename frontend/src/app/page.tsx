import ScoreCard from "@/components/ScoreCard";

const DOMAIN_SCORES: { label: string; score: number; tier: "low" | "medium" | "high" | "critical" }[] = [
  { label: "Identity & Access", score: 78, tier: "medium" },
  { label: "Network & Config", score: 85, tier: "low" },
  { label: "Vulnerability Mgmt", score: 52, tier: "high" },
  { label: "Backup & Recovery", score: 90, tier: "low" },
  { label: "Monitoring & Detection", score: 61, tier: "medium" },
  { label: "Incident Response", score: 45, tier: "high" },
  { label: "Compliance Alignment", score: 70, tier: "medium" },
];

export default function DashboardPage() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-white">Resilience Dashboard</h1>
        <p className="mt-1 text-sm text-white/60">
          Sample data shown below &mdash; connect the backend to replace with live scores.
        </p>
      </div>

      <div className="rounded-xl bg-navy-cyan-gradient p-6">
        <p className="text-sm text-white/80">Overall Resilience Score</p>
        <p className="mt-2 text-5xl font-bold text-white">70</p>
        <p className="mt-1 text-sm uppercase tracking-wide text-white/80">Medium risk tier</p>
      </div>

      <div>
        <h2 className="mb-3 text-lg font-medium text-white">Per-domain scores</h2>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {DOMAIN_SCORES.map((domain) => (
            <ScoreCard key={domain.label} {...domain} />
          ))}
        </div>
      </div>
    </div>
  );
}
