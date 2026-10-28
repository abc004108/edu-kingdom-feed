"""Publish HKET's public article summaries and original publication times."""
from datetime import datetime
from email.utils import format_datetime, parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlparse, quote
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from prepare_feed import HKT

SOURCE = 'https://inews.hket.com/sran001/' + quote('全部')
FEED_PATH = 'feeds/hket/inews.xml'
TITLE = '香港經濟日報 · 即時新聞 · 全部'


def article_url(value):
    url = urlparse(value)
    match = re.match(r'^/article/(\d+)(?:/|$)', url.path)
    if url.scheme != 'https' or not (url.hostname or '').endswith('.hket.com') or url.port or url.username or not match:
        raise ValueError('Unexpected HKET article URL')
    return f'https://{url.hostname}/article/{match[1]}'


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links, self.meta, self.scripts = [], {}, []
        self.script = None
        self.feed(html)

    def handle_starttag(self, tag, pairs):
        attrs = dict(pairs)
        if tag == 'meta':
            self.meta[attrs.get('property', attrs.get('name', ''))] = attrs.get('content', '')
        if tag == 'script' and attrs.get('type') == 'application/ld+json':
            self.script = ''
        if tag == 'button' and 'share-button' in attrs.get('class', '').split():
            try:
                link = article_url(attrs.get('data-url', ''))
                if link not in self.links:
                    self.links.append(link)
            except ValueError:
                pass

    def handle_data(self, text):
        if self.script is not None:
            self.script += text

    def handle_endtag(self, tag):
        if tag == 'script' and self.script is not None:
            try:
                self.scripts.append(json.loads(self.script))
            except json.JSONDecodeError:
                pass
            self.script = None


def nodes(value):
    if isinstance(value, list):
        for item in value:
            yield from nodes(item)
    elif isinstance(value, dict):
        yield value
        yield from nodes(value.get('@graph', []))


def parse_article(html, link):
    page = Page(html)
    for obj in nodes(page.scripts):
        types = obj.get('@type', [])
        if isinstance(types, str):
            types = [types]
        if not {'NewsArticle', 'Article', 'ReportageNewsArticle'} & set(types):
            continue
        # Infinite-scroll pages may contain metadata for additional articles.
        entity = obj.get('mainEntityOfPage', obj.get('url', ''))
        if isinstance(entity, dict):
            entity = entity.get('@id', '')
        if entity and article_url(entity) != article_url(link):
            continue
        published = obj.get('datePublished', '')
        if not re.search(r'T\d{2}:\d{2}', published):
            raise ValueError('Original publication time missing')
        date = datetime.fromisoformat(published.replace('Z', '+00:00'))
        if date.tzinfo is None:
            raise ValueError('Publication timezone missing')
        title = unescape(obj.get('headline', '')).strip()
        description = unescape(obj.get('description') or page.meta.get('og:description') or page.meta.get('description', '')).strip()
        if not title or not description or '\ufffd' in title + description:
            raise ValueError('Article title or public summary missing')
        return {'link': article_url(link), 'title': title, 'description': description,
                'published': date.astimezone(HKT).isoformat()}
    raise ValueError('Article publication metadata not found')


def browser_html(url):
    body = json.dumps({'cmd': 'request.get', 'url': url, 'session': 'edu-kingdom-feed', 'maxTimeout': 15000}).encode()
    request = Request('http://127.0.0.1:8191/v1', data=body, headers={'Content-Type': 'application/json'})
    with urlopen(request, timeout=22) as response:
        result = json.load(response)
    solution = result.get('solution', {})
    if result.get('status') != 'ok' or solution.get('status') != 200:
        raise ValueError(f"HKET browser request failed: {solution.get('status')} {result.get('message', '')}")
    return solution.get('response', '')


def render(articles, feed_url):
    rss = ET.Element('rss', version='2.0')
    channel = ET.SubElement(rss, 'channel')
    for key, value in [('title', TITLE), ('link', SOURCE), ('description', '即時新聞公開摘要及原始發布時間'),
                       ('language', 'zh-HK'), ('ttl', '240'), ('lastBuildDate', format_datetime(datetime.now(HKT)))]:
        ET.SubElement(channel, key).text = value
    ET.SubElement(channel, '{http://www.w3.org/2005/Atom}link', href=feed_url, rel='self', type='application/rss+xml')
    for article in sorted(articles, key=lambda a: a['published'], reverse=True)[:500]:
        item = ET.SubElement(channel, 'item')
        for key in ['title', 'description', 'link']:
            ET.SubElement(item, key).text = article[key]
        ET.SubElement(item, 'guid', isPermaLink='true').text = article['link']
        ET.SubElement(item, 'pubDate').text = format_datetime(datetime.fromisoformat(article['published']).astimezone(HKT))
    ET.indent(rss)
    return ET.tostring(rss, encoding='utf-8', xml_declaration=True)


