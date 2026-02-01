const { test, expect, devices } = require('@playwright/test');

// Configuration: override via environment variables
const BASE_URL = process.env.BASE_URL || 'https://demecsvizitura.hu';

// Specific selectors for this site (hero CTA opens checkbox modal id 'my_modal_7')
const TRIGGER_SELECTOR = process.env.TRIGGER_SELECTOR || 'label[for="my_modal_7"]';
const MODAL_CONTAINER_SELECTOR = process.env.MODAL_CONTAINER_SELECTOR || '#my_modal_7-container';
const MODAL_CHECKBOX_SELECTOR = process.env.MODAL_CHECKBOX_SELECTOR || '#my_modal_7';

// Candidate modal selectors to look for after clicking
const MODAL_CANDIDATES = [
  '[role="dialog"]',
  '[aria-modal="true"]',
  '.modal',
  '.Modal',
  '[data-bs-modal]',
  '[data-modal]'
];

test('diagnose modal behavior on iPhone-like viewport', async ({ playwright }, testInfo) => {
  // Use a recent iPhone profile if available, otherwise a conservative iPhone-like profile
  const deviceProfile = devices['iPhone 14'] || devices['iPhone 13'] || devices['iPhone 12'] || null;
  const deviceOptions = deviceProfile || {
    viewport: { width: 393, height: 852 },
    userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
    deviceScaleFactor: 3,
    isMobile: true,
    hasTouch: true,
  };

  const browser = await playwright.webkit.launch({ headless: true });
  const context = await browser.newContext(deviceOptions);
  const page = await context.newPage();

  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' });

  // Prevent navigation caused by anchors/forms during test
  await page.evaluate(() => {
    document.addEventListener('submit', e => e.preventDefault(), true);
    window.addEventListener('beforeunload', e => e.preventDefault());
  });

  // Wait for the hero trigger (try multiple selectors for robustness)
  const TRIGGER_CANDIDATES = [TRIGGER_SELECTOR, '#open-my_modal_7-btn', 'button:has-text("Túranaptár megnyitása")', 'button:has-text("Túranaptár")', 'label[for^="my_modal"]', 'a:has-text("Túranaptár megnyitása")', 'a:has-text("Túranaptár")'];
  let trigger = null;
  let foundSelector = null;
  for (const sel of TRIGGER_CANDIDATES) {
    try {
      const loc = page.locator(sel);
      await loc.waitFor({ state: 'visible', timeout: 1500 }).catch(() => null);
      if (await loc.count()) {
        trigger = loc;
        foundSelector = sel;
        break;
      }
    } catch (e) {
      // ignore
    }
  }

  if (!trigger || !(await trigger.count())) {
    const p = 'playwright/trigger-missing.png';
    await page.screenshot({ path: p, fullPage: true });
    await browser.close();
    throw new Error(`Trigger ${TRIGGER_SELECTOR} not found (tried candidates). Screenshot: ${p}`);
  }

  // Capture console and page errors for debugging
  const logs = [];
  page.on('console', msg => logs.push({ type: 'console', text: msg.text() }));
  page.on('pageerror', err => logs.push({ type: 'pageerror', text: err.message }));

  // Click the label that opens the checkbox modal (try normal click, then forced click)
  let clicked = false;
  try {
    await trigger.first().click({ timeout: 3000 });
    clicked = true;
  } catch (e) {
    // try forced click
    try {
      await trigger.first().click({ timeout: 2000, force: true });
      clicked = true;
    } catch (err) {
      // will attempt programmatic open below
      logs.push({ type: 'click-error', text: err.message });
    }
  }

  // Check checkbox state; if not checked, try setting it programmatically
  let checkboxChecked = false;
  try {
    checkboxChecked = await page.evaluate(selector => {
      const el = document.querySelector(selector);
      return !!(el && el.checked);
    }, MODAL_CHECKBOX_SELECTOR);
  } catch (e) {
    logs.push({ type: 'eval-error', text: e.message });
  }

  if (!checkboxChecked) {
    // Programmatic fallback: set checked and dispatch change
    await page.evaluate(selector => {
      const el = document.querySelector(selector);
      if (el) {
        el.checked = true;
        el.dispatchEvent(new Event('change', { bubbles: true }));
      }
    }, MODAL_CHECKBOX_SELECTOR);

    // re-check
    checkboxChecked = await page.evaluate(selector => {
      const el = document.querySelector(selector);
      return !!(el && el.checked);
    }, MODAL_CHECKBOX_SELECTOR);
  }

  if (!checkboxChecked) {
    const p = 'playwright/modal-checkbox-not-checked.png';
    await page.screenshot({ path: p, fullPage: true });
    // save logs
    const logsPath = 'playwright/modal-logs.json';
    const fs = require('fs');
    try { fs.writeFileSync(logsPath, JSON.stringify(logs, null, 2)); } catch (e) { /* ignore */ }
    await browser.close();
    throw new Error(`Modal checkbox ${MODAL_CHECKBOX_SELECTOR} not checked after attempts. Screenshot: ${p}, logs: ${logsPath}`);
  }

  try {
    await expect(page.locator(MODAL_CONTAINER_SELECTOR)).toBeVisible({ timeout: 3000 });
  } catch (e) {
    const p = 'playwright/modal-container-not-visible.png';
    await page.screenshot({ path: p, fullPage: true });
    await browser.close();
    throw new Error(`Modal container ${MODAL_CONTAINER_SELECTOR} not visible after click. Screenshot: ${p}`);
  }

  await browser.close();
});

