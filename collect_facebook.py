"""Publish configurable public Facebook groups through RSSHub."""
from datetime import datetime
from email.utils import format_datetime, parsedate_to_datetime
from html import escape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import xml.etree.ElementTree as ET

from prepare_feed import HKT

HOSTS = {'facebook.com', 'www.facebook.com', 'm.facebook.com'}


class SafeHTML(HTMLParser):
    allowed = {'p', 'div', 'span', 'br', 'hr', 'a', 'img', 'video', 'source', 'b', 'strong', 'i', 'em', 'u', 's', 'ul', 'ol', 'li', 'blockquote', 'h1', 'h2', 'h3'}
    blocked = {'script', 'style', 'iframe', 'object', 'svg', 'math', 'form', 'button'}
    void = {'img', 'br', 'hr', 'source'}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.stack = [], []
    def handle_starttag(self, tag, pairs):
        if self.stack:
            if tag not in self.void and tag not in {'input', 'meta', 'link', 'embed'}:
                self.stack.append(tag)
            return
        if tag in self.blocked:
            self.stack.append(tag)
            return
        if tag not in self.allowed:
            return
        attrs = []
        for key, value in pairs:
            if key in {'href', 'src', 'poster'} and value and urlparse(value).scheme in {'http', 'https'} and not urlparse(value).username:
                attrs.append(f' {key}="{escape(value, quote=True)}"')
            elif key == 'alt':
                attrs.append(f' alt="{escape(value or "", quote=True)}"')
            elif key == 'controls' and tag == 'video':
                attrs.append(' controls="controls"')
        self.parts.append('<' + tag + ''.join(attrs) + '>')
    def handle_endtag(self, tag):
        if self.stack:
            if tag in self.stack:
                self.stack = self.stack[:len(self.stack) - 1 - self.stack[::-1].index(tag)]
            return
        if tag in self.allowed and tag not in self.void:
            self.parts.append('</' + tag + '>')
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.void:
            self.handle_endtag(tag)
    def handle_data(self, value):
        if not self.stack:
            self.parts.append(escape(value))


def sanitize(value):
    parser = SafeHTML()
    parser.feed(value)
    return ''.join(parser.parts).strip()


def groups(path):
    values = json.loads(Path(path).read_text(encoding='utf-8'))['groups']
    seen = set()
    for group in values:
        identifier = str(group['id'])
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,99}', identifier) or identifier.lower() in seen:
            raise ValueError('Group IDs must be valid, unique Facebook IDs/usernames')
        seen.add(identifier.lower())
        if group.get('public') is not True:
            raise ValueError('Public GitHub Pages feeds require explicit public:true for each group')
        if group.get('numeric_id') is not None and not str(group['numeric_id']).isdigit():
            raise ValueError('numeric_id must contain digits only')
        group.update(id=identifier, path='feeds/facebook/' + identifier.lower() + '.xml')
    return values


def fetch(url):
    try:
        with urlopen(Request(url, headers={'User-Agent': 'FacebookGroupFeedPublisher/1.0'}), timeout=100) as response:
            return response.read()
    except HTTPError as exc:
        if url.startswith('http://127.0.0.1:1200/facebook/'):
            body = exc.read(120000).decode('utf-8', errors='replace').lower()
            reason = 'source request failed'
            for phrase, label in [('rate limit', 'Facebook rate limit'), ('not found', 'group lookup failed'),
                                  ('login', 'Facebook login required'), ('logged in', 'Facebook session required'),
                                  ('checkpoint', 'Facebook verification required'), ('dtsg', 'Facebook session initialization failed'),
                                  ('graphql', 'Facebook GraphQL request failed')]:
                if phrase in body:
                    reason = label
                    break
            raise ValueError(f'RSSHub HTTP {exc.code}: {reason}') from exc
        raise


def resolve_id(group):
    if group.get('numeric_id') or group['id'].isdigit():
        return str(group.get('numeric_id') or group['id'])
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'}
    if os.environ.get('FACEBOOK_COOKIE'):
        headers['Cookie'] = os.environ['FACEBOOK_COOKIE']
    try:
        with urlopen(Request('https://www.facebook.com/groups/' + group['id'] + '/about', headers=headers), timeout=20) as response:
            text = response.read().decode('utf-8')
        match = re.search(r'"groupID"\s*:\s*"(\d+)"', text)
        if match:
            return match[1]
    except (OSError, ValueError):
        pass
    return group['id']


