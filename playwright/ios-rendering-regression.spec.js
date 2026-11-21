const { test, expect, chromium, webkit } = require('@playwright/test');

const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:5000';

async function waitForPage(page) {
  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' });
  await page.locator('#page-preloader').waitFor({ state: 'hidden', timeout: 10_000 });
}

async function assertRendered(locator) {
  await locator.scrollIntoViewIfNeeded();
  const metrics = await locator.evaluate((element) => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return {
      opacity: Number(style.opacity),
      visibility: style.visibility,
      display: style.display,
      width: rect.width,
      height: rect.height,
      inViewport: rect.bottom > 0 && rect.top < innerHeight
    };
  });
  expect(metrics.opacity).toBeGreaterThan(0.99);
  expect(metrics.visibility).toBe('visible');
  expect(metrics.display).not.toBe('none');
  expect(metrics.width).toBeGreaterThan(40);
  expect(metrics.height).toBeGreaterThan(40);
  expect(metrics.inViewport).toBeTruthy();
}

for (const width of [375, 390, 430]) {
  test(`WebKit reduced motion renders tours at ${width}px`, async () => {
    const browser = await webkit.launch({ headless: true });
    const context = await browser.newContext({
      viewport: { width, height: 844 },
      reducedMotion: 'reduce',
      isMobile: true,
      hasTouch: true,
      userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1'
    });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));

    await waitForPage(page);
    const bodyStyle = await page.locator('body').evaluate((body) => ({
      transform: body.style.transform,
      webkitTransform: body.style.webkitTransform,
      backface: body.style.webkitBackfaceVisibility
    }));
    expect(bodyStyle).toEqual({ transform: '', webkitTransform: '', backface: '' });

    const location = page.locator('.location-card[data-location-has-slots="true"]').first();
    await assertRendered(location);
    await location.click();

    const tourCard = page.locator('[data-tour-card]').first();
    await expect(tourCard).toHaveCount(1);
    await assertRendered(tourCard);
    await assertRendered(page.locator('#faq'));
    expect(errors).toEqual([]);

    await page.screenshot({ path: `test-results/ios-webkit-reduced-${width}.png`, fullPage: true });
    await browser.close();
  });
}

for (const engine of [{ name: 'webkit', type: webkit }, { name: 'chromium', type: chromium }]) {
  test(`${engine.name} repeated overlays restore scrolling`, async () => {
    const browser = await engine.type.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
    const page = await context.newPage();
    await waitForPage(page);

    await page.locator('label[for="mobile-drawer"]').first().click();
    await expect(page.locator('#mobile-drawer')).toBeChecked();
    await page.locator('.drawer-side a[href="#faq"]').click();
    await expect(page.locator('#mobile-drawer')).not.toBeChecked();

    await page.locator('#tours').scrollIntoViewIfNeeded();
    const carousel = page.locator('[data-location-carousel]');
    const initialCarouselLeft = await carousel.evaluate((element) => element.scrollLeft);
    await page.locator('[data-carousel-next]').click();
    await expect.poll(() => carousel.evaluate((element) => element.scrollLeft)).toBeGreaterThan(initialCarouselLeft);
    const startY = await page.evaluate(() => scrollY);

    for (let iteration = 0; iteration < 2; iteration += 1) {
      await page.locator('#my_modal_7').evaluate((toggle) => {
        toggle.checked = true;
        toggle.dispatchEvent(new Event('change'));
      });
      await expect(page.locator('#my_modal_7')).toBeChecked();
      await expect.poll(() => page.locator('body').evaluate((body) => body.style.position)).toBe('fixed');
      await page.locator('#close-modal-btn').click();
      await expect(page.locator('#my_modal_7')).not.toBeChecked();
      await expect.poll(() => page.locator('body').evaluate((body) => body.style.position)).toBe('');
      expect(Math.abs((await page.evaluate(() => scrollY)) - startY)).toBeLessThanOrEqual(2);
    }

    const mapTrigger = page.locator('.location-card [data-map-overlay-trigger]').first();
    await mapTrigger.click();
    await expect(page.locator('#tour-map-overlay')).not.toHaveClass(/hidden/);
    await page.locator('[data-close-map-overlay]').click();
    await expect(page.locator('#tour-map-overlay')).toHaveClass(/hidden/);
    await expect.poll(() => page.locator('body').evaluate((body) => body.style.position)).toBe('');

    await page.locator('.location-card[data-location-has-slots="true"]').first().click();
    const preview = page.locator('.location-tour-carousel .carousel-item[aria-hidden="false"] [data-image-preview]').first();
    await assertRendered(preview);
    await preview.click();
    await expect(page.locator('#location-image-modal')).toHaveJSProperty('open', true);
    await page.locator('#location-image-modal [data-modal-close]').click();
    await expect(page.locator('#location-image-modal')).toHaveJSProperty('open', false);
    await expect.poll(() => page.locator('body').evaluate((body) => body.style.position)).toBe('');

    await page.locator('[data-tour-info-button]').first().click();
    await expect(page.locator('#my_modal_7')).toBeChecked();
    await expect(page.locator('#reservation-view')).not.toHaveClass(/hidden/);
    await page.locator('#close-modal-btn').click();
    await expect(page.locator('#my_modal_7')).not.toBeChecked();
    await expect.poll(() => page.locator('body').evaluate((body) => body.style.position)).toBe('');

    await page.setViewportSize({ width: 844, height: 390 });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.setViewportSize({ width: 1440, height: 900 });
    await assertRendered(page.locator('#tours'));
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    await browser.close();
  });
}

test('WebKit keeps tour information usable when images fail', async () => {
  const browser = await webkit.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const page = await context.newPage();
  await page.route(/\.(?:avif|gif|jpe?g|png|webp)(?:\?.*)?$/i, (route) => route.abort());
  await waitForPage(page);
  await page.locator('.location-card[data-location-has-slots="true"]').first().click();
  const card = page.locator('[data-tour-card]').first();
  await assertRendered(card);
  await expect(card.locator('[data-tour-info-button]')).toBeEnabled();
  await expect(card.getByText(/A kép nem tölthető be|Hiba/).first()).toBeVisible();
  await browser.close();
});
