import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import PasswordInput from "./PasswordInput";
import TemporaryPassword from "./TemporaryPassword";

it("starts hidden and preserves values, autocomplete and name while toggling", () => {
  render(<PasswordInput label="Password" aria-label="Password" name="password" defaultValue="Synthetic-secret" autoComplete="current-password" required />);
  const input = screen.getByLabelText("Password");
  expect(input).toHaveAttribute("type", "password");
  fireEvent.click(screen.getByRole("button", { name: "Show password" }));
  expect(input).toHaveAttribute("type", "text");
  expect(input).toHaveValue("Synthetic-secret");
  expect(input).toHaveAttribute("autocomplete", "current-password");
  expect(input).toHaveAttribute("name", "password");
  expect(input).toBeRequired();
  fireEvent.click(screen.getByRole("button", { name: "Hide password" }));
  expect(input).toHaveAttribute("type", "password");
});

it("supports keyboard activation without submitting the surrounding form", async () => {
  const submit = vi.fn(event => event.preventDefault());
  const user = userEvent.setup();
  render(<form onSubmit={submit}><PasswordInput label="Password" aria-label="Password" /></form>);
  await user.tab(); await user.tab();
  expect(screen.getByRole("button", { name: "Show password" })).toHaveFocus();
  await user.keyboard("{Enter}");
  expect(screen.getByLabelText("Password")).toHaveAttribute("type", "text");
  await user.keyboard(" ");
  expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
  expect(submit).not.toHaveBeenCalled();
});

it("keeps fields independent and hides again on remount", () => {
  const { unmount } = render(<><PasswordInput label="Current password" aria-label="Current password" /><PasswordInput label="New password" aria-label="New password" /></>);
  fireEvent.click(screen.getByRole("button", { name: "Show current password" }));
  expect(screen.getByLabelText("Current password")).toHaveAttribute("type", "text");
  expect(screen.getByLabelText("New password")).toHaveAttribute("type", "password");
  unmount();
  render(<PasswordInput label="Current password" aria-label="Current password" />);
  expect(screen.getByLabelText("Current password")).toHaveAttribute("type", "password");
});

it("disables both input and reveal button when disabled", () => {
  render(<PasswordInput label="Password" aria-label="Password" disabled />);
  expect(screen.getByLabelText("Password")).toBeDisabled();
  expect(screen.getByRole("button", { name: "Show password" })).toBeDisabled();
});

it("masks a new temporary handover and can copy without revealing", async () => {
  const clipboard = { writeText: vi.fn().mockResolvedValue(undefined) };
  vi.stubGlobal("navigator", { clipboard });
  const first = { who: "Synthetic user", password: "First-synthetic", expiresAt: null, added: true };
  const { rerender } = render(<TemporaryPassword handover={first} onDone={vi.fn()} />);
  expect(screen.getByLabelText("Temporary password value")).toHaveAttribute("type", "password");
  fireEvent.click(screen.getByRole("button", { name: "Copy" }));
  expect(clipboard.writeText).toHaveBeenCalledWith("First-synthetic");
  await screen.findByRole("button", { name: "Copied" });
  fireEvent.click(screen.getByRole("button", { name: "Show temporary password" }));
  expect(screen.getByLabelText("Temporary password value")).toHaveAttribute("type", "text");
  rerender(<TemporaryPassword handover={{ ...first, password: "Second-synthetic" }} onDone={vi.fn()} />);
  expect(screen.getByLabelText("Temporary password value")).toHaveAttribute("type", "password");
  expect(screen.getByLabelText("Temporary password value")).toHaveValue("Second-synthetic");
  expect(screen.getByRole("button", { name: "Copy" })).toBeInTheDocument();
});

it.each(["denied", "unavailable"])("handles %s clipboard access without revealing the secret", async mode => {
  vi.stubGlobal("navigator", mode === "denied" ? { clipboard: { writeText: vi.fn().mockRejectedValue(new Error("Denied")) } } : {});
  render(<TemporaryPassword handover={{ who: "Synthetic user", password: "Never-echo-this", expiresAt: null, added: false }} onDone={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Copy" }));
  const error = await screen.findByRole("alert");
  expect(error).toHaveTextContent("Copy unavailable");
  expect(error).not.toHaveTextContent("Never-echo-this");
  expect(screen.getByLabelText("Temporary password value")).toHaveAttribute("type", "password");
});
