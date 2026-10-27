import json
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
import tempfile
import unittest
from urllib.error import URLError
import xml.etree.ElementTree as ET

from collect_feeds import collect, load_config
from prepare_feed import render_feed, SITES


def fixture(fid, tid=123, site='edu-kingdom'):
    host = SITES[site][0]
    link = f'https://{host}/forum.php?mod=viewthread&amp;tid={tid}'
    return f'''<rss version="2.0"><channel><title>Source</title>
    <link>https://{host}/forum.php?mod=forumdisplay&amp;fid={fid}</link>
    <item><title>中文 &amp; school</title><link>{link}</link><guid>{link}</guid>
    <pubDate>Mon, 26 Oct 2026 00:00:00 GMT</pubDate></item></channel></rss>'''.encode()


class PublishingTests(unittest.TestCase):
    def test_all_sites_convert_feed_and_item_dates_to_hkt_without_changing_instants(self):
        for site in SITES:
            with self.subTest(site=site):
                source = ET.fromstring(fixture(27, site=site))
                channel = source.find('channel')
                ET.SubElement(channel, 'lastBuildDate').text = 'Tue, 27 Oct 2026 20:51:15 GMT'
                ET.SubElement(channel, 'pubDate').text = 'Tue, 27 Oct 2026 12:51:15 -0800'
                url = 'https://example.org/feed.xml'
                result = render_feed(ET.tostring(source), 27, 'Forum', url, site)
                output = ET.fromstring(result)
                self.assertEqual(output.findtext('channel/lastBuildDate'), 'Wed, 28 Oct 2026 04:51:15 +0800')
                self.assertEqual(output.findtext('channel/pubDate'), 'Wed, 28 Oct 2026 04:51:15 +0800')
                self.assertEqual(output.findtext('channel/item/pubDate'), 'Mon, 26 Oct 2026 08:00:00 +0800')
                self.assertEqual(parsedate_to_datetime(output.findtext('channel/lastBuildDate')), parsedate_to_datetime(channel.findtext('lastBuildDate')))
                self.assertEqual(output.findtext('channel/item/guid'), source.findtext('channel/item/guid'))
                self.assertEqual(render_feed(result, 27, 'Forum', url, site), result)

    def test_preserved_feeds_and_status_use_hkt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            forums = self.config(root, [{'id': 7, 'name': 'Forum', 'aliases': ['legacy.xml']}])
            def fetcher(url):
                if '/forum/' in url:
                    raise URLError('temporary source failure')
                return fixture(7)
            results = collect(forums, root / 'site', 'https://example.org', fetcher)
            self.assertEqual(results[0]['state'], 'preserved')
            for path in ['feeds/7.xml', 'legacy.xml']:
                self.assertTrue(ET.parse(root / 'site' / path).findtext('channel/item/pubDate').endswith('+0800'))
            status = json.loads((root / 'site/status.json').read_text(encoding='utf-8'))
            self.assertEqual(datetime.fromisoformat(status['checked_at']).utcoffset(), timedelta(hours=8))
            self.assertEqual(status['timezone'], 'Asia/Hong_Kong')

    def test_flyert_uses_own_route_and_import_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            forums = self.config(root, [{'site': 'flyert', 'id': 228, 'name': '海外用卡'}])
            calls = []
            def fetcher(url):
                calls.append(url)
                return fixture(228, site='flyert')
            collect(forums, root / 'site', 'https://example.org', fetcher)
            self.assertEqual(calls, ['http://127.0.0.1:1200/flyert/new-topics/228'])
            self.assertTrue((root / 'site/feeds/flyert/228.xml').exists())
            self.assertEqual(len(ET.parse(root / 'site/flyert.opml').findall('body/outline')), 1)
            with self.assertRaises(ValueError):
                render_feed(fixture(228), 228, 'Flyert', 'https://example.org/flyert.xml', 'flyert')

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
