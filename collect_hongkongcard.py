"""Public HongKongCard discussions: first 20 topics, newest 50 replies each."""
from datetime import datetime
from email.utils import format_datetime, parsedate_to_datetime
from html import escape
import json
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from collect_facebook import SafeHTML
from prepare_feed import HKT

SITE = 'https://www.hongkongcard.com'
PATH = 'feeds/hongkongcard/forum.xml'
ATOM = 'http://www.w3.org/2005/Atom'
DC = 'http://purl.org/dc/elements/1.1/'
ET.register_namespace('atom', ATOM)
ET.register_namespace('dc', DC)


class ContentHTML(SafeHTML):
    def handle_starttag(self, tag, pairs):
        attrs = dict(pairs)
        # The forum lazy-loads images with data-src instead of src.
        if tag == 'img' and attrs.get('data-src'):
            attrs['src'] = attrs['data-src']
        for key in ('href', 'src', 'poster'):
            if attrs.get(key):
                attrs[key] = urljoin(SITE, attrs[key])
        super().handle_starttag(tag, list(attrs.items()))


def content(value):
    parser = ContentHTML()
    parser.feed(value or '')
    return ''.join(parser.parts).strip()


def stamp(value):
    date = datetime.fromisoformat(value)
    return date.replace(tzinfo=HKT) if date.tzinfo is None else date.astimezone(HKT)


def fetch_json(path, **params):
    url = SITE + path + ('?' + urlencode(params) if params else '')
    request = Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json', 'Referer': SITE + '/forum'})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                data = json.load(response)
            if not isinstance(data, dict) or not isinstance(data.get('data'), list):
                raise ValueError('Unexpected forum API response')
            return data
        except (OSError, ValueError) as exc:
            if isinstance(exc, HTTPError) and exc.code not in (429, 500, 502, 503, 504):
                raise
            if attempt == 2:
                raise
            time.sleep(2 ** (attempt + 1))


def latest_replies(topic, limit, fetcher=fetch_json):
    tid = int(topic['id'])
    # Start at the known last page; no need to download years of older replies.
    page = max(1, int(topic.get('total_page', 1)))
    replies, seen_pages = {}, set()
    while page >= 1:
        if page in seen_pages:
            raise ValueError('Inconsistent reply pagination')
        seen_pages.add(page)
        data = fetcher('/vue/forum/replies', thread_id=tid, page=page)
        meta = data['meta']
        last = int(meta['last_page'])
        current = int(meta['current_page'])
        # The topic list and replies can change between requests.
        if last < 1 or int(meta['per_page']) < 1 or last > 100000:
            raise ValueError('Invalid reply pagination')
        if page > last or (len(seen_pages) == 1 and page != last):
            page = last
            seen_pages.discard(page)
            continue
        if current != page:
            raise ValueError('Reply API returned the wrong page')
        for reply in data['data']:
            if int(reply['thread_id']) != tid:
                raise ValueError('Reply belongs to another topic')
            stamp(reply['created_at'])
            replies[int(reply['id'])] = reply
        if len(replies) >= limit or page == 1:
            break
        page -= 1
    return sorted(replies.values(), key=lambda r: (stamp(r['created_at']), int(r['id'])), reverse=True)[:limit]


def snapshot(topic_limit, reply_limit, fetcher=fetch_json):
    data = fetcher('/vue/forum/threads', category_id=100, page=1, filter='latest')
    # Preserve the site's first-page selection (including pinned topics).
    topics = data['data'][:topic_limit]
    if len(topics) != topic_limit or len({int(t['id']) for t in topics}) != topic_limit:
        raise ValueError('Incomplete or duplicate topic list')
    result = []
    for topic in topics:
        stamp(topic['created_at'])
        replies = latest_replies(topic, reply_limit, fetcher)
        activity = max([stamp(topic['created_at'])] + [stamp(r['created_at']) for r in replies])
        result.append((topic, replies, activity))
    return sorted(result, key=lambda v: (v[2], int(v[0]['id'])), reverse=True)


def section(post, heading):
    author = (post.get('user') or {}).get('nickname', '')
    when = stamp(post['created_at']).strftime('%Y-%m-%d %H:%M:%S HKT')
    return f'<h3>{escape(heading)}</h3><p>{escape(author)} · {when}</p>{content(post.get("content"))}'