def read_previous(data):
    root = ET.fromstring(data)
    if root.findtext('channel/link') != SOURCE:
        raise ValueError('Wrong saved HKET feed')
    articles = {}
    for item in root.findall('channel/item'):
        link = article_url(item.findtext('link', ''))
        date = parsedate_to_datetime(item.findtext('pubDate', ''))
        if not date.tzinfo or not item.findtext('description') or not item.findtext('title'):
            raise ValueError('Invalid saved HKET article')
        articles[link] = {'link': link, 'title': item.findtext('title'), 'description': item.findtext('description'),
                          'published': date.astimezone(HKT).isoformat()}
    if not articles:
        raise ValueError('Empty saved HKET feed')
    return articles


def collect(output, base_url, cache_path='.hket-cache/articles.json', fetch_html=browser_html):
    output, cache_path = Path(output), Path(cache_path)
    articles = read_previous(render(json.loads(cache_path.read_text(encoding='utf-8')), base_url + '/' + FEED_PATH)) if cache_path.exists() else {}
    # Recover the published feed too, so an evicted Actions cache cannot erase history.
    try:
        with urlopen(base_url + '/' + FEED_PATH, timeout=15) as response:
            articles.update(read_previous(response.read()))
    except (OSError, ValueError, ET.ParseError):
        pass
    known = set(articles)
    errors, discovered, completed = [], set(), 0
    started = time.monotonic()
    max_pages = 20 if known else 3
    for page in range(1, max_pages + 1):
        if time.monotonic() - started > 600:
            errors.append({'error': 'Ten-minute collection budget reached; continue next update'})
            break
        try:
            links = Page(fetch_html(SOURCE + f'?p={page}')).links
            if not links:
                raise ValueError('HKET listing has no article links')
        except (OSError, ValueError) as exc:
            errors.append({'page': page, 'error': str(exc)})
            break
        fresh = [link for link in links if link not in articles and link not in discovered]
        discovered.update(links)
        failures = 0
        for link in fresh:
            if time.monotonic() - started > 600:
                errors.append({'link': link, 'error': 'Collection budget reached'})
                break
            try:
                articles[link] = parse_article(fetch_html(link), link)
                completed += 1
                failures = 0
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(list(articles.values()), ensure_ascii=False), encoding='utf-8')
                print(json.dumps({'hket_article': link, 'published': articles[link]['published'], 'collected': completed}), flush=True)
            except (OSError, ValueError) as exc:
                failures += 1
                errors.append({'link': link, 'error': str(exc)})
                if failures >= 3:
                    break
        if failures >= 3 or (known and all(link in known for link in links)):
            break
    if not articles:
        raise RuntimeError('No valid HKET articles; refusing to publish an empty feed: ' + json.dumps(errors))
    retained = sorted(articles.values(), key=lambda a: a['published'], reverse=True)[:500]
    target = output / FEED_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(render(retained, base_url + '/' + FEED_PATH))
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(retained, ensure_ascii=False), encoding='utf-8')
    status = json.loads((output / 'status.json').read_text(encoding='utf-8'))
    status['news'] = [{'site': 'hket', 'path': FEED_PATH, 'state': 'updated' if completed else 'preserved',
                       'checked_at': datetime.now(HKT).isoformat(), 'items': len(retained), 'new_articles': completed,
                       'discovered': len(discovered), 'errors': errors}]
    (output / 'status.json').write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
    for filename in ['subscriptions.opml', 'hket.opml']:
        path = output / filename
        root = ET.parse(path).getroot() if path.exists() else ET.fromstring('<opml version="2.0"><head><title>HKET</title></head><body/></opml>')
        body = root.find('body')
        for old in list(body):
            if old.get('xmlUrl') == base_url + '/' + FEED_PATH:
                body.remove(old)
        ET.SubElement(body, 'outline', text=TITLE, title=TITLE, type='rss', xmlUrl=base_url + '/' + FEED_PATH, htmlUrl=SOURCE)
        ET.indent(root)
        ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)
    if errors:
        print(f'::warning::HKET collected with {len(errors)} errors; see status.json')
    print(json.dumps(status['news'][0], ensure_ascii=True), flush=True)


if __name__ == '__main__':
    collect(*sys.argv[1:])
