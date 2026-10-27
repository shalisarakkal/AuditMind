import { riskTierStyle } from "@/lib/domain";
import type { RiskTier } from "@/lib/types";

type ScoreCardProps = {
  label: string;
  score: number | null;
  tier: RiskTier | null;
  title?: string;
};

export default function ScoreCard({ label, score, tier, title }: ScoreCardProps) {
  const style = riskTierStyle(score == null ? null : tier);
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-5" title={title}>
      <p className="text-sm text-white/60">{label}</p>
      <p className={`mt-2 ${score == null ? "text-lg font-medium" : "text-3xl font-bold"} ${style.text}`}>{score == null ? "Not assessed" : Math.round(score)}</p>
      {score != null && <p className={`mt-1 text-xs uppercase tracking-wide ${style.text}`}>{tier}</p>}
    </div>
  );
}
