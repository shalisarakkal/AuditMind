import { riskTierStyle } from "@/lib/domain";
import type { RiskTier } from "@/lib/types";
import { enumLabel } from "@/lib/presentation";

type ScoreCardProps = {
  label: string;
  score: number | null;
  tier: RiskTier | null;
  title?: string;
  unscoredLabel?: string;
};

export default function ScoreCard({ label, score, tier, title, unscoredLabel = "Not assessed" }: ScoreCardProps) {
  const style = riskTierStyle(score == null ? null : tier);
  return (
    <div className="min-w-0 rounded-xl border border-white/10 bg-white/5 p-4 sm:p-5" title={title}>
      <p className="text-sm text-white/60">{label}</p>
      <p className={`mt-2 ${score == null ? "text-lg font-medium" : "text-3xl font-bold"} ${style.text}`}>{score == null ? unscoredLabel : Math.round(score)}</p>
      {score != null && <p className={`mt-1 text-xs tracking-wide ${style.text}`}>{tier ? enumLabel(tier) : "Not recorded"}</p>}
    </div>
  );
}
