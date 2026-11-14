import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse
from original_post import first_page_url, original_pid
from topic_content import original_content, TopicContent
from topic_times import original_time, TopicTimes

LINK = 'https://www.flyert.com.cn/forum.php?mod=viewthread&tid=123'
HTML = '''<a id="postnum900">99<sup>#</sup></a><em id="authorposton900">2026-11-14 22:00</em>
<td id="postmessage_900">Latest reply must never enter feed</td>
<a id="postnum100" title="Jump to floor"><em>1</em><sup>#</sup></a>
<em id="authorposton100">2026-11-10 09:15</em><td id="postmessage_100">Actual original post</td>'''

class FirstPostTests(unittest.TestCase):
    def test_chooses_floor_one_even_when_latest_reply_is_displayed_first(self):
        self.assertEqual(original_pid(HTML, strict=True), '100')
        self.assertEqual(original_content(HTML, LINK), '<div>Actual original post</div>')
        self.assertEqual(original_time(HTML, strict=True).day, 10)
        self.assertEqual(original_time(HTML, strict=True).hour, 9)

    def test_refuses_reply_only_page(self):
        html = HTML[:HTML.index('<a id="postnum100"')]
        with self.assertRaises(ValueError):
            original_content(html, LINK)
        with self.assertRaises(ValueError):
            original_time(html, strict=True)

    def test_url_removes_lastpost_and_author_filters_and_reverse_order(self):
        url = first_page_url(LINK + '&page=8&ordertype=1&authorid=222&goto=lastpost#lastpost')
        self.assertEqual(parse_qs(urlparse(url).query), {'mod':['viewthread'], 'tid':['123'], 'page':['1'], 'ordertype':['2']})
        self.assertFalse(urlparse(url).fragment)

    def test_migration_invalidates_wrong_flyert_content_and_time_once(self):
        with tempfile.TemporaryDirectory() as folder:
            times_path, content_path = Path(folder, 'times.json'), Path(folder, 'content.json')
            other = 'https://www.baby-kingdom.com/forum.php?mod=viewthread&tid=123'
            times_path.write_text(json.dumps({LINK:'2026-11-14T22:00:00+08:00', other:'2026-11-10T09:15:00+08:00'}))
            content_path.write_text(json.dumps({LINK:'Wrong reply', other:'Good content'}))
            times = TopicTimes(times_path, lambda link: HTML)
            content = TopicContent(times, content_path)
            self.assertNotIn(LINK, times.values)
            self.assertNotIn(LINK, content.values)
            self.assertEqual(content.values[other], 'Good content')
            self.assertEqual(times.resolve(LINK).day, 10)
            self.assertEqual(content.resolve(LINK), '<div>Actual original post</div>')
            self.assertIn(LINK, TopicTimes(times_path).values)

if __name__ == '__main__':
    unittest.main()
