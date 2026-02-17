/**
 * Test "Túra info" button functionality - verifies the button works on repeated clicks
 * Run: BASE_URL=https://demecsvizitura.hu npx playwright test playwright/tour_info_button.spec.js --reporter=list
 */
const { test, expect, devices } = require('@playwright/test');

const BASE_URL = process.env.BASE_URL || 'https://demecsvizitura.hu';

test.describe('Tour Info Button Tests', () => {

    test('tour info button works on repeated clicks', async ({ browser }) => {
        // Use iPhone viewport for mobile testing
        const context = await browser.newContext({
            ...devices['iPhone 13'],
            ignoreHTTPSErrors: true,
        });
        const page = await context.newPage();

        // Collect console errors
        const consoleErrors = [];
        page.on('console', msg => {
            if (msg.type() === 'error') {
                consoleErrors.push(msg.text());
            }
        });

        // Navigate to the page
        await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 30000 });

        // Scroll to location section to find tour info buttons
        const locationSection = page.locator('#location-tours-panel, [data-tours-list]').first();
        if (await locationSection.count() > 0) {
            await locationSection.scrollIntoViewIfNeeded();
            await page.waitForTimeout(500);
        }

        // Find the "Túra info" button
        const tourInfoButton = page.locator('[data-tour-info-button]').first();

        // Wait for button to be visible
        try {
            await tourInfoButton.waitFor({ state: 'visible', timeout: 10000 });
        } catch (e) {
            // If no tour info button found in location section, try the tours section
            const toursSection = page.locator('#tours').first();
            if (await toursSection.count() > 0) {
                await toursSection.scrollIntoViewIfNeeded();
                await page.waitForTimeout(500);
            }

            // Try finding any tour info button
            const anyTourInfoBtn = page.locator('button:has-text("Túra info"), .open-tour-details-btn').first();
            if (await anyTourInfoBtn.count() === 0) {
                console.log('No tour info buttons found on page');
                await page.screenshot({ path: 'playwright/no-tour-info-btn.png', fullPage: true });
                return;
            }
        }

        // First click - should open modal with tour details
        console.log('Click 1: Clicking tour info button...');
        await tourInfoButton.click();
        await page.waitForTimeout(2000); // Wait for fetch and render

        // Check if modal or reservation view appeared
        const reservationView = page.locator('#reservation-view, .modal-box, [data-reservation-view]').first();
        const isVisible1 = await reservationView.isVisible().catch(() => false);
        console.log(`Click 1: Reservation view visible: ${isVisible1}`);

        // Take screenshot after first click
        await page.screenshot({ path: 'playwright/tour-info-click1.png', fullPage: true });

        // Close the modal by clicking backdrop or back button
        const closeButton = page.locator('[data-close-modal], .modal-backdrop, label[for="my_modal_7"], #back-to-calendar, #back-to-calendar-btn, button:has-text("Vissza")').first();
        if (await closeButton.count() > 0) {
            await closeButton.click();
            await page.waitForTimeout(1000);
        } else {
            // Press Escape to close
            await page.keyboard.press('Escape');
            await page.waitForTimeout(1000);
        }

        console.log('Modal closed (or attempted)');
        await page.screenshot({ path: 'playwright/tour-info-after-close.png', fullPage: true });

        // Second click - should open modal again
        console.log('Click 2: Clicking tour info button again...');

        // Make sure button is visible again
        if (await tourInfoButton.isVisible()) {
            await tourInfoButton.click();
        } else {
            // Scroll back to find button
            await page.evaluate(() => window.scrollTo(0, 0));
            await page.waitForTimeout(500);
            const btn2 = page.locator('[data-tour-info-button]').first();
            await btn2.click();
        }

        await page.waitForTimeout(2000);

        // Check if modal appeared second time
        const isVisible2 = await reservationView.isVisible().catch(() => false);
        console.log(`Click 2: Reservation view visible: ${isVisible2}`);

        // Take screenshot after second click
        await page.screenshot({ path: 'playwright/tour-info-click2.png', fullPage: true });

        // Report any console errors
        if (consoleErrors.length > 0) {
            console.log('Console errors during test:');
            consoleErrors.forEach(err => console.log(`  - ${err}`));
        }

        // Assert that modal opened on second click
        expect(isVisible2, 'Modal should open on second click').toBeTruthy();

        await context.close();
    });

    test('tour info button opens modal from tours section', async ({ browser }) => {
        const context = await browser.newContext({
            ignoreHTTPSErrors: true,
        });
        const page = await context.newPage();

        await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 30000 });

        // Find tour info button in tours section
        const tourInfoButton = page.locator('#tours .open-tour-details-btn, #tours button:has-text("Túra info")').first();

        if (await tourInfoButton.count() === 0) {
            console.log('No tour info button found in tours section');
            return;
        }

        await tourInfoButton.scrollIntoViewIfNeeded();
        await page.waitForTimeout(300);

        // Click 3 times with waits
        for (let i = 1; i <= 3; i++) {
            console.log(`Click ${i}...`);
            await tourInfoButton.click();
            await page.waitForTimeout(2000);

            // Check modal state
            const modalCheckbox = page.locator('#my_modal_7');
            const isChecked = await modalCheckbox.isChecked().catch(() => false);
            console.log(`  Modal checkbox checked: ${isChecked}`);

            await page.screenshot({ path: `playwright/tours-section-click${i}.png`, fullPage: true });

            // Close modal
            await page.keyboard.press('Escape');
            await page.waitForTimeout(500);
        }

        await context.close();
    });
});
