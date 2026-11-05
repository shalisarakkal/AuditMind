import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import Pager from "./Pager";

it("passes the cursor for the chosen direction while preserving offset navigation", () => {
  const change = vi.fn();
  const view = render(<Pager offset={100} limit={100} total={400} onChange={change}
    nextCursor="next-anchor" previousCursor="previous-anchor" />);
  fireEvent.click(screen.getByText("Next"));
  expect(change).toHaveBeenLastCalledWith(200, "next-anchor");
  fireEvent.click(screen.getByText("Previous"));
  expect(change).toHaveBeenLastCalledWith(0, "previous-anchor");
  view.rerender(<Pager offset={100} limit={100} total={400} onChange={change} />);
  fireEvent.click(screen.getByText("Next"));
  expect(change).toHaveBeenLastCalledWith(200);
});