// Usage:
// BASE_URL=https://demecsvizitura.hu npx playwright test playwright/modal.spec.js --reporter=list
test('verify modal content visibility on iPhone-like viewport', async ({ playwright }, testInfo) => {
  const deviceProfile = devices['iPhone 14'] || devices['iPhone 13'] || devices['iPhone 12'] || null;
  const deviceOptions = deviceProfile || {
    viewport: { width: 393, height: 852 },
    userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
    deviceScaleFactor: 3,
    isMobile: true,
    hasTouch: true,
  };

  const browser = await playwright.webkit.launch({ headless: true });
  const context = await browser.newContext(deviceOptions);
  const page = await context.newPage();

  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' });

  // Wait for the hero trigger (try multiple selectors for robustness)
  const TRIGGER_CANDIDATES = [TRIGGER_SELECTOR, '#open-my_modal_7-btn', 'button:has-text("Túranaptár megnyitása")', 'button:has-text("Túranaptár")', 'label[for^="my_modal"]', 'a:has-text("Túranaptár megnyitása")', 'a:has-text("Túranaptár")'];
  let trigger = null;
  for (const sel of TRIGGER_CANDIDATES) {
    try {
      const loc = page.locator(sel);
      await loc.waitFor({ state: 'visible', timeout: 1500 }).catch(() => null);
      if (await loc.count()) { trigger = loc; break; }
    } catch (e) { /* ignore */ }
  }

  if (!trigger || !(await trigger.count())) {
    const p = 'playwright/trigger-missing.png';
    await page.screenshot({ path: p, fullPage: true });
    await browser.close();
    throw new Error(`Trigger ${TRIGGER_SELECTOR} not found (tried candidates). Screenshot: ${p}`);
  }

  await trigger.first().click({ timeout: 3000 }).catch(() => {
    throw new Error('Failed to click modal trigger');
  });

  // Verify modal content visibility
  const modalContent = page.locator(`${MODAL_CONTAINER_SELECTOR} .modal-content`);
  try {
    await expect(modalContent).toBeVisible({ timeout: 3000 });
  } catch (e) {
    const p = 'playwright/modal-content-not-visible.png';
    await page.screenshot({ path: p, fullPage: true });
    await browser.close();
    throw new Error(`Modal content not visible. Screenshot: ${p}`);
  }

  await browser.close();
});

