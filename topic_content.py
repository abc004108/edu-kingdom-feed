"""Extract publicly visible original Discuz posts into safe RSS descriptions."""
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlparse, parse_qs
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from prepare_feed import SITES
from topic_times import PostTimeParser

VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}


def public_url(value, base):
    url = urljoin(base, value or '')
    return url if urlparse(url).scheme in {'http', 'https'} and not urlparse(url).username else None


class PostBody(HTMLParser):
    def __init__(self, target, link):
        super().__init__(convert_charrefs=True)
        self.target, self.link = target, link
        self.depth = 0
        self.skip = 0
        self.done = False
        self.parts = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if not self.depth:
            if not self.done and attrs.get('id') == self.target:
                self.depth = 1
            return
        if tag not in VOID:
            self.depth += 1
        if self.skip:
            return
        classes = set(attrs.get('class', '').split())
        if tag in {'script', 'style', 'form', 'button', 'iframe', 'object', 'blockquote'} or classes & {'quote', 'pstatus', 'signature', 'locked', 'showhide', 'attach_nopermission', 'aimg_tip', 'tip'}:
            if tag not in VOID:
                self.skip = self.depth
            return
        if tag in {'br', 'p', 'div', 'li', 'tr', 'hr'}:
            self.parts.append('\n')
        if tag == 'img':
            source = next((attrs[k] for k in ['zoomfile', 'file', 'data-src', 'src'] if attrs.get(k)), '')
            url = public_url(source, self.link)
            if url:
                self.parts.append(f'<img src="{escape(url, quote=True)}" alt="{escape(attrs.get("alt", ""), quote=True)}" />')

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if not self.depth or tag in VOID:
            return
        if self.skip == self.depth:
            self.skip = 0
        elif not self.skip and tag in {'p', 'div', 'li', 'tr'}:
            self.parts.append('\n')
        self.depth -= 1
        if self.depth == 0:
            self.done = True

    def handle_data(self, value):
        if self.depth and not self.skip:
            self.text.append(value)
            self.parts.append(escape(value))


def original_content(html, link):
    header = PostTimeParser()
    header.feed(html)
    if not header.first:
        raise ValueError('Original author header missing; refusing to use a reply')
    pid = re.search(r'\d+$', header.first).group()
    parser = PostBody('postmessage_' + pid, link)
    parser.feed(html)
    result = re.sub(r'\n[ \t\r\n]*\n+', '\n\n', ''.join(parser.parts)).strip()
    if not parser.done or not result or (not ''.join(parser.text).strip() and '<img ' not in result):
        raise ValueError('Original post content unavailable or restricted')
    return '<div>' + result.replace('\n', '<br/>') + '</div>'


class TopicContent:
    def __init__(self, timestamps, path='.topic-cache/post-content.json', fetch_html=None):
        self.timestamps, self.path = timestamps, Path(path)
        self.values = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
        self.fetch_html = fetch_html
        self.failures, self.host_failures = [], {}

    def resolve(self, link):
        host = urlparse(link).hostname
        if host not in {value[0] for value in SITES.values()} or not parse_qs(urlparse(link).query).get('tid', [''])[0].isdigit():
            raise ValueError('Unexpected topic URL')
        if link in self.values:
            return self.values[link]
        if self.host_failures.get(host, 0) >= 3:
            raise ValueError('Content requests paused after three failures; retry next run')
        html = self.timestamps.pages.get(link)
        if html is None and self.fetch_html:
            html = self.fetch_html(link)
        if html is None and host == 'www.flyert.com.cn':
            try:
                with urlopen(Request(link + '&page=1&ordertype=1', headers={'User-Agent': 'Mozilla/5.0'}), timeout=8) as response:
                    html = response.read().decode(response.headers.get_content_charset() or 'gbk')
                result = original_content(html, link)
            except (OSError, ValueError):
                html = None
        if html is None:
            html = self.timestamps.fetch_html(link)
        result = original_content(html, link)
        self.values[link] = result
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.values, ensure_ascii=False), encoding='utf-8')
        self.host_failures[host] = 0
        return result

    def enrich(self, data):
        root = ET.fromstring(data)
        count = 0
        for item in root.findall('channel/item'):
            link = item.findtext('link')
            description = item.find('description')
            if description is None:
                description = ET.SubElement(item, 'description')
            try:
                description.text = self.resolve(link)
            except (OSError, ValueError) as exc:
                self.failures.append({'link': link, 'error': str(exc)})
                host = urlparse(link).hostname
                self.host_failures[host] = self.host_failures.get(host, 0) + 1
                if not description.text:
                    description.text = '<p>Original post could not be retrieved. <a href="' + escape(link, quote=True) + '">Read the topic</a>.</p>'
            if link in self.values:
                count += 1
        print(f'Post descriptions: {count} available; {len(self.values)} cached', flush=True)
        return ET.tostring(root, encoding='utf-8', xml_declaration=True), count
