// Inspect consent/Begin once. Do not answer or solve any verification puzzle.
import 'dotenv/config';
import { mkdir, writeFile } from 'node:fs/promises';
import { chromium } from 'patchright';

const output = '/tmp/hket-probe';
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: false, executablePath: process.env.CHROMIUM_EXECUTABLE_PATH, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const context = await browser.newContext({ viewport: { width: 1365, height: 900 }, timezoneId: 'Asia/Hong_Kong' });
const page = await context.newPage();
const report = { actions: [], snapshots: [] };

async function snapshot(label) {
    const frames = [];
    for (const frame of page.frames()) {
        try {
            const url = new URL(frame.url());
            frames.push({ url: url.origin + url.pathname, text: (await frame.locator('body').innerText({ timeout: 3000 })).slice(0, 3500),
                controls: await frame.locator('button, [role="button"], input[type="button"]').evaluateAll(elements => elements.map(e => ({ text: (e.innerText || e.value || '').slice(0, 100), label: e.getAttribute('aria-label') }))) });
        } catch (error) { frames.push({ error: String(error).slice(0, 150) }); }
    }
    const item = { label, title: await page.title(), articles: await page.locator('.main-listing-container .share-button[data-url]').count(), frames };
    report.snapshots.push(item);
    await page.screenshot({ path: `${output}/${label}.png`, fullPage: true });
    console.log(JSON.stringify(item));
}

async function clickVisible(label) {
    for (const frame of page.frames()) {
        const button = frame.getByText(label, { exact: true }).first();
        if (await button.isVisible().catch(() => false)) {
            await button.click({ timeout: 5000 });
            report.actions.push({ clicked: label });
            console.log(JSON.stringify({ clicked: label }));
            await page.waitForTimeout(5000);
            return true;
        }
    }
    return false;
}

try {
    await page.goto('https://inews.hket.com/sran001/%E5%85%A8%E9%83%A8?mtc=80042', { waitUntil: 'domcontentloaded', timeout: 45000 });
    await page.waitForTimeout(8000);
    await snapshot('before');
    if (await clickVisible('Consent')) await snapshot('after-consent');
    if (await clickVisible('Begin')) {
        await snapshot('after-begin');
        await page.waitForTimeout(10000);
        await snapshot('after-begin-settled');
    }
    report.result = await page.locator('.main-listing-container .share-button[data-url]').count() > 0 ? 'articles-loaded' : 'verification-still-present';
} catch (error) {
    report.result = 'probe-error';
    report.error = String(error);
    await snapshot('error').catch(() => {});
} finally {
    await writeFile(`${output}/report.json`, JSON.stringify(report, null, 2));
    console.log(JSON.stringify({ result: report.result, actions: report.actions, error: report.error }));
    await browser.close();
}
