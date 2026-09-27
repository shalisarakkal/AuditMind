import { TIER_COLORS } from "@/lib/domain";
import type { RiskTier } from "@/lib/types";

type ScoreCardProps = {
  label: string;
  score: number;
  tier: RiskTier;
  title?: string;
};

export default function ScoreCard({ label, score, tier, title }: ScoreCardProps) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-5" title={title}>
      <p className="text-sm text-white/60">{label}</p>
      <p className={`mt-2 text-3xl font-bold ${TIER_COLORS[tier]}`}>{Math.round(score)}</p>
      <p className={`mt-1 text-xs uppercase tracking-wide ${TIER_COLORS[tier]}`}>{tier}</p>
    </div>
  );
}
