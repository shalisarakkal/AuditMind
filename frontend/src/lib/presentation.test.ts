import { expect, it } from "vitest";
import { capturedTime, enumLabel, reportScope } from "./presentation";

it("formats captured instants with the browser locale rather than raw UTC", () => {
  const instant = "2026-10-23T16:56:58.129864+00:00";
  expect(capturedTime(instant)).toBe(new Date(instant).toLocaleString());
  expect(capturedTime(instant)).not.toContain("+00:00");
  expect(capturedTime(null)).toBe("Not recorded");
  expect(capturedTime("bad")).toBe("Invalid recorded timestamp");
});
it("labels known enums without transforming arbitrary report content", () => {
  expect(enumLabel("ACCEPTED_RISK")).toBe("Accepted risk");
  expect(reportScope("currently active findings created within inclusive UTC dates; current inventory")).toContain("Date boundaries were evaluated in UTC.");
  expect(reportScope("Original CIS/NIST scope")).toBe("Original CIS/NIST scope");
});
