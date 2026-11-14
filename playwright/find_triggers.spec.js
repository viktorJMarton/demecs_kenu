const { test } = require('@playwright/test');
const { devices } = require('@playwright/test');

const BASE_URL = process.env.BASE_URL || 'https://demecsvizitura.hu';

test('list visible buttons and anchors on iPhone-like viewport', async ({ playwright }) => {
  const deviceProfile = devices['iPhone 14'] || devices['iPhone 13'] || devices['iPhone 12'] || null;
  const deviceOptions = deviceProfile || { viewport: { width: 393, height: 852 }, isMobile: true, hasTouch: true };

  const browser = await playwright.webkit.launch({ headless: true });
  const context = await browser.newContext(deviceOptions);
  const page = await context.newPage();
  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' });

  // Query visible buttons and anchors
  const elements = await page.$$(':is(button, a, [role="button"], [aria-haspopup="dialog"])');
  const results = [];
  for (let i = 0; i < elements.length; i++) {
    const el = elements[i];
    const visible = await el.isVisible().catch(() => false);
    if (!visible) continue;
    const text = (await el.innerText()).trim().replace(/\s+/g, ' ');
    const href = await el.getAttribute('href').catch(() => null);
    const id = await el.getAttribute('id').catch(() => null);
    const cls = await el.getAttribute('class').catch(() => null);
    results.push({ index: i, text, href, id, class: cls });
  }

  // Print candidates that contain likely keywords
  const keywords = ['napt', 'túra', 'tura', 'tour', 'calendar', 'naptár', 'naptar'];
  for (const r of results) {
    if (keywords.some(k => (r.text||'').toLowerCase().includes(k))) {
      console.log('MATCH:', JSON.stringify(r));
    }
  }

  // Also print top 30 visible elements for manual inspection
  console.log('Top visible elements:');
  results.slice(0, 60).forEach(r => console.log(JSON.stringify(r)));

  await browser.close();
});
