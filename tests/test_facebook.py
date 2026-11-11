import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from collect_facebook import collect, groups, read_feed, render, sanitize

GROUP = {'id': 'taiwaifestivalcity', 'resolved_id': '12345', 'public': True}

def fixture(group='12345', post='67890', description='Text &amp; 中文', date='Wed, 11 Nov 2026 03:00:00 GMT'):
    return f'''<rss><channel><title>Group</title><link>https://www.facebook.com/groups/{group}/</link><item>
    <title>Post</title><link>https://www.facebook.com/groups/{group}/permalink/{post}/</link>
    <description>{description}</description><pubDate>{date}</pubDate></item></channel></rss>'''.encode()

class FacebookTests(unittest.TestCase):
    def test_group_identity_content_hkt_and_alias_stable_guid(self):
        posts, title = read_feed(fixture(), GROUP)
        payload = render(posts, GROUP, title, 'https://example.org/feed.xml')
        root = ET.fromstring(payload)
        self.assertEqual(root.findtext('channel/item/pubDate'), 'Wed, 11 Nov 2026 11:00:00 +0800')
        self.assertEqual(root.findtext('channel/item/guid'), 'facebook:post:67890')
        self.assertEqual(root.findtext('channel/item/description'), 'Text &amp; 中文')
        saved, _ = read_feed(payload, {'id': GROUP['id']})
        self.assertEqual(saved['67890']['description'], posts['67890']['description'])

    def test_sanitizes_scripts_handlers_and_unsafe_links_preserving_media(self):
        body = sanitize('<p>Text</p><script>evil()</script><a href="javascript:evil()" onclick="bad()">link</a><img src="https://example.org/a.jpg" onerror="bad()"><video controls src="https://example.org/a.mp4"></video>')
        for bad in ['evil', 'onclick', 'onerror', 'javascript:', '<script']:
            self.assertNotIn(bad, body)
        self.assertIn('https://example.org/a.jpg', body)
        self.assertIn('https://example.org/a.mp4', body)

    def test_rejects_wrong_group_invalid_time_empty_content_and_login(self):
        for data in [fixture(group='99999'), fixture(description=''), fixture(description='&lt;p&gt;&lt;/p&gt;'), fixture(date='Wed, 11 Nov 2026 03:00:00'), b'<html>Log in</html>']:
            with self.assertRaises((ValueError, TypeError)):
                read_feed(data, GROUP)

    def test_public_configuration_is_required_and_ids_validated(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder, 'groups.json')
            for values in [[{'id': 'private'}], [{'id': '../bad', 'public': True}], [{'id': 'ok', 'public': True, 'numeric_id': 'oops'}]]:
                config.write_text(json.dumps({'groups': values}))
                with self.assertRaises(ValueError):
                    groups(config)

    def test_failed_initial_fetch_publishes_no_placeholder_then_preserves_valid_feed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / 'groups.json'
            config.write_text(json.dumps({'groups': [GROUP]}))
            (root / 'status.json').write_text('{"forums": [1], "x": [2]}')
            def failed(url):
                raise OSError('Login required')
            collect(config, root, 'https://example.org', failed, lambda g: '12345')
            path = root / 'feeds/facebook/taiwaifestivalcity.xml'
            self.assertFalse(path.exists())
            def good(url):
                return fixture() if url.startswith('http://127.0.0.1:1200/') else failed(url)
            collect(config, root, 'https://example.org', good, lambda g: '12345')
            self.assertEqual(len(ET.parse(root / 'facebook.opml').findall('body/outline')), 1)
            def previous(url):
                return path.read_bytes() if url.startswith('https://example.org/') else failed(url)
            collect(config, root, 'https://example.org', previous, lambda g: g['id'])
            status = json.loads((root / 'status.json').read_text())
            self.assertEqual(status['facebook'][0]['state'], 'preserved')
            self.assertEqual(status['forums'], [1])
            self.assertEqual(status['x'], [2])

if __name__ == '__main__':
    unittest.main()
