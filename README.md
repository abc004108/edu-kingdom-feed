# Edu-Kingdom 小一選校 — new topics

RSSHub generates a feed of newly created topics in forum 368. GitHub Actions runs the collector in the cloud, and GitHub Pages hosts the resulting XML. Your computer does not need to remain on.

Feed address after the first successful deployment: https://abc004108.github.io/edu-kingdom-feed/feed.xml

The workflow runs around minutes 17 and 47 of each hour. GitHub can delay or skip scheduled runs. Each topic has a stable thread URL as its GUID and uses its creation date; replies do not create separate feed items. The initial feed includes the latest existing topics.

The first run builds RSSHub plus Chromium from the pinned source revision. Later runs restore a cached image. A failed fetch or invalid response stops publication, preserving the last successfully published feed.

## Maintenance

- Check the Actions tab if the feed stops updating. The forum may challenge GitHub-hosted requests even when a previous run succeeded.
- GitHub can disable scheduled workflows after 60 days without repository activity. Re-enable the workflow in Actions if this occurs.
- Only the latest forum page is collected. Long interruptions or high posting volume can cause missed topics.
- This setup uses a public repository, standard GitHub-hosted Ubuntu runners, and GitHub Pages. No paid host or container registry is configured.

Source: https://www.edu-kingdom.com/forum.php?mod=forumdisplay&fid=368
