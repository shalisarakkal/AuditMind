import "@testing-library/jest-dom/vitest";

import { cleanup, configure } from "@testing-library/react";
import { afterEach, vi } from "vitest";

import { clearToken } from "@/lib/apiClient";

// findBy/waitFor wait up to 3 s (the default is 1 s): a full run shares the
// machine with the dev servers and the worker, and a busy moment made
// different tests miss the 1 s now and then.
configure({ asyncUtilTimeout: 3000 });

// jsdom does not implement the browser top layer/focus containment. Component
// tests model open/close only; installed Chrome verifies native modal behavior.
HTMLDialogElement.prototype.showModal = function () { this.open = true; };
HTMLDialogElement.prototype.close = function () { this.open = false; };

afterEach(() => {
  cleanup();
  clearToken();
  window.localStorage.clear();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
});