def read_feed(data, group):
    if b'<!DOCTYPE' in data.upper():
        raise ValueError('Unexpected XML document type')
    root = ET.fromstring(data)
    channel = root.find('channel')
    if root.tag != 'rss' or channel is None:
        raise ValueError('Expected RSS, not a login/error page')
    expected = {str(group['id']).lower(), str(group.get('numeric_id', '')).lower(), str(group.get('resolved_id', '')).lower()} - {''}
    link = urlparse(channel.findtext('link', ''))
    parts = link.path.strip('/').split('/')
    if link.hostname not in HOSTS or len(parts) != 2 or parts[0] != 'groups' or parts[1].lower() not in expected:
        raise ValueError('Unexpected Facebook group; numeric_id may be needed in configuration')
    # Keep the previously resolved numeric identity when a later lookup is blocked.
    saved_id = channel.findtext('{urn:feed-publisher}facebookGroupId', '')
    if saved_id.isdigit():
        expected.add(saved_id)
    posts = {}
    for item in channel.findall('item'):
        url = urlparse(item.findtext('link', ''))
        match = re.fullmatch(r'/groups/([^/]+)/(?:posts|permalink)/([A-Za-z0-9]+)/?', url.path)
        if url.scheme != 'https' or url.hostname not in HOSTS or not match or match[1].lower() not in expected:
            raise ValueError('Post does not belong to the configured group')
        date = parsedate_to_datetime(item.findtext('pubDate', ''))
        if not date.tzinfo:
            raise ValueError('Original Facebook publication timezone missing')
        content = item.findtext('description') or item.findtext('{http://purl.org/rss/1.0/modules/content/}encoded') or ''
        content = sanitize(content)
        if not content or '\ufffd' in content or (not re.sub(r'<[^>]*>', '', content).strip() and not re.search(r'<(?:img|video)\b[^>]*(?:src|poster)=', content)):
            raise ValueError('Post content missing or corrupted')
        identifier = match[2]
        if identifier in posts:
            raise ValueError('Duplicate Facebook post')
        posts[identifier] = {'title': item.findtext('title') or 'Facebook post', 'description': content,
                             'link': f'https://www.facebook.com/groups/{match[1]}/posts/{identifier}/',
                             'date': date.astimezone(HKT), 'author': item.findtext('{http://purl.org/dc/elements/1.1/}creator', '')}
    if not posts:
        raise ValueError('No group posts returned; Facebook may require FACEBOOK_COOKIE or numeric_id')
    return posts, channel.findtext('title', group['id'])


def render(posts, group, title, feed_url):
    root = ET.Element('rss', version='2.0')
    channel = ET.SubElement(root, 'channel')
    for key, value in [('title', group.get('name') or title), ('link', 'https://www.facebook.com/groups/' + group['id']),
                       ('description', 'Public group posts'), ('ttl', '240'), ('lastBuildDate', format_datetime(datetime.now(HKT)))]:
        ET.SubElement(channel, key).text = value
    ET.SubElement(channel, '{http://www.w3.org/2005/Atom}link', href=feed_url, rel='self', type='application/rss+xml')
    ET.SubElement(channel, '{urn:feed-publisher}facebookGroupId').text = group.get('resolved_id', group['id'])
    for identifier, post in sorted(posts.items(), key=lambda entry: entry[1]['date'], reverse=True)[:200]:
        item = ET.SubElement(channel, 'item')
        for key in ['title', 'description', 'link']:
            ET.SubElement(item, key).text = post[key]
        ET.SubElement(item, 'guid', isPermaLink='false').text = 'facebook:post:' + identifier
        ET.SubElement(item, 'pubDate').text = format_datetime(post['date'])
        if post.get('author'):
            ET.SubElement(item, '{http://purl.org/dc/elements/1.1/}creator').text = post['author']
    ET.indent(root)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def collect(config, output, base, fetcher=fetch, resolver=resolve_id):
    output, base = Path(output), base.rstrip('/')
    results, available = [], []
    for group in groups(config):
        identifier, path = group['id'], group['path']
        prior, previous, title = None, {}, identifier
        try:
            prior = fetcher(base + '/' + path)
            previous, title = read_feed(prior, group)
        except (OSError, ValueError, TypeError, ET.ParseError):
            prior, previous = None, {}
        saved_id = ET.fromstring(prior).findtext('channel/{urn:feed-publisher}facebookGroupId', '') if prior else ''
        group['resolved_id'] = str(group.get('numeric_id') or (saved_id if saved_id.isdigit() else '') or resolver(group))
        payload, error = prior, None
        try:
            latest, title = read_feed(fetcher('http://127.0.0.1:1200/facebook/group/' + group['resolved_id']), group)
            previous.update(latest)
            payload = render(previous, group, title, base + '/' + path)
            state = 'updated'
        except (OSError, ValueError, TypeError, ET.ParseError) as exc:
            state, error = 'preserved' if prior else 'failed', str(exc)
        if payload:
            target = output / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            available.append(group)
        results.append({'id': identifier, 'resolved_id': group['resolved_id'], 'state': state, 'path': path if payload else None,
                        'items': min(len(previous), 200), 'authentication_configured': bool(os.environ.get('FACEBOOK_COOKIE')),
                        'checked_at': datetime.now(HKT).isoformat(), 'error': error})
    path = output / 'status.json'
    status = json.loads(path.read_text(encoding='utf-8'))
    status['facebook'] = results
    path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
    for filename in ['subscriptions.opml', 'facebook.opml']:
        path = output / filename
        root = ET.parse(path).getroot() if path.exists() else ET.fromstring('<opml version="2.0"><head><title>Facebook groups</title></head><body/></opml>')
        body = root.find('body')
        for entry in list(body):
            if entry.get('xmlUrl', '').startswith(base + '/feeds/facebook/'):
                body.remove(entry)
        for group in available:
            label = group.get('name') or group['id']
            ET.SubElement(body, 'outline', text=label, title=label, type='rss', xmlUrl=base + '/' + group['path'], htmlUrl='https://www.facebook.com/groups/' + group['id'])
        ET.indent(root)
        ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)
    print(json.dumps({'facebook': results}), flush=True)


if __name__ == '__main__':
    collect(*sys.argv[1:])
