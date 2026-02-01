const { webkit } = require('playwright');

(async () => {
  const BASE_URL = process.env.BASE_URL || 'https://demecsvizitura.hu';
  const deviceOptions = {
    viewport: { width: 393, height: 852 },
    userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1',
    deviceScaleFactor: 3,
    isMobile: true,
    hasTouch: true,
  };

  const browser = await webkit.launch({ headless: true });
  const context = await browser.newContext(deviceOptions);
  const page = await context.newPage();

  try {
    console.log('Navigating to', BASE_URL);
    await page.goto(BASE_URL, { waitUntil: 'domcontentloaded', timeout: 15000 });
    await page.screenshot({ path: 'playwright/live-before.png', fullPage: true });

    const TRIGGER_CANDIDATES = [
      'label[for="my_modal_7"]',
      '#open-my_modal_7-btn',
      'button:has-text("Túranaptár megnyitása")',
      'button:has-text("Túranaptár")',
      'label[for^="my_modal"]',
      'a:has-text("Túranaptár megnyitása")',
      'a:has-text("Túranaptár")'
    ];

    let trigger = null;
    for (const sel of TRIGGER_CANDIDATES) {
      const loc = page.locator(sel);
      await loc.waitFor({ state: 'visible', timeout: 2000 }).catch(() => null);
      const count = await loc.count();
      console.log(`Selector ${sel} count=${count}`);
      if (count) { trigger = loc; break; }
    }

    if (!trigger) {
      console.error('No trigger found. See screenshot: playwright/live-before.png');
      await browser.close();
      process.exit(2);
    }

    console.log('Clicking trigger');
    await trigger.first().click({ timeout: 5000 }).catch(async (e) => {
      console.warn('Normal click failed, trying force', e.message);
      await trigger.first().click({ timeout: 3000, force: true });
    });

    await page.waitForTimeout(800);
    await page.screenshot({ path: 'playwright/live-after-open.png', fullPage: true });

    // locate close button
    const closeSel = '#close-modal-btn';
    const closeBtn = page.locator(closeSel);
    await closeBtn.waitFor({ state: 'visible', timeout: 3000 }).catch(() => null);
    const closeCount = await closeBtn.count();
    console.log(`Close button count=${closeCount}`);
    if (!closeCount) {
      console.error('Close button not found. See screenshot: playwright/live-after-open.png');
      await browser.close();
      process.exit(3);
    }

    console.log('Clicking close button');
    try {
      await closeBtn.first().click({ timeout: 3000 });
    } catch (e) {
      console.warn('Normal click failed, trying force click', e.message);
      await closeBtn.first().click({ timeout: 2000, force: true });
    }

    await page.waitForTimeout(500);
    await page.screenshot({ path: 'playwright/live-after-close.png', fullPage: true });

    // Check if modal container is visible
    const modalVisible = await page.locator('#my_modal_7-container').isVisible().catch(() => false);
    console.log('Modal visible after close?', modalVisible);

    if (modalVisible) {
      console.error('Modal remained open after clicking close. See playwright/live-after-close.png');
      await browser.close();
      process.exit(4);
    }

    console.log('Modal closed successfully with close button');
    await browser.close();
    process.exit(0);
  } catch (e) {
    console.error('Test script error', e);
    try { await page.screenshot({ path: 'playwright/live-error.png', fullPage: true }); } catch(_) {}
    await browser.close();
    process.exit(1);
  }
})();