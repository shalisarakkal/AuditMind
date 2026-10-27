import { createEvent, fireEvent, render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import FileDropGuard from "@/components/FileDropGuard";

describe("FileDropGuard", () => {
  it("prevents browser file navigation anywhere in the authenticated document", () => {
    const { unmount } = render(<FileDropGuard />);
    for (const name of ["dragOver", "drop"] as const) {
      const event = createEvent[name](document.body, { dataTransfer: { types: ["Files"], files: [] } });
      fireEvent(document.body, event);
      expect(event.defaultPrevented).toBe(true);
    }
    unmount();
    const event = createEvent.drop(document.body, { dataTransfer: { types: ["Files"], files: [] } });
    fireEvent(document.body, event);
    expect(event.defaultPrevented).toBe(false);
  });

  it("preserves text drags and native file-input drop behavior", () => {
    const { container } = render(<><FileDropGuard /><input type="file" /></>);
    const text = createEvent.drop(document.body, { dataTransfer: { types: ["text/plain"], files: [] } });
    fireEvent(document.body, text);
    expect(text.defaultPrevented).toBe(false);
    const native = createEvent.drop(container.querySelector("input")!, { dataTransfer: { types: ["Files"], files: [] } });
    fireEvent(container.querySelector("input")!, native);
    expect(native.defaultPrevented).toBe(false);
  });
});
