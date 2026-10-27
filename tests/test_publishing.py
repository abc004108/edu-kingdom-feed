import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import URLError
import xml.etree.ElementTree as ET

from collect_feeds import collect, load_config
from prepare_feed import render_feed


def fixture(fid, tid=123, site='edu-kingdom'):
    link = f'https://www.{site}.com/forum.php?mod=viewthread&amp;tid={tid}'
    return f'''<rss version="2.0"><channel><title>Source</title>
    <link>https://www.{site}.com/forum.php?mod=forumdisplay&amp;fid={fid}</link>
    <item><title>中文 &amp; school</title><link>{link}</link><guid>{link}</guid>
    <pubDate>Mon, 26 Oct 2026 00:00:00 GMT</pubDate></item></channel></rss>'''.encode()


class PublishingTests(unittest.TestCase):
    def test_same_forum_id_on_two_sites_has_distinct_feeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            forums = self.config(root, [{'id': 27, 'name': 'Edu'}, {'site': 'baby-kingdom', 'id': 27, 'name': '二手市場'}])
            def fetcher(url):
                return fixture(27, site='baby-kingdom' if '/baby-kingdom/' in url else 'edu-kingdom')
            results = collect(forums, root / 'site', 'https://example.org', fetcher)
            self.assertTrue(all(r['state'] == 'updated' for r in results))
            self.assertTrue((root / 'site/feeds/27.xml').exists())
            baby = ET.parse(root / 'site/feeds/baby-kingdom/27.xml')
            self.assertIn('www.baby-kingdom.com', baby.findtext('channel/item/guid'))
            self.assertEqual(len(ET.parse(root / 'site/baby-kingdom.opml').findall('body/outline')), 1)

    def test_other_site_feed_is_rejected_even_when_forum_id_matches(self):
        with self.assertRaises(ValueError):
            render_feed(fixture(27), 27, 'Baby', 'https://example.org/baby.xml', 'baby-kingdom')

    def config(self, root, forums):
        path = root / 'forums.json'
        path.write_text(json.dumps({'forums': forums}), encoding='utf-8')
        return load_config(path)

    def test_wrong_forum_cannot_be_published_under_another_subscription(self):
        with self.assertRaises(ValueError):
            render_feed(fixture(368), 7, 'School', 'https://example.org/feeds/7.xml')

    def test_multiple_feeds_keep_legacy_guid_and_opml(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            forums = self.config(root, [{'id': 368, 'name': '小一選校', 'aliases': ['feed.xml']}, {'id': 7, 'name': '小學雜談'}])
            results = collect(forums, root / 'site', 'https://example.org', lambda url: fixture(url.rsplit('/', 1)[-1]))
            self.assertTrue(all(r['state'] == 'updated' for r in results))
            legacy = ET.parse(root / 'site/feed.xml')
            canonical = ET.parse(root / 'site/feeds/368.xml')
            self.assertEqual(legacy.findtext('channel/item/guid'), canonical.findtext('channel/item/guid'))
            self.assertEqual(legacy.findtext('channel/ttl'), '240')
            self.assertEqual(len(ET.parse(root / 'site/subscriptions.opml').findall('body/outline')), 2)

    def test_one_failed_forum_retains_old_feed_while_other_updates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            forums = self.config(root, [{'id': 368, 'name': 'A'}, {'id': 7, 'name': 'B'}])
            def fetcher(url):
                if url.endswith('/forum/7'):
                    raise URLError('temporary source failure')
                return fixture(7, 70) if '/feeds/7.xml' in url else fixture(368, 369)
            results = collect(forums, root / 'site', 'https://example.org', fetcher)
            self.assertEqual([r['state'] for r in results], ['updated', 'preserved'])
            self.assertIn('tid=70', ET.parse(root / 'site/feeds/7.xml').findtext('channel/item/guid'))

    def test_missing_initial_forum_does_not_write_partial_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            forums = self.config(root, [{'id': 368, 'name': 'A'}, {'id': 7, 'name': 'B'}])
            def fetcher(url):
                if url.endswith('/forum/368'):
                    return fixture(368)
                raise URLError('blocked')
            with self.assertRaises(RuntimeError):
                collect(forums, root / 'site', 'https://example.org', fetcher)
            self.assertFalse((root / 'site').exists())

    def test_config_rejects_ambiguous_ids_and_unsafe_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for forums in [[{'id': 7, 'name': 'A'}, {'id': 7, 'name': 'B'}], [{'id': 7, 'name': 'A', 'aliases': ['../feed.xml']}]]:
                with self.assertRaises(ValueError):
                    self.config(root, forums)


if __name__ == '__main__':
    unittest.main()
