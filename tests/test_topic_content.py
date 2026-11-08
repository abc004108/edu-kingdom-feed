from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from topic_times import TopicTimes
from topic_content import TopicContent, original_content
from test_publishing import fixture

LINK = 'https://www.baby-kingdom.com/forum.php?mod=viewthread&tid=123'
HTML = '''<em id="authorposton42">2026-11-08 12:34</em>
<td id="postmessage_42"><div class="pstatus">Edited yesterday</div>
Original &amp; 中文<br><div class="quote">Quoted reply</div>
<img file="/images/photo.jpg" onerror="bad()"><script>bad()</script><p>Second paragraph</p></td>
<em id="authorposton43">2026-11-08 13:00</em><td id="postmessage_43">Reply body</td>'''


class ContentTests(unittest.TestCase):
    def test_original_only_safe_markup_and_lazy_image(self):
        body = original_content(HTML, LINK)
        self.assertIn('Original &amp; 中文', body)
        self.assertIn('Second paragraph', body)
        self.assertIn('https://www.baby-kingdom.com/images/photo.jpg', body)
        for excluded in ['Quoted reply', 'Reply body', 'bad()', 'onerror', 'Edited yesterday']:
            self.assertNotIn(excluded, body)

    def test_restricted_or_missing_original_never_uses_reply(self):
        for html in ['<td id="postmessage_42">No header</td>',
                     '<em id="authorposton42"></em><td id="postmessage_43">Reply only</td>',
                     '<em id="authorposton42"></em><td id="postmessage_42"><div class="locked">Login required</div></td>']:
            with self.assertRaises(ValueError):
                original_content(html, LINK)

    def test_reuses_timestamp_page_and_persistent_cache_preserving_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            times = TopicTimes(Path(folder, 'times.json'), lambda link: self.fail('Already fetched'))
            times.pages[LINK] = HTML
            cache = Path(folder, 'content.json')
            resolver = TopicContent(times, cache)
            source = fixture(27, site='baby-kingdom')
            result, count = resolver.enrich(source)
            self.assertEqual(count, 1)
            before, after = ET.fromstring(source), ET.fromstring(result)
            for key in ['title', 'link', 'guid', 'pubDate']:
                self.assertEqual(before.findtext('channel/item/' + key), after.findtext('channel/item/' + key))
            times.pages.clear()
            saved = TopicContent(times, cache)
            self.assertEqual(saved.resolve(LINK), resolver.values[LINK])

    def test_failure_preserves_existing_description(self):
        with tempfile.TemporaryDirectory() as folder:
            times = TopicTimes(Path(folder, 'times.json'), lambda link: '<html>blocked</html>')
            resolver = TopicContent(times, Path(folder, 'content.json'))
            root = ET.fromstring(fixture(27, site='baby-kingdom'))
            ET.SubElement(root.find('channel/item'), 'description').text = 'Previously saved content'
            result, count = resolver.enrich(ET.tostring(root))
            self.assertEqual(count, 0)
            self.assertEqual(ET.fromstring(result).findtext('channel/item/description'), 'Previously saved content')


if __name__ == '__main__':
    unittest.main()
