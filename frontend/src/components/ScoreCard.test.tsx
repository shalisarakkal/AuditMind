import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ScoreCard from "./ScoreCard";
import { riskTierStyle } from "@/lib/domain";

describe("risk-tier presentation", () => {
  it.each([
    ["critical", "Critical risk", "red"],
    ["high", "High risk", "orange"],
    ["medium", "Medium risk", "amber"],
    ["low", "Low risk", "emerald"],
  ] as const)("renders %s with the original layout and shared text color", (tier, label, color) => {
    render(<ScoreCard label="Domain" score={15} tier={tier} />);
    expect(screen.getByText(tier.charAt(0).toUpperCase() + tier.slice(1)).className).toContain(`text-${color}-`);
    expect(screen.getByText("15")).toBeVisible();
    expect(screen.getByText("Domain").parentElement).toHaveClass("bg-white/5", "border-white/10");
    expect(riskTierStyle(tier.toUpperCase())).toEqual(riskTierStyle(tier));
  });
  it("uses neutral styling for missing or unknown tiers", () => {
    expect(riskTierStyle(null).label).toBe("Risk tier unavailable");
    expect(riskTierStyle("unknown").bg).toBe("bg-white/5");
  });
});
