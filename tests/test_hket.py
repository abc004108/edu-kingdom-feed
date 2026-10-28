from email.utils import parsedate_to_datetime
import json
import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

from hket_feed import Page, SOURCE, article_url, collect, parse_article, read_previous, render


def fixture(**changes):
    data = {'@type': 'NewsArticle', 'headline': '中文 & news', 'description': 'Public <summary> & details',
            'mainEntityOfPage': 'https://inews.hket.com/article/4215852/title',
            'datePublished': '2026-10-28T14:58:39.295+08:00', 'dateModified': '2026-10-28T19:00:00+08:00'}
    data.update(changes)
    return '<script type="application/ld+json">' + json.dumps({'@graph': [data]}) + '</script>'


class HketTests(unittest.TestCase):
    def test_original_publication_not_modified_and_safe_summary_roundtrip(self):
        article = parse_article(fixture(), 'https://inews.hket.com/article/4215852')
        root = ET.fromstring(render([article], 'https://example.org/feed.xml'))
        self.assertEqual(root.findtext('channel/item/pubDate'), 'Wed, 28 Oct 2026 14:58:39 +0800')
        self.assertEqual(root.findtext('channel/item/description'), 'Public <summary> & details')
        self.assertEqual(root.findtext('channel/item/guid'), article['link'])
        saved = read_previous(ET.tostring(root))
        self.assertEqual(saved[article['link']]['description'], article['description'])

    def test_rejects_date_only_naive_missing_description_and_wrong_article(self):
        for changes in [{'datePublished': '2026-10-28'}, {'datePublished': '2026-10-28T12:00:00'},
                        {'description': ''}, {'mainEntityOfPage': 'https://inews.hket.com/article/999'}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                parse_article(fixture(**changes), 'https://inews.hket.com/article/4215852')

    def test_timezone_conversion_and_midnight_are_real_instants(self):
        article = parse_article(fixture(datePublished='2026-10-27T16:00:00Z'), 'https://inews.hket.com/article/4215852')
        self.assertEqual(article['published'], '2026-10-28T00:00:00+08:00')

    def test_listing_uses_unique_share_urls_and_filters_external_links(self):
        html = '''<button class="share-button" data-url="https://ps.hket.com/article/123"></button>
        <button class="share-button" data-url="https://ps.hket.com/article/123/title?mtc=1"></button>
        <button class="share-button" data-url="https://evil.example/article/123"></button>'''
        self.assertEqual(Page(html).links, ['https://ps.hket.com/article/123'])
        for value in ['https://hket.com.evil.example/article/1', 'https://evil-hket.com/article/1',
                      'http://inews.hket.com/article/1', 'https://inews.hket.com/not-an-article']:
            with self.assertRaises(ValueError):
                article_url(value)

    def test_saved_feed_cannot_be_another_site_or_empty(self):
        for content in ['<rss><channel><link>https://example.org</link></channel></rss>',
                        f'<rss><channel><link>{SOURCE}</link></channel></rss>']:
            with self.assertRaises(ValueError):
                read_previous(content)

    def test_collection_retains_history_on_outage_and_opml_is_idempotent(self):
        link = 'https://inews.hket.com/article/4215852'
        with tempfile.TemporaryDirectory() as folder, patch('hket_feed.urlopen', side_effect=OSError('offline')):
            root = Path(folder)
            (root / 'status.json').write_text('{"forums": []}', encoding='utf-8')
            (root / 'subscriptions.opml').write_text('<opml><head/><body/></opml>', encoding='utf-8')
            cache = root / 'cache.json'
            def fetch(url):
                return fixture() if '/article/' in url else f'<button class="share-button" data-url="{link}"></button>'
            collect(root, 'https://example.org', cache, fetch)
            def offline(url):
                raise OSError('blocked')
            collect(root, 'https://example.org', cache, offline)
            published = ET.parse(root / 'feeds/hket/inews.xml')
            self.assertEqual(len(published.findall('channel/item')), 1)
            self.assertEqual(published.findtext('channel/item/description'), 'Public <summary> & details')
            self.assertEqual(len(ET.parse(root / 'subscriptions.opml').findall('body/outline')), 1)
            status = json.loads((root / 'status.json').read_text(encoding='utf-8'))
            self.assertEqual(status['news'][0]['state'], 'preserved')
            self.assertEqual(status['forums'], [])


if __name__ == '__main__':
    unittest.main()
