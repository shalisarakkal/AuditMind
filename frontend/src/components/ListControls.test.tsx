import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PickFilter } from "@/components/ListControls";

function Filter({ label = "type" }: { label?: string }) {
  const [chosen, setChosen] = useState<string[]>([]);
  // PickFilter consumes just these two list operations.
  const list = {
    values: () => chosen,
    setValues: (_name: string, values: string[]) => setChosen(values),
  };
  return <PickFilter name={label} label={label} list={list} options={[
    { value: "database", label: "Database" }, { value: "server", label: "Server" },
  ]} />;
}

describe("PickFilter dismissal", () => {
  it("closes on an outside click without clearing the selection", async () => {
    const user = userEvent.setup();
    render(<><Filter /><button>Outside</button></>);
    await user.click(screen.getByLabelText("Filter type: All"));
    await user.click(screen.getByRole("checkbox", { name: "Database" }));
    const summary = screen.getByLabelText("Filter type: Database");
    expect(summary.closest("details")).toHaveAttribute("open");
    await user.click(screen.getByRole("button", { name: "Outside" }));
    expect(summary.closest("details")).not.toHaveAttribute("open");
    await user.click(summary);
    expect(screen.getByRole("checkbox", { name: "Database" })).toBeChecked();
  });

  it("keeps internal multi-selection and Clear clicks open", async () => {
    const user = userEvent.setup();
    render(<Filter />);
    const summary = screen.getByLabelText("Filter type: All");
    await user.click(summary);
    await user.click(screen.getByRole("checkbox", { name: "Database" }));
    await user.click(screen.getByRole("checkbox", { name: "Server" }));
    expect(summary.closest("details")).toHaveAttribute("open");
    await user.click(screen.getByRole("button", { name: "Clear" }));
    expect(summary.closest("details")).toHaveAttribute("open");
    expect(screen.getByRole("checkbox", { name: "Database" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Server" })).not.toBeChecked();
  });

  it("closes with Escape and returns keyboard focus to its summary", async () => {
    const user = userEvent.setup();
    render(<Filter />);
    const summary = screen.getByLabelText("Filter type: All");
    await user.click(summary);
    screen.getByRole("checkbox", { name: "Database" }).focus();
    await user.keyboard("{Escape}");
    expect(summary.closest("details")).not.toHaveAttribute("open");
    expect(summary).toHaveFocus();
  });

  it("retains summary toggle behavior and closes when another filter opens", async () => {
    const user = userEvent.setup();
    render(<><Filter /><Filter label="subtype" /></>);
    const first = screen.getByLabelText("Filter type: All");
    await user.click(first);
    await user.click(first);
    expect(first.closest("details")).not.toHaveAttribute("open");
    await user.click(first);
    const second = screen.getByLabelText("Filter subtype: All");
    await user.click(second);
    expect(first.closest("details")).not.toHaveAttribute("open");
    expect(second.closest("details")).toHaveAttribute("open");
  });

  it("uses capture for outside clicks and removes listeners on unmount", async () => {
    const remove = vi.spyOn(document, "removeEventListener");
    const user = userEvent.setup();
    const view = render(<><Filter /><button onClick={event => event.stopPropagation()}>Outside</button></>);
    const summary = screen.getByLabelText("Filter type: All");
    await user.click(summary);
    fireEvent.click(screen.getByRole("button", { name: "Outside" }));
    expect(summary.closest("details")).not.toHaveAttribute("open");
    view.unmount();
    expect(remove).toHaveBeenCalledWith("click", expect.any(Function), true);
    expect(remove).toHaveBeenCalledWith("keydown", expect.any(Function));
  });
});
