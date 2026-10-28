// Private, run-scoped browser transport inside the existing RSSHub container.
import 'dotenv/config';
import http from 'node:http';
import { chromium } from 'patchright';

const browser = await chromium.launch({
    headless: false,
    executablePath: process.env.CHROMIUM_EXECUTABLE_PATH,
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
});
const context = await browser.newContext({ viewport: { width: 1365, height: 900 }, timezoneId: 'Asia/Hong_Kong' });
const page = await context.newPage();
http.createServer(async (request, response) => {
    try {
        const url = new URL(new URL(request.url, 'http://localhost').searchParams.get('url'));
        if (url.protocol !== 'https:' || !url.hostname.endsWith('.hket.com') || url.port || url.username) {
            throw new Error('Only public HKET pages are allowed');
        }
        if (page.url() !== url.href) {
            await page.goto(url.href, { waitUntil: 'domcontentloaded', timeout: 30000 });
        }
        await page.waitForFunction(() => document.querySelector('.main-listing-container .share-button[data-url]') ||
            [...document.querySelectorAll('script[type="application/ld+json"]')].some(e => e.textContent.includes('NewsArticle')),
            undefined, { timeout: 45000 });
        response.writeHead(200, { 'Content-Type': 'application/json' });
        response.end(JSON.stringify({ html: await page.content() }));
    } catch (error) {
        response.writeHead(502, { 'Content-Type': 'application/json' });
        response.end(JSON.stringify({ error: String(error), title: await page.title(), text: (await page.locator('body').innerText()).slice(0, 500) }));
    }
}).listen(1201, '127.0.0.1');
