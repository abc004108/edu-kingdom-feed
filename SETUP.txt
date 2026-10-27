# Edu-Kingdom and Baby-Kingdom forum feeds

One GitHub Actions job updates all nine forums every four hours. It starts RSSHub and FlareSolverr once, reuses a browser session, collects forums sequentially, and publishes validated XML through GitHub Pages. Your PC can be off.

| Site | Forum | Feed |
| --- | --- | --- |
| 教育王國 | 小一選校 | [368](https://abc004108.github.io/edu-kingdom-feed/feeds/368.xml) |
| 教育王國 | 小學雜談 | [7](https://abc004108.github.io/edu-kingdom-feed/feeds/7.xml) |
| 教育王國 | 二手市場 | [709](https://abc004108.github.io/edu-kingdom-feed/feeds/709.xml) |
| 教育王國 | 中學交流 | [715](https://abc004108.github.io/edu-kingdom-feed/feeds/715.xml) |
| 教育王國 | 幼校討論 | [6](https://abc004108.github.io/edu-kingdom-feed/feeds/6.xml) |
| 親子王國 | 二手市場 | [27](https://abc004108.github.io/edu-kingdom-feed/feeds/baby-kingdom/27.xml) |
| 親子王國 | 家庭理財 | [39](https://abc004108.github.io/edu-kingdom-feed/feeds/baby-kingdom/39.xml) |
| 親子王國 | 自由報料 | [19](https://abc004108.github.io/edu-kingdom-feed/feeds/baby-kingdom/19.xml) |
| 親子王國 | 齊齊著數 | [724](https://abc004108.github.io/edu-kingdom-feed/feeds/baby-kingdom/724.xml) |

Import [all nine subscriptions](https://abc004108.github.io/edu-kingdom-feed/subscriptions.opml), [Baby-Kingdom only](https://abc004108.github.io/edu-kingdom-feed/baby-kingdom.opml), or [Edu-Kingdom only](https://abc004108.github.io/edu-kingdom-feed/edu-kingdom.opml).

The original [feed.xml](https://abc004108.github.io/edu-kingdom-feed/feed.xml) remains an alias for Edu-Kingdom 368 with the same item GUIDs. [Collection status](https://abc004108.github.io/edu-kingdom-feed/status.json) reports each forum separately.

## Add a forum

Add an entry to `forums.json` and commit:

```json
{"site": "baby-kingdom", "id": 123, "name": "版塊名稱"}
```

Supported sites are `edu-kingdom` (the default when omitted) and `baby-kingdom`. Edu-Kingdom publishes at `feeds/ID.xml`; Baby-Kingdom at `feeds/baby-kingdom/ID.xml`. Forum IDs are unique within each site. The shared Discuz parser and browser transport are in `routes/edu-kingdom/utils.ts`; the two namespaces supply the site and label. Configuration changes reuse the cached RSSHub image; route changes rebuild it. No workflow edits are needed to add forums on either site.

## Schedule and failure handling

Runs are scheduled approximately 00:17, 04:17, 08:17, 12:17, 16:17, and 20:17 Hong Kong time. GitHub may delay or skip runs. RSS TTL is 240 minutes. Each thread uses its permanent URL as GUID. Replies do not create separate items. Only topic titles, authors, creation dates where available, and links are collected.

If a forum fails, its last validated published feed is preserved while other forums update. Validation checks both site and forum ID. If a newly added forum has never produced a valid feed, publication stops and keeps the existing site intact.

Only the latest page is collected; more than a page of new topics between runs or long interruptions can cause missed topics. The first subscription includes the current recent topics. GitHub may disable schedules after 60 days without repository activity; re-enable the workflow in Actions if needed.

## Hosting

This uses a public repository, standard GitHub-hosted Ubuntu runners, GitHub Pages, a cached RSSHub image, and a pinned FlareSolverr image. No paid host, proxy, or CAPTCHA service is configured. Browser sessions are temporary; no personal credentials are stored. Source security checks may change and future access is not guaranteed.
