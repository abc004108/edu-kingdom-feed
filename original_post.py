"""Choose the actual first floor, independently of displayed reply order."""
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

def first_page_url(link):
    url = urlparse(link)
    tid = parse_qs(url.query).get('tid', [''])[0]
    if not tid.isdigit():
        raise ValueError('Missing numeric thread ID')
    return urlunparse((url.scheme, url.netloc, url.path, '', urlencode({'mod': 'viewthread', 'tid': tid, 'page': 1, 'ordertype': 2}), ''))

class Floors(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.headers, self.labels = [], {}
        self.pid, self.depth = None, 0
        self.feed(html)
    def handle_starttag(self, tag, pairs):
        attrs = dict(pairs)
        header = re.fullmatch(r'authorposton(\d+)', attrs.get('id', ''))
        if header:
            self.headers.append(header[1])
        marker = re.fullmatch(r'postnum_?(\d+)', attrs.get('id', ''))
        if marker:
            self.pid, self.depth = marker[1], 1
            self.labels[self.pid] = ''
        elif self.depth and tag not in VOID:
            self.depth += 1
    def handle_endtag(self, tag):
        if self.depth and tag not in VOID:
            self.depth -= 1
            if not self.depth:
                self.pid = None
    def handle_data(self, value):
        if self.pid:
            self.labels[self.pid] += value

def original_pid(html, strict=False):
    data = Floors(html)
    for pid, label in data.labels.items():
        label = re.sub(r'\s+', '', label)
        if label in {'1', '1#', '1楼', '1樓', '楼主', '樓主'} and pid in data.headers:
            return pid
    # Flyert's lead-post layout has two author/date headers for the same post
    # (the article header and author panel), but no reply-floor/postnum link.
    # Replies have postnum links. Require a unique unnumbered lead post, a body,
    # duplicate header references and the oldest PID; never use display order.
    leads = {pid for pid in data.headers if pid not in data.labels and data.headers.count(pid) >= 2
             and re.search(r'id=["\']postmessage_' + pid + r'["\']', html)}
    if len(leads) == 1:
        lead = next(iter(leads))
        if int(lead) == min(map(int, data.headers)):
            return lead
    if strict:
        raise ValueError('Cannot verify first-floor marker; refusing to use a reply. Floors: ' + repr(list(data.labels.values())[:4]))
    if not data.headers:
        raise ValueError('Original author header missing; refusing to use a reply')
    return data.headers[0]

def migrate_flyert_cache(path, values):
    marker = Path(str(path) + '.first-post-v2')
    if marker.exists():
        return values
    import json
    values = {link: value for link, value in values.items() if urlparse(link).hostname != 'www.flyert.com.cn'}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if Path(path).exists():
        Path(path).write_text(json.dumps(values, ensure_ascii=False), encoding='utf-8')
    marker.write_text('First-floor extraction v2', encoding='utf-8')
    return values
