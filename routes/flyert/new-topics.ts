import { load } from 'cheerio';
import iconv from 'iconv-lite';

import type { DataItem, Route } from '@/types';
import got from '@/utils/got';
import { creationDate, forumHtml } from '@/routes/edu-kingdom/utils';

const origin = 'https://www.flyert.com.cn';
const topicSelector = 'tbody[id^="normalthread_"] .comiis_common a[data-track$="文章"]';

export function parseTopics(html: string) {
    const $ = load(html);
    const topics = new Map<string, DataItem>();
    $('tbody[id^="normalthread_"]').each((_, row) => {
        const $row = $(row);
        if ($row.find('img[id^="stick_"], .comiis_top').length) {
            return;
        }
        const id = $row.attr('id')?.match(/^normalthread_(\d+)$/)?.[1];
        const anchor = $row.find('.comiis_common a[data-track$="文章"]').first();
        const title = anchor.text().trim();
        if (!id || !title) {
            return;
        }
        const source = new URL(anchor.attr('href') || '', origin);
        if (source.hostname !== 'www.flyert.com.cn' || source.searchParams.get('tid') !== id) {
            return;
        }
        // Use the original author/date, never the poster/latest-reply column.
        const dateElement = $row.find('.author .author_b').first();
        const rawDate = dateElement.find('[title]').first().attr('title') || dateElement.attr('title') || dateElement.text().trim();
        const link = `${origin}/forum.php?mod=viewthread&tid=${id}`;
        topics.set(id, {
            title,
            link,
            guid: link,
            author: $row.find('.author .author_t').first().text().trim() || undefined,
            pubDate: creationDate(rawDate),
        });
    });
    return [...topics.entries()].sort(([a], [b]) => Number(b) - Number(a)).map(([, item]) => item);
}

async function handler(ctx: Parameters<Route['handler']>[0]) {
    const fid = ctx.req.param('fid') || '228';
    if (!/^\d+$/.test(fid)) {
        throw new Error('The forum ID must be numeric.');
    }
    const link = `${origin}/forum.php?mod=forumdisplay&fid=${fid}&filter=lastpost&orderby=dateline`;
    let html: string;
    let items: DataItem[];
    try {
        const response = await got(link, { responseType: 'buffer', timeout: { request: 30000 }, retry: { limit: 0 } });
        html = iconv.decode(response.data, 'gbk');
        items = parseTopics(html);
        if (!items.length || html.includes('\uFFFD')) {
            throw new Error('Direct request did not return usable topics');
        }
    } catch {
        html = await forumHtml(link, topicSelector);
        items = parseTopics(html);
    }
    if (!items.length) {
        throw new Error('No Flyert topics found. Check forum access and markup.');
    }
    const $ = load(html);
    return {
        title: `飞客 · ${$('h1').first().text().trim() || 'Forum ' + fid} · 新主题`,
        link,
        language: 'zh-CN',
        description: '按发帖时间排序的新主题；回复不产生新的订阅项目。',
        item: items,
    };
}

export const route: Route = {
    path: '/new-topics/:fid?',
    name: '新主题',
    categories: ['bbs'],
    example: '/flyert/new-topics/228',
    parameters: { fid: { description: 'Forum ID', default: '228' } },
    maintainers: [],
    features: { requirePuppeteer: true, antiCrawler: true },
    description: 'Reads the public forum list ordered by topic creation. Decodes GBK, excludes pinned rows, and uses stable thread IDs. Does not fetch post bodies or replies. Falls back to the configured local browser helper if required. Register a real maintainer before proposing this private route upstream.',
    handler,
};
