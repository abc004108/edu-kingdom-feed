from datetime import datetime
import tempfile
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

from collect_hongkongcard import HKT, collect, latest_replies, render, snapshot


def reply(number, tid=1):
    return {'id': number, 'thread_id': tid, 'created_at': f'2026-11-15 {number // 3600:02}:{number // 60 % 60:02}:{number % 60:02}',
            'content': '<p>Reply</p>', 'user': {'nickname': 'Reader'}}


class HongKongCardTests(unittest.TestCase):
    def test_latest_fifty_across_partial_last_page_and_deleted_replies(self):
        calls = []
        def fetch(path, **params):
            page = params['page']
            calls.append(page)
            # Listed page count can be stale after deleted posts.
            rows = [] if page > 3 else [reply(n) for n in range((page-1)*25+1, min(page*25, 57)+1)]
            return {'data': rows, 'meta': {'current_page': page, 'last_page': 3, 'per_page': 25}}
        got = latest_replies({'id': 1, 'total_page': 4}, 50, fetch)
        self.assertEqual(calls, [4, 3, 2, 1])
        self.assertEqual([r['id'] for r in got], list(range(57, 7, -1)))

    def test_rejects_wrong_topic_and_wrong_page(self):
        def fetch(path, **params):
            return {'data': [reply(1, 2)], 'meta': {'current_page': 1, 'last_page': 1, 'per_page': 25}}
        with self.assertRaisesRegex(ValueError, 'another topic'):
            latest_replies({'id': 1}, 50, fetch)

    def test_twenty_selected_before_sorting_and_original_timestamps(self):
        topics = [{'id': n, 'title': f'Topic {n}', 'created_at': '2026-11-01 00:00:00', 'total_page': 1,
                   'content': '<p>Original <img data-src="/image.jpg"><script>bad()</script></p>', 'user': {'nickname': 'Author'}} for n in range(1, 26)]
        def fetch(path, **params):
            if path.endswith('threads'):
                return {'data': topics}
            n = params['thread_id']
            return {'data': [reply(n, n)], 'meta': {'current_page': 1, 'last_page': 1, 'per_page': 25}}
        got = snapshot(20, 50, fetch)
        self.assertEqual([t['id'] for t, _, _ in got], list(range(20, 0, -1)))
        root = ET.fromstring(render(got, 'https://example.org', 50))
        first = root.find('channel/item')
        self.assertEqual(first.findtext('pubDate'), 'Sun, 15 Nov 2026 00:00:20 +0800')
        description = first.findtext('description')
        self.assertIn('2026-11-01 00:00:00 HKT', description)
        self.assertIn('https://www.hongkongcard.com/image.jpg', description)
        self.assertNotIn('bad()', description)
        self.assertIn('hongkongcard:thread:20', first.findtext('guid'))

    def test_new_reply_creates_new_entry_but_unchanged_polls_do_not(self):
        topic = {'id': 1, 'title': 'Original', 'created_at': '2026-11-01 12:34:56', 'content': '<p>Original body</p>'}
        def entry(replies):
            date = datetime(2026, 11, 15, tzinfo=HKT)
            return ET.fromstring(render([(topic, replies, date)], 'https://example.org', 50)).find('channel/item')
        original = entry([])
        first = entry([reply(1)])
        repeat = entry([reply(1)])
        changed_body = reply(1)
        changed_body['content'] = '<p>Edited reply</p>'
        edited = entry([changed_body])
        newer = reply(2)
        newer['created_at'] = reply(1)['created_at']  # Distinct replies can share a second.
        second = entry([reply(1), newer])
        self.assertEqual(original.findtext('guid'), 'hongkongcard:thread:1:original')
        self.assertEqual(first.findtext('guid'), 'hongkongcard:thread:1:reply:1')
        self.assertEqual(first.findtext('guid'), repeat.findtext('guid'))
        self.assertEqual(first.findtext('guid'), edited.findtext('guid'))
        self.assertEqual(second.findtext('guid'), 'hongkongcard:thread:1:reply:2')
        self.assertIn('Original body', second.findtext('description'))
        self.assertEqual(second.findtext('description').count('<h3>回覆 #'), 2)
        self.assertEqual(first.findtext('link'), second.findtext('link'))

    def test_failed_refresh_preserves_whole_valid_snapshot(self):
        topic = {'id': 1, 'title': 'Original', 'created_at': '2026-11-01 12:34:56', 'content': '<p>Body</p>'}
        saved = render([(topic, [], datetime(2026, 11, 1, 12, 34, 56, tzinfo=HKT))], 'https://example.org', 50)
        def fail(*args, **kwargs):
            raise ValueError('Source unavailable')
        with tempfile.TemporaryDirectory() as directory:
            result = collect({'topic_limit': 1, 'reply_limit': 50}, directory, 'https://example.org', fail, saved)
            self.assertEqual(result['state'], 'preserved')
            self.assertEqual(Path(directory, result['path']).read_bytes(), saved)


if __name__ == '__main__':
    unittest.main()
