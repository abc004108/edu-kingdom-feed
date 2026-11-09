import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from collect_x import accounts, collect, read_feed, render

def fixture(handle='TJ_Research', description='Post &amp; 中文', date='Mon, 09 Nov 2026 03:00:00 GMT'):
    return f'''<rss><channel><title>X</title><link>https://x.com/{handle}</link>
    <item><title>Post</title><description>{description}</description><link>https://twitter.com/{handle}/status/123</link><pubDate>{date}</pubDate></item></channel></rss>'''.encode()

class XTests(unittest.TestCase):
    def test_content_hkt_and_stable_guid(self):
        account = {'handle': 'TJ_Research'}
        posts = read_feed(fixture(), account['handle'])
        root = ET.fromstring(render(posts, account, 'https://example.org/feed.xml'))
        self.assertEqual(root.findtext('channel/item/description'), 'Post & 中文')
        self.assertEqual(root.findtext('channel/item/pubDate'), 'Mon, 09 Nov 2026 11:00:00 +0800')
        self.assertEqual(root.findtext('channel/item/guid'), 'x:status:123')
        self.assertEqual(root.findtext('channel/item/link'), 'https://x.com/TJ_Research/status/123')
        self.assertEqual(read_feed(ET.tostring(root), 'tj_research')['123']['description'], 'Post & 中文')

    def test_wrong_account_empty_missing_content_and_date_rejected(self):
        for source in [fixture('Other'), fixture(description=''), fixture(date='Mon, 09 Nov 2026 03:00:00'), b'<html>Login</html>']:
            with self.assertRaises((ValueError, TypeError)):
                read_feed(source, 'TJ_Research')

    def test_configuration_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, 'config.json')
            for values in [[{'handle': '../bad'}], [{'handle': 'TJ_Research'}, {'handle': 'tj_research'}], [{'handle': 'abc', 'include_replies': 'false'}]]:
                path.write_text(json.dumps({'accounts': values}))
                with self.assertRaises(ValueError):
                    accounts(path)

    def test_missing_auth_no_fake_feed_and_failure_preserves_posts(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / 'config.json'
            config.write_text(json.dumps({'accounts': [{'handle': 'TJ_Research'}]}))
            (root / 'status.json').write_text('{"forums": [1]}')
            def unavailable(url):
                raise OSError('Unavailable')
            collect(config, root, 'https://example.org', unavailable)
            status = json.loads((root / 'status.json').read_text())
            self.assertEqual(status['x'][0]['state'], 'missing_auth')
            self.assertFalse((root / 'feeds/x/tj_research.xml').exists())
            def fetcher(url):
                return fixture() if url.startswith('http://127.0.0.1:1200/twitter/user/') else unavailable(url)
            collect(config, root, 'https://example.org', fetcher, True)
            self.assertEqual(len(ET.parse(root / 'x.opml').findall('body/outline')), 1)
            def fallback(url):
                return (root / 'feeds/x/tj_research.xml').read_bytes() if url.startswith('https://example.org/') else unavailable(url)
            collect(config, root, 'https://example.org', fallback, True)
            self.assertEqual(json.loads((root / 'status.json').read_text())['x'][0]['state'], 'preserved')
            self.assertEqual(json.loads((root / 'status.json').read_text())['forums'], [1])

if __name__ == '__main__':
    unittest.main()
