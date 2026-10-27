# Edu-Kingdom 小一選校 — new topics

**Live feed:** https://abc004108.github.io/edu-kingdom-feed/feed.xml

Verified on 27 October 2026: the public URL returned HTTP 200 with 30 unique topics and intact Chinese text. The complete GitHub-hosted collection and publishing job passed.

GitHub Actions starts RSSHub and a temporary FlareSolverr browser helper. The helper retrieves the public forum page; RSSHub turns it into RSS, and GitHub Pages hosts the validated XML. Your computer does not need to remain on. The helper image is pinned to the digest used in the successful access test, and the RSSHub source revision is pinned as well.

The workflow is scheduled around minutes 17 and 47 of each hour. GitHub can delay or skip scheduled runs. Each topic has a stable thread URL as its GUID and uses its creation date; replies do not create separate feed items. The initial feed includes the latest existing topics.

Earlier plain-browser cloud tests encountered security verification. The helper-based access test and full publishing run subsequently succeeded. This establishes current functionality, not a guarantee against future changes to the site's protection.

## Maintenance

- If a fetch or validation fails, publication stops and the last successful feed stays available. Check the Actions tab if the feed becomes stale.
- GitHub can disable scheduled workflows after 60 days without repository activity. Re-enable the workflow in Actions if this occurs.
- Only the latest forum page is collected. Long interruptions or high posting volume can cause missed topics.
- This setup uses a public repository, standard GitHub-hosted Ubuntu runners, and GitHub Pages. No paid host, paid proxy, or paid CAPTCHA service is configured.
- The helper is reachable only within the temporary runner/container network. No browser session cookies or personal credentials are stored in this repository.

Source: https://www.edu-kingdom.com/forum.php?mod=forumdisplay&fid=368

Successful publishing run: https://github.com/abc004108/edu-kingdom-feed/actions/runs/40424686682
