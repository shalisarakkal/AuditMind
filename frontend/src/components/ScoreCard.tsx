type ScoreCardProps = {
  label: string;
  score: number;
  tier: "low" | "medium" | "high" | "critical";
};

const TIER_COLORS: Record<ScoreCardProps["tier"], string> = {
  low: "text-emerald-400",
  medium: "text-yellow-400",
  high: "text-orange-400",
  critical: "text-red-400",
};

export default function ScoreCard({ label, score, tier }: ScoreCardProps) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-5">
      <p className="text-sm text-white/60">{label}</p>
      <p className={`mt-2 text-3xl font-bold ${TIER_COLORS[tier]}`}>{score}</p>
      <p className={`mt-1 text-xs uppercase tracking-wide ${TIER_COLORS[tier]}`}>{tier}</p>
    </div>
  );
}
