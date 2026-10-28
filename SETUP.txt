# Edu-Kingdom, Baby-Kingdom, and Flyert forum feeds

One GitHub Actions job updates all thirteen forums every four hours. It starts RSSHub and FlareSolverr once, reuses a browser session, collects forums sequentially, and publishes validated XML through GitHub Pages. Your PC can be off.

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
| 飞客 | 海外用卡 | [228](https://abc004108.github.io/edu-kingdom-feed/feeds/flyert/228.xml) |
| 飞客 | IHG优悦会 | [23](https://abc004108.github.io/edu-kingdom-feed/feeds/flyert/23.xml) |
| 飞客 | 万豪旅享家 | [63](https://abc004108.github.io/edu-kingdom-feed/feeds/flyert/63.xml) |
| 飞客 | 用卡热点 | [59](https://abc004108.github.io/edu-kingdom-feed/feeds/flyert/59.xml) |

Import [all fourteen subscriptions](https://abc004108.github.io/edu-kingdom-feed/subscriptions.opml), [Baby-Kingdom only](https://abc004108.github.io/edu-kingdom-feed/baby-kingdom.opml), [Flyert only](https://abc004108.github.io/edu-kingdom-feed/flyert.opml), or [Edu-Kingdom only](https://abc004108.github.io/edu-kingdom-feed/edu-kingdom.opml).

The original [feed.xml](https://abc004108.github.io/edu-kingdom-feed/feed.xml) remains an alias for Edu-Kingdom 368 with the same item GUIDs. [Collection status](https://abc004108.github.io/edu-kingdom-feed/status.json) reports each forum separately.

## Add a forum

Add an entry to `forums.json` and commit:

```json
{"site": "baby-kingdom", "id": 123, "name": "版塊名稱"}
```

Supported sites are `edu-kingdom` (the default when omitted) `baby-kingdom`, and `flyert`. Edu-Kingdom publishes at `feeds/ID.xml`; Baby-Kingdom at `feeds/baby-kingdom/ID.xml`; Flyert at `feeds/flyert/ID.xml`. Forum IDs are unique within each site. The shared Discuz parser and browser transport are in `routes/edu-kingdom/utils.ts`; the two namespaces supply the site and label. Configuration changes reuse the cached RSSHub image; route changes rebuild it. No workflow edits are needed to add forums on any supported site.

## Schedule and failure handling

Runs are scheduled approximately 00:17, 04:17, 08:17, 12:17, 16:17, and 20:17 Hong Kong time. GitHub may delay or skip runs. RSS TTL is 240 minutes. Each thread uses its permanent URL as GUID. Replies do not create separate items. Only topic titles, authors, creation dates where available, and links are collected.

All RSS `lastBuildDate` and `pubDate` timestamps use Hong Kong time with the standard numeric offset `+0800`. The conversion preserves the original instant, including when a saved feed is reused. `status.json` uses ISO timestamps with `+08:00` and identifies the timezone as `Asia/Hong_Kong`.

Item publication times are verified from the original first post on page 1, in oldest-first order. The publisher caches these timestamps by permanent thread URL across Actions runs, so each topic normally needs one additional page request. Replies and edit timestamps are excluded. If the original time cannot be verified, that item's `pubDate` is omitted instead of substituting midnight; status reports `original_times` and `undated_items`. The first run backfills the current topics and takes longer. The feeds contain titles and links, not copied post bodies.

If a forum fails, its last validated published feed is preserved while other forums update. Validation checks both site and forum ID. If a newly added forum has never produced a valid feed, publication stops and keeps the existing site intact.

Only the latest page is collected; more than a page of new topics between runs or long interruptions can cause missed topics. The first subscription includes the current recent topics. GitHub may disable schedules after 60 days without repository activity; re-enable the workflow in Actions if needed.

## Hosting

This uses a public repository, standard GitHub-hosted Ubuntu runners, GitHub Pages, a cached RSSHub image, and a pinned FlareSolverr image. No paid host, proxy, or CAPTCHA service is configured. Browser sessions are temporary; no personal credentials are stored. Source security checks may change and future access is not guaranteed.


## Flyert route

The separate `routes/flyert/new-topics.ts` route uses the supplied `filter=lastpost&orderby=dateline` query. Topic creation order comes from `orderby=dateline`; item identity is the permanent thread URL. It reads only unpinned `normalthread` rows, uses original-author dates instead of latest-reply dates, and decodes the source's GBK encoding. It requests the public list directly, with the shared browser helper as a fallback. It does not fetch individual post bodies. The existing upstream Flyert routes are retained.

For example, add `{"site": "flyert", "id": 228, "name": "海外用卡"}` to the forum configuration. The RSSHub path is `/flyert/new-topics/228`; the published file is `feeds/flyert/228.xml`. Import `flyert.opml` for the four Flyert subscriptions, or `subscriptions.opml` for all fourteen.

## HKET instant news

Subscribe to https://abc004108.github.io/edu-kingdom-feed/feeds/hket/inews.xml or import hket.opml. The shared four-hour Actions job runs hket_feed.py alongside the forum RSSHub collector, using the same temporary guest browser session. HKET summaries come from public NewsArticle description metadata; pubDate comes strictly from datePublished, never dateModified or collection time. All dates use HKT (+0800). No article body or subscriber-only content is collected.

The first run seeds up to three listing pages. Later runs walk up to twenty pages, stopping after a page of already-known articles, with a ten-minute collection budget. The latest 500 verified articles are retained across runs using both Actions cache and the previously published feed. Missing metadata and request errors are reported under news in status.json; valid saved articles remain available. A first run with no valid articles stops publication. Busy periods, prolonged outages, pagination changes, or the collection budget can still cause gaps.
