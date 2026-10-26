import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import FindingActionDialog from "./FindingActionDialog";

describe("Finding action dialog", () => {
  it("opens a native modal, allows Escape before submission and restores focus", () => {
    const close = vi.fn(), trigger = document.createElement("button");
    document.body.append(trigger); trigger.focus();
    const view = render(<FindingActionDialog title="Archive this finding" orgName="SA01" onClose={close}><button data-confirm-cancel>Cancel</button></FindingActionDialog>);
    const dialog = screen.getByRole("dialog", { name:"Archive this finding" });
    expect(dialog).toHaveAttribute("open"); expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByRole("button", {name:"Cancel"})).toHaveFocus();
    fireEvent(dialog, new Event("cancel", { cancelable:true })); expect(close).toHaveBeenCalledOnce();
    view.unmount(); expect(trigger).toHaveFocus(); trigger.remove();
  });
  it("blocks Escape while submission is in progress", () => {
    const close = vi.fn();
    render(<FindingActionDialog title="Archive selected findings" orgName="SA01" onClose={close}><div aria-busy="true">Submitting</div></FindingActionDialog>);
    fireEvent(screen.getByRole("dialog"), new Event("cancel", { cancelable:true }));
    expect(close).not.toHaveBeenCalled();
  });
});
