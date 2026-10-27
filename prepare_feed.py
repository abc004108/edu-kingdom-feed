"""Validate RSSHub output before replacing the public feed."""
from email.utils import parsedate_to_datetime
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlparse
import xml.etree.ElementTree as ET


def render_feed(content, fid, name, feed_url):
    if isinstance(content, bytes):
        content = content.decode('utf-8-sig')
    if '\ufffd' in content:
        raise ValueError('The feed contains corrupted Unicode text')
    root = ET.fromstring(content)
    channel = root.find('channel')
    if root.tag != 'rss' or channel is None or channel.find('title') is None:
        raise ValueError('Expected an RSS channel, possibly received a block page')
    source_link = urlparse(channel.findtext('link') or '')
    if source_link.hostname != 'www.edu-kingdom.com' or parse_qs(source_link.query).get('fid') != [str(fid)]:
        raise ValueError(f'Unexpected source forum; expected {fid}')
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
    channel.find('title').text = f'教育王國 · {name} · 新主題'
    ttl = channel.find('ttl')
    if ttl is None:
        ttl = ET.SubElement(channel, 'ttl')
    ttl.text = '240'
    for atom_link in channel.findall('{http://www.w3.org/2005/Atom}link'):
        if atom_link.get('rel') == 'self':
            atom_link.set('href', feed_url)
    ET.indent(root)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def prepare(source, destination, base_url):
    # Keep the original single-feed command usable.
    output = Path(destination)
    data = render_feed(Path(source).read_bytes(), 368, '小一選校', base_url.rstrip('/') + '/feed.xml')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'feed.xml').write_bytes(data)
    (output / '.nojekyll').touch()


if __name__ == '__main__':
    prepare(*sys.argv[1:])
