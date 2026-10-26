import { expect, it } from "vitest";
import { changedWorkflowFields, formatDeadline, type WorkflowHistory } from "./findingWorkflow";

it("formats a saved deadline in local time without timezone/technical detail", () => {
  const expiry="2026-10-25T18:30:00Z";
  const expected=new Date(Date.parse(expiry)-1).toLocaleString(undefined,{year:"numeric",month:"short",day:"numeric",hour:"numeric",minute:"2-digit"});
  expect(formatDeadline("2026-10-25",expiry)).toBe(expected);
  expect(formatDeadline(null,null)).toBe("Not set");
  expect(formatDeadline("2026-10-25",null)).toBe("2026-10-25");
});

it("reports timing changes as deadline changes without exposing timezone metadata", () => {
  const entry={before:{due_date:"2026-10-25",due_timezone:"Asia/Kolkata",due_expires_at:"2026-10-25T18:30:00Z"},
    after:{due_date:"2026-10-25",due_timezone:"UTC",due_expires_at:"2026-10-26T00:00:00Z"}} as unknown as WorkflowHistory;
  expect(changedWorkflowFields(entry)).toEqual(["due_date"]);
  entry.after={...entry.before,due_timezone:"Asia/Calcutta"};
  expect(changedWorkflowFields(entry)).toEqual([]);
});
