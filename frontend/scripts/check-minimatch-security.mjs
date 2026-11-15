// Exercise the actual TypeScript ESLint dependency, preserving unrelated v3 consumers.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdtempSync, writeFileSync, unlinkSync, rmdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
const fromProject = createRequire(import.meta.url);
const fromEstree = createRequire(fromProject.resolve("@typescript-eslint/typescript-estree"));
const { minimatch, Minimatch } = fromEstree("minimatch");
for (const [file, pattern, matches] of [
  ["src/app/page.tsx", "src/**/*.tsx", true],
  ["src/.hidden.ts", "src/*.ts", true],
  ["src/page.js", "src/**/*.tsx", false],
  ["src/page.ts", "src/*.{ts,tsx}", true],
  ["src/page.tsx", "src/!(*.test).tsx", true],
  ["src/page.test.tsx", "src/!(*.test).tsx", false],
]) assert.equal(minimatch(file, pattern, { dot: true }), matches, `${file} / ${pattern}`);
// Bounded reproduction of GHSA-g3hv-75wg-m249: old code expands 256 patterns
// despite a limit of 64. Eight segments keep the pre-fix reproduction small.
const pattern = Array(8).fill("**/../a/b").join("/");
const compiled = new Minimatch(pattern, { optimizationLevel: 2, braceExpandMax: 64 });
assert.ok(compiled.set.length <= 64, `Preprocessing exceeded limit: ${compiled.set.length} > 64`);
// Exercise the actual consumer with a dotfile in a fresh inferred TS project.
const fixture = mkdtempSync(join(tmpdir(), "auditmind-eslint-security-"));
const filePath = join(fixture, ".dependency-security.ts");
try {
  const source = "const value: number = 1;";
  writeFileSync(filePath, source);
  const { parseAndGenerateServices } = fromProject("@typescript-eslint/typescript-estree");
  const parsed = parseAndGenerateServices(source, {
    filePath, tsconfigRootDir: fixture,
    projectService: { allowDefaultProject: ["*.ts"] },
  });
  assert.ok(parsed.services.program, "Project-service glob must admit the dotfile");
} finally {
  unlinkSync(filePath);
  rmdirSync(fixture);
}
console.log("TypeScript ESLint project-service compatibility and amplification guard passed");
