"""Collect configured forums sequentially through one running RSSHub instance."""
from datetime import datetime
import json
from pathlib import Path, PurePosixPath
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from prepare_feed import render_feed, SITES, HKT


def fetch(url):
    with urlopen(Request(url, headers={'User-Agent': 'EduKingdomFeedCollector/1.0'}), timeout=110) as response:
        return response.read()


def load_config(path):
    forums = json.loads(Path(path).read_text(encoding='utf-8'))['forums']
    seen_ids, seen_paths = set(), set()
    if not forums:
        raise ValueError('Configure at least one forum')
    for forum in forums:
        fid = str(forum['id'])
        site = forum.get('site', 'edu-kingdom')
        if site not in SITES:
            raise ValueError(f'Unsupported site: {site}')
        identity = (site, fid)
        if not fid.isdigit() or identity in seen_ids or not forum.get('name', '').strip():
            raise ValueError('Forum IDs must be unique numeric values with a name')
        seen_ids.add(identity)
        forum['id'] = fid
        forum['site'] = site
        forum['path'] = f'feeds/{fid}.xml' if site == 'edu-kingdom' else f'feeds/{site}/{fid}.xml'
        for path in [forum['path'], *forum.get('aliases', [])]:
            parts = PurePosixPath(path)
            if parts.is_absolute() or '..' in parts.parts or '\\' in path or not path.endswith('.xml') or path in seen_paths:
                raise ValueError(f'Invalid or duplicate feed path: {path}')
            seen_paths.add(path)
    return forums


def collect(forums, output, base_url, fetcher=fetch):
    output = Path(output)
    base_url = base_url.rstrip('/')
    results, prepared, missing = [], [], []
    for forum in forums:
        fid, name, path = forum['id'], forum['name'], forum['path']
        site = forum['site']
        feed_url = f'{base_url}/{path}'
        route = 'new-topics' if site == 'flyert' else 'forum'
        try:
            raw = fetcher(f'http://127.0.0.1:1200/{site}/{route}/{fid}')
            data = render_feed(raw, fid, name, feed_url, site)
            state = 'updated'
            error = None
        except (URLError, OSError, ValueError, ET.ParseError) as exc:
            error = str(exc)
            data = None
            # Recover only validated feeds for this forum, including its legacy alias.
            for previous_path in [path, *forum.get('aliases', [])]:
                try:
                    raw = fetcher(f'{base_url}/{previous_path}')
                    data = render_feed(raw, fid, name, feed_url, site)
                    break
                except (URLError, OSError, ValueError, ET.ParseError):
                    pass
            state = 'preserved' if data is not None else 'missing'
            if data is None:
                missing.append(f'{site}/{fid}')
        results.append({'site': site, 'id': fid, 'name': name, 'path': path, 'state': state, 'error': error})
        if data is not None:
            prepared.append((forum, data))
        print(json.dumps(results[-1], ensure_ascii=True), flush=True)
    if missing:
        raise RuntimeError(f'No valid initial feed for forums {", ".join(missing)}; existing published site preserved')

    # Nothing is written until every configured forum has a valid fresh or saved feed.
    for forum, data in prepared:
        for path in [forum['path'], *forum.get('aliases', [])]:
            target = output / path
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = render_feed(data, forum['id'], forum['name'], f'{base_url}/{path}', forum['site']) if path != forum['path'] else data
            target.write_bytes(payload)
    output.mkdir(parents=True, exist_ok=True)
    (output / '.nojekyll').touch()
    (output / 'status.json').write_text(json.dumps({'checked_at': datetime.now(HKT).isoformat(), 'timezone': 'Asia/Hong_Kong', 'forums': results}, ensure_ascii=False, indent=2), encoding='utf-8')
    write_opml(output / 'subscriptions.opml', forums, base_url, '論壇訂閱 · 新主題')
    for site, (_, label) in SITES.items():
        selected = [forum for forum in forums if forum['site'] == site]
        if selected:
            write_opml(output / f'{site}.opml', selected, base_url, f'{label} · 新主題')
    return results


def write_opml(path, forums, base_url, title):
    opml = ET.Element('opml', version='2.0')
    ET.SubElement(ET.SubElement(opml, 'head'), 'title').text = title
    body = ET.SubElement(opml, 'body')
    for forum in forums:
        host, label = SITES[forum['site']]
        name = f"{label} · {forum['name']}"
        ET.SubElement(body, 'outline', text=name, title=name, type='rss', xmlUrl=f"{base_url}/{forum['path']}", htmlUrl=f"https://{host}/forum.php?mod=forumdisplay&fid={forum['id']}")
    ET.indent(opml)
    ET.ElementTree(opml).write(path, encoding='utf-8', xml_declaration=True)


if __name__ == '__main__':
    config, output, base_url = sys.argv[1:]
    results = collect(load_config(config), output, base_url)
    if any(result['state'] != 'updated' for result in results):
        print('::warning::Some forums retain their last successful feed; see public/status.json')
