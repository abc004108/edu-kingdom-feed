"""Publish configurable X accounts via the authenticated RSSHub user route."""
from datetime import datetime
from email.utils import format_datetime, parsedate_to_datetime
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from prepare_feed import HKT


def accounts(path):
    values = json.loads(Path(path).read_text(encoding='utf-8'))['accounts']
    seen = set()
    for account in values:
        handle = account['handle'].removeprefix('@')
        if not re.fullmatch(r'[A-Za-z0-9_]{1,15}', handle) or handle.lower() in seen:
            raise ValueError('X handles must be valid and unique, ignoring case')
        for flag in ['include_replies', 'include_reposts']:
            if type(account.get(flag, False)) is not bool:
                raise ValueError(f'{flag} must be true or false')
        seen.add(handle.lower())
        account.update(handle=handle, path=f'feeds/x/{handle.lower()}.xml')
    return values


def fetch(url):
    with urlopen(Request(url, headers={'User-Agent': 'AccountFeedPublisher/1.0'}), timeout=90) as response:
        return response.read()


def read_feed(data, handle):
    if b'<!DOCTYPE' in data.upper():
        raise ValueError('Unexpected XML document type')
    root = ET.fromstring(data)
    channel = root.find('channel')
    if root.tag != 'rss' or channel is None:
        raise ValueError('Expected RSS, not an authentication/error page')
    profile = urlparse(channel.findtext('link', ''))
    if profile.hostname not in {'x.com', 'www.x.com', 'twitter.com', 'www.twitter.com'} or profile.path.strip('/').lower() != handle.lower():
        raise ValueError('Feed belongs to a different X account')
    posts = {}
    for item in channel.findall('item'):
        link = urlparse(item.findtext('link', ''))
        match = re.fullmatch(r'/([A-Za-z0-9_]+)/status/(\d+)/?', link.path)
        if link.scheme != 'https' or link.hostname not in {'x.com', 'www.x.com', 'twitter.com', 'www.twitter.com'} or not match:
            raise ValueError('Unexpected X post URL')
        date = parsedate_to_datetime(item.findtext('pubDate', ''))
        if not date.tzinfo:
            raise ValueError('X publication time has no timezone')
        description = item.findtext('description') or item.findtext('{http://purl.org/rss/1.0/modules/content/}encoded')
        if not description or '\ufffd' in description:
            raise ValueError('X post content is missing or corrupted')
        identifier = match[2]
        if identifier in posts:
            raise ValueError('Duplicate X post')
        posts[identifier] = {'title': item.findtext('title') or f'@{handle}', 'description': description,
                             'link': f'https://x.com/{match[1]}/status/{identifier}', 'date': date.astimezone(HKT)}
    if not posts:
        raise ValueError('No posts returned; refusing to publish an empty timeline')
    return posts


def render(posts, account, feed_url):
    root = ET.Element('rss', version='2.0')
    channel = ET.SubElement(root, 'channel')
    handle = account['handle']
    for key, value in [('title', f"X · {account.get('name', handle)} (@{handle})"), ('link', f'https://x.com/{handle}'),
                       ('description', f'Posts from @{handle}'), ('ttl', '240'), ('lastBuildDate', format_datetime(datetime.now(HKT)))]:
        ET.SubElement(channel, key).text = value
    ET.SubElement(channel, '{http://www.w3.org/2005/Atom}link', href=feed_url, rel='self', type='application/rss+xml')
    for identifier, post in sorted(posts.items(), key=lambda value: value[1]['date'], reverse=True)[:200]:
        item = ET.SubElement(channel, 'item')
        for key in ['title', 'description', 'link']:
            ET.SubElement(item, key).text = post[key]
        ET.SubElement(item, 'guid', isPermaLink='false').text = 'x:status:' + identifier
        ET.SubElement(item, 'pubDate').text = format_datetime(post['date'])
    ET.indent(root)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def collect(config, output, base, fetcher=fetch, authenticated=False):
    output, base = Path(output), base.rstrip('/')
    results, available = [], []
    for account in accounts(config):
        handle, path = account['handle'], account['path']
        prior = None
        try:
            prior = fetcher(base + '/' + path)
            previous = read_feed(prior, handle)
        except (OSError, ValueError, TypeError, ET.ParseError):
            prior, previous = None, {}
        error = None
        state = 'missing_auth'
        payload = prior
        if authenticated:
            try:
                params = 'includeReplies=' + str(account.get('include_replies', False)).lower() + '&includeRts=' + str(account.get('include_reposts', False)).lower()
                route = f'http://127.0.0.1:1200/twitter/user/{handle}/' + quote(params, safe='=&')
                latest = read_feed(fetcher(route), handle)
                previous.update(latest)
                payload = render(previous, account, base + '/' + path)
                state = 'updated'
            except (OSError, ValueError, TypeError, ET.ParseError) as exc:
                state, error = 'preserved' if prior else 'failed', str(exc)
        if payload:
            target = output / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            available.append(account)
        results.append({'handle': handle, 'path': path if payload else None, 'state': state,
                        'items': min(len(previous), 200), 'checked_at': datetime.now(HKT).isoformat(), 'error': error})
    status_path = output / 'status.json'
    status = json.loads(status_path.read_text(encoding='utf-8'))
    status['x'] = results
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
    for name in ['subscriptions.opml', 'x.opml']:
        path = output / name
        root = ET.parse(path).getroot() if path.exists() else ET.fromstring('<opml version="2.0"><head><title>X subscriptions</title></head><body/></opml>')
        body = root.find('body')
        for entry in list(body):
            if entry.get('xmlUrl', '').startswith(base + '/feeds/x/'):
                body.remove(entry)
        for account in available:
            title = account.get('name', account['handle']) + ' (@' + account['handle'] + ')'
            ET.SubElement(body, 'outline', text=title, title=title, type='rss', xmlUrl=base + '/' + account['path'], htmlUrl='https://x.com/' + account['handle'])
        ET.indent(root)
        ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)
    print(json.dumps({'x': results}), flush=True)


if __name__ == '__main__':
    collect(*sys.argv[1:], authenticated=os.environ.get('X_AUTH_CONFIGURED', '').lower() == 'true')
