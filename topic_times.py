"""Resolve original first-post timestamps, independently of reply activity."""
from datetime import datetime
from email.utils import format_datetime
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlparse, parse_qs
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from prepare_feed import HKT, SITES


class PostTimeParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.first = None
        self.capture = False
        self.values = []
        self.meta = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta' and (attrs.get('property') == 'article:published_time' or attrs.get('itemprop') == 'datePublished'):
            self.meta.append(attrs.get('content', ''))
        if self.first is None and re.fullmatch(r'authorposton\d+', attrs.get('id', '')):
            self.first = attrs['id']
            self.capture = True
            self.depth = 1
        elif self.capture:
            self.depth += 1
        if self.capture:
            self.values.extend(attrs[key] for key in ['title', 'datetime'] if key in attrs)

    def handle_endtag(self, tag):
        if self.capture:
            self.depth -= 1
            if self.depth <= 0:
                self.capture = False

    def handle_data(self, data):
        if self.capture:
            self.values.append(data)


def original_time(html):
    parser = PostTimeParser()
    parser.feed(html)
    # Inspect only the first author's timestamp or explicit publication metadata.
    # Never search arbitrary page text, which can contain reply/edit times.
    for raw in [*parser.values, *parser.meta]:
        match = re.search(r'(?<!\d)(\d{4}|\d{2})-(\d{1,2})-(\d{1,2})[ T]+(\d{1,2}):(\d{2})(?::(\d{2}))?(?!\d)', raw)
        if not match:
            continue
        year, month, day, hour, minute, second = match.groups()
        year = int(year) + (2000 if len(year) == 2 else 0)
        date = datetime(year, int(month), int(day), int(hour), int(minute), int(second or 0), tzinfo=HKT)
        # Publication metadata can carry its own explicit offset.
        if raw in parser.meta:
            try:
                parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
                if parsed.tzinfo:
                    date = parsed.astimezone(HKT)
            except ValueError:
                pass
        return date
    raise ValueError(f'Original first-post time was not exposed; first timestamp fields: {parser.values[:4]}')


class TopicTimes:
    def __init__(self, path='topic-times.json', fetch_html=None):
        self.path = Path(path)
        self.values = {}
        if self.path.exists():
            self.values = json.loads(self.path.read_text(encoding='utf-8'))
        self.fetch_html = fetch_html or self.browser_html
        self.attempts = 0
        self.failures = []

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.values, ensure_ascii=False, indent=2), encoding='utf-8')

    @staticmethod
    def browser_html(link):
        helper = os.environ.get('FORUM_BROWSER_HELPER', 'http://127.0.0.1:8191/v1')
        session = os.environ.get('FORUM_BROWSER_SESSION', 'edu-kingdom-feed')
        body = json.dumps({'cmd':'request.get', 'url':link+'&page=1&ordertype=1', 'session':session, 'maxTimeout':30000}).encode()
        with urlopen(Request(helper, data=body, headers={'Content-Type':'application/json'}), timeout=40) as response:
            result = json.load(response)
        solution = result.get('solution', {})
        if result.get('status') != 'ok' or solution.get('status') != 200:
            raise ValueError(result.get('message', 'No usable topic page'))
        return solution.get('response', '')

    def resolve(self, link):
        parsed = urlparse(link)
        if parsed.hostname not in {host for host, _ in SITES.values()} or not parse_qs(parsed.query).get('tid', [''])[0].isdigit():
            raise ValueError('Unexpected topic URL')
        if link in self.values:
            return datetime.fromisoformat(self.values[link]).astimezone(HKT)
        self.attempts += 1
        date = None
        # Flyert's public HTML is GBK. Read it directly before using the browser,
        # reducing browser traffic and avoiding unnecessary session restrictions.
        if parsed.hostname == 'www.flyert.com.cn':
            try:
                request = Request(link+'&page=1&ordertype=1', headers={'User-Agent':'Mozilla/5.0 (compatible; ForumFeedCollector/1.0)'})
                with urlopen(request, timeout=20) as response:
                    charset = response.headers.get_content_charset() or 'gbk'
                    html = response.read().decode(charset)
                date = original_time(html)
                time.sleep(0.5)
            except (OSError, ValueError, TimeoutError):
                pass
        if date is None:
            date = original_time(self.fetch_html(link))
        self.values[link] = date.isoformat()
        self.save()
        return date

    def enrich(self, data):
        root = ET.fromstring(data)
        resolved = 0
        for item in root.findall('channel/item'):
            date = item.find('pubDate')
            if date is not None:
                item.remove(date)
            link = item.findtext('link')
            try:
                value = self.resolve(link)
                ET.SubElement(item, 'pubDate').text = format_datetime(value)
                resolved += 1
            except (OSError, ValueError, TimeoutError) as exc:
                self.failures.append({'link':link, 'error':str(exc)})
            if self.attempts % 10 == 0 and self.attempts:
                print(f'Original timestamps: {len(self.values)} cached; {len(self.failures)} unavailable', flush=True)
        return ET.tostring(root, encoding='utf-8', xml_declaration=True), resolved
