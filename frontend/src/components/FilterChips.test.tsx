import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { FilterChips } from "@/components/FilterChips";
import type { ListState } from "@/lib/useListState";

function Filters({ initial = [] }: { initial?: string[] }) {
  const [values, setValues] = useState(initial);
  const list: ListState = {
    apiQuery: "", offset: 0, sort: null, order: "asc", text: () => "",
    values: () => values, hasFilters: values.length > 0, filterKey: "", clearCount: 0,
    setText: () => {}, setValues: (_name, next) => setValues(next),
    setSort: () => {}, setOffset: () => {}, clearFilters: () => setValues([]),
  };
  return <FilterChips name="frameworks" label="Frameworks" options={[
    { value: "CIS", label: "CIS" }, { value: "NIST", label: "NIST" },
  ]} list={list} />;
}

test("chips replace the selection and All clears it", () => {
  render(<Filters />);
  expect(screen.getByRole("group", { name: "Frameworks" })).toBeInTheDocument();
  const all = screen.getByRole("button", { name: "All" });
  const cis = screen.getByRole("button", { name: "CIS" });
  const nist = screen.getByRole("button", { name: "NIST" });
  expect(all).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(cis);
  expect(cis).toHaveAttribute("aria-pressed", "true");
  expect(all).toHaveAttribute("aria-pressed", "false");
  fireEvent.click(nist);
  expect(cis).toHaveAttribute("aria-pressed", "false");
  expect(nist).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(all);
  expect(all).toHaveAttribute("aria-pressed", "true");
  expect(nist).toHaveAttribute("aria-pressed", "false");
});

test("chips reflect a filter restored from the URL", () => {
  render(<Filters initial={["NIST"]} />);
  expect(screen.getByRole("button", { name: "NIST" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "false");
});
