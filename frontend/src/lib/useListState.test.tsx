import { act, renderHook } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { useListState } from "./useListState";

const navigation = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: navigation.replace }),
  usePathname: () => "/assets",
  useSearchParams: () => new URLSearchParams("org=org-1&q=server"),
}));

it("keeps selection filter identity across seek pages and resets cursors when sorting or filtering", () => {
  const { result } = renderHook(() => useListState(100, "org-1"));
  const identity = result.current.filterKey;
  act(() => result.current.setOffset(100, "signed-anchor"));
  expect(new URLSearchParams(result.current.apiQuery).get("cursor")).toBe("signed-anchor");
  expect(result.current.filterKey).toBe(identity);
  act(() => result.current.setSort("hostname", "desc"));
  expect(result.current.offset).toBe(0);
  expect(new URLSearchParams(result.current.apiQuery).has("cursor")).toBe(false);
  act(() => result.current.setOffset(100, "another-anchor"));
  act(() => result.current.setText("q", "network"));
  expect(result.current.offset).toBe(0);
  expect(new URLSearchParams(result.current.apiQuery).has("cursor")).toBe(false);
  expect(result.current.filterKey).not.toBe(identity);
});
