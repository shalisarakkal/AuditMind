// frontend/scripts/a11y.js
// Accessibility audit using Playwright + @axe-core/playwright

(async () => {
  const { chromium } = await import('playwright');
  const { AxeBuilder } = await import('@axe-core/playwright');
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  // The app redirects unauthenticated users to /login — audit that page too.
  const pagesToAudit = [
    'http://localhost:3000/login',
    'http://localhost:3000/reports',
    'http://localhost:3000/',
  ];

  let totalViolations = 0;

  for (const url of pagesToAudit) {
    try {
      await page.goto(url, { waitUntil: 'networkidle', timeout: 15000 });
    } catch {
      // Page may redirect or time out — still run axe on whatever loaded
    }

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();

    if (results.violations.length) {
      console.error(`\n[FAIL] ${url} — ${results.violations.length} violation(s):`);
      results.violations.forEach(v => {
        console.error(`  • [${v.impact.toUpperCase()}] ${v.id}: ${v.description}`);
        v.nodes.slice(0, 3).forEach(n => console.error(`    HTML: ${n.html.slice(0, 120)}`));
      });
      totalViolations += results.violations.length;
    } else {
      console.log(`[PASS] ${url}`);
    }
  }

  await browser.close();

  if (totalViolations > 0) {
    console.error(`\nTotal WCAG violations: ${totalViolations}`);
    process.exit(1);
  } else {
    console.log('\nNo accessibility violations detected.');
    process.exit(0);
  }
})();
