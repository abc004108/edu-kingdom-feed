"""Validate RSSHub output before replacing the public feed."""
from email.utils import parsedate_to_datetime
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlparse
import xml.etree.ElementTree as ET


def prepare(source, destination, base_url):
    content = Path(source).read_text(encoding='utf-8-sig')
    if '\ufffd' in content:
        raise ValueError('The feed contains corrupted Unicode text')
    root = ET.fromstring(content)
    channel = root.find('channel')
    if root.tag != 'rss' or channel is None:
        raise ValueError('Expected an RSS channel, possibly received a block page')
    source_link = urlparse(channel.findtext('link') or '')
    if source_link.hostname != 'www.edu-kingdom.com' or parse_qs(source_link.query).get('fid') != ['368']:
        raise ValueError('Unexpected source forum')
    items = channel.findall('item')
    if not items:
        raise ValueError('Empty feed: the published version will be preserved')
    seen = set()
    for item in items:
        link = item.findtext('link') or ''
        parsed = urlparse(link)
        tid = parse_qs(parsed.query).get('tid', [''])[0]
        if parsed.hostname != 'www.edu-kingdom.com' or not tid.isdigit():
            raise ValueError('Invalid thread link')
        if link in seen or item.findtext('guid') != link or not item.findtext('title'):
            raise ValueError('Invalid or duplicate topic identity')
        seen.add(link)
        if item.findtext('pubDate'):
            parsedate_to_datetime(item.findtext('pubDate'))
    channel.find('title').text = '教育王國 · 小一選校 · 新主題'
    for atom_link in channel.findall('{http://www.w3.org/2005/Atom}link'):
        if atom_link.get('rel') == 'self':
            atom_link.set('href', base_url.rstrip('/') + '/feed.xml')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    ET.indent(root)
    ET.ElementTree(root).write(destination / 'feed.xml', encoding='utf-8', xml_declaration=True)
    (destination / '.nojekyll').touch()
    print(f'Validated {len(items)} topics. Feed URL: {base_url.rstrip("/")}/feed.xml')


if __name__ == '__main__':
    prepare(*sys.argv[1:])
