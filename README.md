# Edu-Kingdom forum feeds

One GitHub Actions job updates all configured forums every four hours. It starts RSSHub and FlareSolverr once, creates one browser session, collects forums sequentially, and publishes the validated XML through GitHub Pages. Your PC can be off.

| Forum | ID | Feed |
| --- | --- | --- |
| 小一選校 | 368 | https://abc004108.github.io/edu-kingdom-feed/feeds/368.xml |
| 小學雜談 | 7 | https://abc004108.github.io/edu-kingdom-feed/feeds/7.xml |
| 二手市場 | 709 | https://abc004108.github.io/edu-kingdom-feed/feeds/709.xml |
| 中學交流 | 715 | https://abc004108.github.io/edu-kingdom-feed/feeds/715.xml |
| 幼校討論 | 6 | https://abc004108.github.io/edu-kingdom-feed/feeds/6.xml |

The original 小一選校 URL, https://abc004108.github.io/edu-kingdom-feed/feed.xml, stays available with the same item GUIDs. You do not need to change an existing subscription.

Import all subscriptions: https://abc004108.github.io/edu-kingdom-feed/subscriptions.opml

Last collection status: https://abc004108.github.io/edu-kingdom-feed/status.json

## Add a forum

Edit `forums.json` and add one entry to the `forums` array:

```json
{"id": 123, "name": "版塊名稱"}
```

Commit the change. The workflow collects it and publishes `feeds/123.xml`, and includes it in the OPML file. No route duplication or workflow editing is needed. Configuration changes reuse the cached RSSHub image; route changes rebuild it. Optional `aliases` are only needed when keeping an older feed URL, as for forum 368.

## Schedule and failure handling

Scheduled times in Hong Kong are approximately 00:17, 04:17, 08:17, 12:17, 16:17, and 20:17. GitHub may delay or skip a run. RSS feed TTL is 240 minutes.

Each thread is one RSS item, using its stable thread URL as the GUID and its creation date. Replies do not create separate items. The first subscription includes existing recent topics.

If one forum fails, the collector validates and preserves that forum's last published XML while updating the others. The status file reports `preserved`, and Actions shows a warning. If a new forum has never produced a valid feed, publication is stopped so the current site is not replaced by an incomplete set.

The latest page of each forum is collected. Long interruptions or more than a page of new topics between runs can cause missed topics. GitHub may disable schedules after 60 days without repository activity; re-enable the workflow in Actions if needed.

## Hosting

Public repository, standard GitHub-hosted Ubuntu runners, GitHub Pages, a cached RSSHub image, and a pinned FlareSolverr image. No paid host, proxy, or CAPTCHA service is configured. Browser sessions are destroyed when the temporary containers stop, and no personal credentials are stored.