def render(topics, base_url, reply_limit):
    root = ET.Element('rss', version='2.0')
    channel = ET.SubElement(root, 'channel')
    for tag, value in [('title', 'HongKongCard 討論區 · 最新討論及回覆'), ('link', SITE + '/forum'),
                       ('description', f'論壇首頁首 {len(topics)} 個主題；每個主題附原文及最新 {reply_limit} 則回覆（由新至舊）。時間：香港。'),
                       ('language', 'zh-HK'), ('lastBuildDate', format_datetime(datetime.now(HKT))), ('ttl', '240')]:
        ET.SubElement(channel, tag).text = value
    ET.SubElement(channel, f'{{{ATOM}}}link', href=base_url.rstrip('/') + '/' + PATH, rel='self', type='application/rss+xml')
    for topic, replies, activity in topics:
        item = ET.SubElement(channel, 'item')
        ET.SubElement(item, 'title').text = topic['title'].strip()
        ET.SubElement(item, 'link').text = SITE + '/forum/show/' + str(int(topic['id']))
        # Stable topic identity lets readers update the entry without duplicates.
        ET.SubElement(item, 'guid', isPermaLink='false').text = 'hongkongcard:thread:' + str(int(topic['id']))
        ET.SubElement(item, 'pubDate').text = format_datetime(activity)
        ET.SubElement(item, f'{{{ATOM}}}updated').text = activity.isoformat()
        ET.SubElement(item, f'{{{DC}}}creator').text = (topic.get('user') or {}).get('nickname', '')
        intro = section(topic, '原帖')
        summary = f'<h2>最新回覆（{len(replies)} 則，由新至舊）</h2>'
        body = ''.join(section(r, f'回覆 #{r["id"]}') for r in replies)
        ET.SubElement(item, 'description').text = intro + summary + (body or '<p>暫無回覆</p>')
    ET.indent(root)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def validate_saved(raw, count):
    if b'<!DOCTYPE' in raw.upper():
        raise ValueError('Unexpected document type')
    root = ET.fromstring(raw)
    items = root.findall('channel/item')
    if root.findtext('channel/link') != SITE + '/forum' or len(items) != count:
        raise ValueError('Invalid saved HongKongCard feed')
    for item in items:
        if not item.findtext('guid', '').startswith('hongkongcard:thread:') or not item.findtext('description'):
            raise ValueError('Invalid saved topic')
        parsedate_to_datetime(item.findtext('pubDate'))
    return raw


def collect(config, output, base_url, fetcher=fetch_json, previous=None):
    limit, replies = int(config['topic_limit']), int(config['reply_limit'])
    if not 1 <= limit <= 25 or not 1 <= replies <= 50:
        raise ValueError('Use 1–25 topics and 1–50 replies')
    output = Path(output)
    result = {'path': PATH, 'checked_at': datetime.now(HKT).isoformat(), 'state': 'failed', 'topics': 0, 'error': None}
    try:
        topics = snapshot(limit, replies, fetcher)
        raw = render(topics, base_url, replies)
        result.update(state='updated', topics=len(topics), replies=sum(len(r) for _, r, _ in topics),
                      latest_activity=topics[0][2].isoformat())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result['error'] = str(exc)
        raw = None
        try:
            if previous is None:
                with urlopen(Request(base_url.rstrip('/') + '/' + PATH, headers={'User-Agent': 'Mozilla/5.0'}), timeout=25) as response:
                    previous = response.read()
            raw = validate_saved(previous, limit)
            result.update(state='preserved', topics=limit)
        except (OSError, ValueError, TypeError, ET.ParseError):
            pass
    output.mkdir(parents=True, exist_ok=True)
    if raw is not None:
        target = output / PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        opml_path = output / 'subscriptions.opml'
        opml = ET.parse(opml_path) if opml_path.exists() else ET.ElementTree(ET.fromstring('<opml version="2.0"><head/><body/></opml>'))
        body = opml.getroot().find('body')
        url = base_url.rstrip('/') + '/' + PATH
        if not any(o.get('xmlUrl') == url for o in body.iter('outline')):
            ET.SubElement(body, 'outline', text='HongKongCard 討論區', title='HongKongCard 討論區', type='rss', xmlUrl=url, htmlUrl=SITE + '/forum')
        ET.indent(opml)
        opml.write(opml_path, encoding='utf-8', xml_declaration=True)
    status_path = output / 'status.json'
    status = json.loads(status_path.read_text(encoding='utf-8')) if status_path.exists() else {}
    status['hongkongcard'] = result
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'hongkongcard': result}, ensure_ascii=True), flush=True)
    if result['state'] != 'updated':
        print('::warning::HongKongCard collection failed; see status.json')
    return result


if __name__ == '__main__':
    config, output, base = sys.argv[1:]
    collect(json.loads(Path(config).read_text(encoding='utf-8')), output, base)
