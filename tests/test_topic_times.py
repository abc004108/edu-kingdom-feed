from datetime import timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import xml.etree.ElementTree as ET

from topic_times import TopicTimes, original_time
from test_publishing import fixture


class OriginalTimeTests(unittest.TestCase):
    def test_flyert_direct_gbk_html_avoids_browser(self):
        with tempfile.TemporaryDirectory() as tmp:
            response = MagicMock()
            response.headers.get_content_charset.return_value = 'gbk'
            response.read.return_value = '<em id="authorposton1">发表于 2026-10-27 18:19:42</em>'.encode('gbk')
            response.__enter__.return_value = response
            resolver = TopicTimes(Path(tmp, 'times.json'), lambda link: self.fail('Direct HTML should suffice'))
            with patch('topic_times.urlopen', return_value=response), patch('topic_times.time.sleep'):
                date = resolver.resolve('https://www.flyert.com.cn/forum.php?mod=viewthread&tid=123')
            self.assertEqual(date.isoformat(), '2026-10-27T18:19:42+08:00')

    def test_first_post_beats_reply_and_edit_times(self):
        html = '''<div>Last edited 2026-10-28 20:10</div>
        <em id="authorposton123">發表於 <span title="2026-10-27 18:19:42">8 分鐘前</span></em>
        <em id="authorposton124">2026-10-28 01:00:00</em>'''
        date = original_time(html)
        self.assertEqual(date.isoformat(), '2026-10-27T18:19:42+08:00')

    def test_real_midnight_is_valid_but_date_only_is_not(self):
        self.assertEqual(original_time('<em id="authorposton1">发表于 26-10-27 00:00</em>').hour, 0)
        with self.assertRaises(ValueError):
            original_time('<em id="authorposton1">2026-10-27</em><div>reply 2026-10-27 18:19</div>')

    def test_cache_is_reused_and_guid_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, 'times.json')
            calls = []
            def fetcher(link):
                calls.append(link)
                return '<em id="authorposton1">發表於 2026-10-27 18:19</em>'
            resolver = TopicTimes(path, fetcher)
            raw = fixture(27, site='baby-kingdom')
            enriched, count = resolver.enrich(raw)
            root = ET.fromstring(enriched)
            self.assertEqual(count, 1)
            self.assertEqual(root.findtext('channel/item/guid'), ET.fromstring(raw).findtext('channel/item/guid'))
            self.assertEqual(parsedate_to_datetime(root.findtext('channel/item/pubDate')).utcoffset(), timedelta(hours=8))
            second = TopicTimes(path, lambda link: self.fail('Cached topics must not be requested again'))
            self.assertEqual(second.enrich(raw)[1], 1)
            self.assertEqual(len(calls), 1)

    def test_unavailable_time_omits_placeholder_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            resolver = TopicTimes(Path(tmp, 'times.json'), lambda link: '<html>Security verification</html>')
            data, count = resolver.enrich(fixture(27, site='baby-kingdom'))
            self.assertEqual(count, 0)
            self.assertIsNone(ET.fromstring(data).find('channel/item/pubDate'))
