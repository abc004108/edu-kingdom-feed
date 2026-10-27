import type { Route } from '@/types';
import { kingdomForum } from '@/routes/edu-kingdom/utils';

export const route: Route = {
    path: '/forum/:fid?',
    name: '新主題',
    categories: ['bbs'],
    example: '/baby-kingdom/forum/27',
    parameters: { fid: { description: 'Forum ID', default: '27' } },
    maintainers: [],
    features: { requirePuppeteer: true, antiCrawler: true },
    description: 'Reads the first page ordered by topic creation, with permanent thread IDs and creation dates. Can use a locally networked FlareSolverr helper via EDU_KINGDOM_BROWSER_HELPER. Does not fetch replies or post bodies. Register a real maintainer before proposing this private route upstream.',
    handler: (ctx) => kingdomForum(ctx, 'baby-kingdom', '27', '親子王國'),
};
