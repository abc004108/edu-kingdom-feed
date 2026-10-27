import { load } from 'cheerio';

import type { DataItem, Route } from '@/types';
import ofetch from '@/utils/ofetch';
import { parseDate } from '@/utils/parse-date';
import { getPlaywrightPage } from '@/utils/playwright';

const topicSelector = 'tbody[id^="normalthread_"] a.xst';
const allowedResourceTypes = new Set(['document', 'script', 'stylesheet', 'xhr', 'fetch']);

function creationDate(raw: string): Date | undefined {
    const match = raw.match(/^(\d{2}|\d{4})-(\d{1,2})-(\d{1,2})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$/);
    if (!match) {
        return;
    }
    const [, year, month, day, hour = '00', minute = '00', second = '00'] = match;
    const fullYear = year.length === 2 ? `20${year}` : year;
    const value = `${fullYear}-${month.padStart(2, '0')}-${day.padStart(2, '0')}T${hour.padStart(2, '0')}:${minute}:${second}+08:00`;
    const date = parseDate(value);
    return Number.isNaN(date.getTime()) ? undefined : date;
}

async function forumHtml(link: string): Promise<string> {
    const helper = process.env.EDU_KINGDOM_BROWSER_HELPER;
    if (helper) {
        const result = await ofetch<{ status: string; message?: string; solution?: { status: number; response: string } }>(helper, {
            method: 'POST',
            body: { cmd: 'request.get', url: link, maxTimeout: 60000, ...(process.env.EDU_KINGDOM_BROWSER_SESSION ? { session: process.env.EDU_KINGDOM_BROWSER_SESSION } : {}) },
            timeout: 80000,
            retry: 0,
        });
        if (result.status !== 'ok' || result.solution?.status !== 200 || !result.solution.response) {
            throw new Error(`Forum browser helper failed: ${result.message || 'no usable page returned'}`);
        }
        return result.solution.response;
    }
    const { page, destroy } = await getPlaywrightPage(link, {
        closeTimeout: 0,
        gotoConfig: { waitUntil: 'domcontentloaded', timeout: 30000 },
        onBeforeLoad: async (page) => {
            await page.route('**/*', (requestRoute) => {
                return allowedResourceTypes.has(requestRoute.request().resourceType()) ? requestRoute.continue() : requestRoute.abort();
            });
        },
    });

    try {
        try {
            await page.waitForSelector(topicSelector, { state: 'attached', timeout: 20000 });
        } catch {
            throw new Error('Forum topics did not load. The host may be blocked by security verification, or the forum markup may have changed. No feed was generated.');
        }
        return await page.content();
    } finally {
        await destroy();
    }
}

export async function kingdomForum(ctx: Parameters<Route['handler']>[0], site: 'edu-kingdom' | 'baby-kingdom', defaultId: string, label: string) {
    const origin = `https://www.${site}.com`;
    const fid = ctx.req.param('fid') || defaultId;
    if (!/^\d+$/.test(fid)) {
        throw new Error('The forum ID must be numeric.');
    }
    const link = `${origin}/forum.php?mod=forumdisplay&fid=${fid}&filter=author&orderby=dateline`;
    const $ = load(await forumHtml(link));
    const topics = new Map<string, DataItem>();
    $('tbody[id^="normalthread_"]').each((_, row) => {
        const $row = $(row);
        // Discuz can place pinned topics inside normalthread rows as well.
        if ($row.find('img[id^="stick_"]').length) {
            return;
        }
        const id = $row.attr('id')?.match(/^normalthread_(\d+)$/)?.[1];
        const title = $row.find('a.xst').first().text();
        if (!id || !title) {
            return;
        }
        const authorCell = $row.find('td.by').first();
        const dateElement = authorCell.find('em').first();
        const rawDate = dateElement.find('[title]').first().attr('title') || dateElement.attr('title') || dateElement.text().trim();
        const topicLink = `${origin}/forum.php?mod=viewthread&tid=${id}`;
        topics.set(id, {
            title,
            link: topicLink,
            guid: topicLink,
            author: authorCell.find('cite').first().text().trim() || undefined,
            pubDate: creationDate(rawDate),
        });
    });
    if (topics.size === 0) {
        throw new Error('No unpinned topics found. Check the forum access and markup.');
    }
    // IDs represent topic creation, independent of the latest reply time.
    const items = [...topics.entries()].sort(([a], [b]) => Number(b) - Number(a)).map(([, item]) => item);
    return {
        title: `${label} · ${$('#threadlist h1').text().trim() || 'Forum ' + fid} · 新主題`,
        link,
        language: 'zh-HK',
        description: '新主題；回覆不產生新的訂閱項目。',
        item: items,
    };
}

