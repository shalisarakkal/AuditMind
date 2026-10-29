import { describe, expect, it } from "vitest";
import { DOCUMENT_MAX_BYTES, LOGO_MAX_BYTES, documentFileError, formatFileLimit, importFileError } from "./uploadValidation";

function fileWithSize(name: string, size: number) {
  const file = new File(["small fixture, no large allocation"], name);
  Object.defineProperty(file, "size", { value: size });
  return file;
}

describe("upload metadata validation", () => {
  it.each([[16, "16 bytes"], [1024, "1 KiB"], [10 * 1024**2, "10 MiB"], [256 * 1024**2, "256 MiB"], [1024**3, "1 GiB"]])("formats %s bytes", (bytes, expected) => {
    expect(formatFileLimit(Number(bytes))).toBe(expected);
  });
  it("uses the configured import ceiling, not the 10 MiB processing threshold", () => {
    expect(importFileError(fileWithSize("cloud_assets.json", 251 * 1024**2), 256 * 1024**2)).toBeNull();
    expect(importFileError(fileWithSize("cloud_assets.json", 256 * 1024**2 + 1), 256 * 1024**2)).toContain("256 MiB");
    expect(importFileError(fileWithSize("assets.CSV", 256 * 1024**2), 256 * 1024**2)).toBeNull();
  });
  it("distinguishes documents from inventory files and enforces exact document boundary", () => {
    expect(documentFileError(fileWithSize("POLICY.MD", DOCUMENT_MAX_BYTES))).toBeNull();
    expect(documentFileError(fileWithSize("policy.txt", DOCUMENT_MAX_BYTES + 1))).toContain("10 MiB");
    expect(documentFileError(fileWithSize("cloud_assets.json", 10))).toContain("Assets or Findings");
    expect(LOGO_MAX_BYTES).toBe(2 * 1024**2);
  });
  it("rejects unsupported import extensions", () => {
    expect(importFileError(fileWithSize("executable.exe", 1), 1024)).toContain("Unsupported file type");
    expect(importFileError(fileWithSize("scan.NESSUS", 1), 1024)).toBeNull();
  });
});