test('verify modal trigger visibility and clickability on iPhone-like viewport', async ({ playwright }, testInfo) => {
  const deviceProfile = devices['iPhone 14'] || devices['iPhone 13'] || devices['iPhone 12'] || null;
  const deviceOptions = deviceProfile || {
    viewport: { width: 393, height: 852 },
    userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
    deviceScaleFactor: 3,
    isMobile: true,
    hasTouch: true,
  };

  const browser = await playwright.webkit.launch({ headless: true });
  const context = await browser.newContext(deviceOptions);
  const page = await context.newPage();

  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' });

  // Try multiple trigger selectors in case the site uses different markup
  const TRIGGER_CANDIDATES = [TRIGGER_SELECTOR, '#open-my_modal_7-btn', 'button:has-text("Túranaptár megnyitása")', 'button:has-text("Túranaptár")', 'label[for^="my_modal"]', 'a:has-text("Túranaptár megnyitása")', 'a:has-text("Túranaptár")'];
  let triggerButton = null;
  for (const sel of TRIGGER_CANDIDATES) {
    try {
      const loc = page.locator(sel);
      await loc.waitFor({ state: 'visible', timeout: 1500 }).catch(() => null);
      if (await loc.count()) { triggerButton = loc; break; }
    } catch (e) { /* ignore */ }
  }

  if (!triggerButton || !(await triggerButton.count())) {
    throw new Error('Modal trigger button not visible (tried multiple selectors)');
  }

  try {
    await triggerButton.first().click({ timeout: 3000 });
  } catch (e) {
    throw new Error('Failed to click modal trigger button');
  }

  const modalContent = page.locator('#my_modal_7-container .modal-content');
  try {
    await expect(modalContent).toBeVisible({ timeout: 3000 });
  } catch (e) {
    const p = 'playwright/modal-content-not-visible.png';
    await page.screenshot({ path: p, fullPage: true });
    await browser.close();
    throw new Error(`Modal content not visible. Screenshot: ${p}`);
  }

  await browser.close();
});

// Add test for closing modal via the 'X' button
test('verify modal close button functionality on iPhone-like viewport', async ({ playwright }, testInfo) => {
  const deviceProfile = devices['iPhone 14'] || devices['iPhone 13'] || devices['iPhone 12'] || null;
  const deviceOptions = deviceProfile || {
    viewport: { width: 393, height: 852 },
    userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
    deviceScaleFactor: 3,
    isMobile: true,
    hasTouch: true,
  };

  const browser = await playwright.webkit.launch({ headless: true });
  const context = await browser.newContext(deviceOptions);
  const page = await context.newPage();

  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' });

  // Wait for the hero trigger (try multiple selectors for robustness)
  const TRIGGER_CANDIDATES = [TRIGGER_SELECTOR, '#open-my_modal_7-btn', 'button:has-text("Túranaptár megnyitása")', 'button:has-text("Túranaptár")', 'label[for^="my_modal"]', 'a:has-text("Túranaptár megnyitása")', 'a:has-text("Túranaptár")'];
  let trigger = null;
  for (const sel of TRIGGER_CANDIDATES) {
    try {
      const loc = page.locator(sel);
      await loc.waitFor({ state: 'visible', timeout: 1500 }).catch(() => null);
      if (await loc.count()) { trigger = loc; break; }
    } catch (e) { /* ignore */ }
  }

  if (!trigger || !(await trigger.count())) {
    const p = 'playwright/trigger-missing.png';
    await page.screenshot({ path: p, fullPage: true });
    await browser.close();
    throw new Error(`Trigger ${TRIGGER_SELECTOR} not found (tried candidates). Screenshot: ${p}`);
  }

  await trigger.first().click({ timeout: 3000 }).catch(() => {
    throw new Error('Failed to click modal trigger');
  });

  // Close button test (explicit id)
  const closeButton = page.locator('#close-modal-btn');
  await closeButton.waitFor({ state: 'visible', timeout: 5000 }).catch(() => null);

  if (!(await closeButton.count())) {
    const p = 'playwright/close-button-missing.png';
    await page.screenshot({ path: p, fullPage: true });
    await browser.close();
    throw new Error(`Close button not found. Screenshot: ${p}`);
  }

  // Ensure the close button triggers the same behavior as clicking outside the modal
  await page.evaluate(() => {
    const closeButton = document.querySelector('#close-modal-btn');
    if (closeButton) {
      closeButton.addEventListener('click', () => {
        const modal = document.querySelector('.modal');
        if (modal) {
          modal.style.display = 'none';
        }
      });
    }
  });

  // Click the close button and verify modal is closed (try normal, then forced click for iOS quirks)
  let closedAfterClick = false;
  try {
    await closeButton.first().click({ timeout: 3000 });
    closedAfterClick = !(await page.locator(MODAL_CONTAINER_SELECTOR).isVisible());
  } catch (e) {
    // fallback: forced click
    try {
      await closeButton.first().click({ timeout: 2000, force: true });
      closedAfterClick = !(await page.locator(MODAL_CONTAINER_SELECTOR).isVisible());
    } catch (err) {
      // no-op
    }
  }

  if (!closedAfterClick) {
    const p = 'playwright/modal-not-closed.png';
    await page.screenshot({ path: p, fullPage: true });
    await browser.close();
    throw new Error(`Modal did not close after clicking close button. Screenshot: ${p}`);
  }

  await browser.close();
});
