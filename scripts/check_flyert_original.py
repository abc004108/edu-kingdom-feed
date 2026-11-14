"""One-off public-page diagnostic for first-floor extraction."""
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from original_post import first_page_url, Floors
from topic_content import original_content

try:
    with urlopen('https://abc004108.github.io/edu-kingdom-feed/feeds/flyert/23.xml', timeout=20) as response:
        item = ET.fromstring(response.read()).find('channel/item')
    link = item.findtext('link')
    body = json.dumps({'cmd':'request.get', 'url':first_page_url(link), 'session':'edu-kingdom-feed', 'maxTimeout':60000}).encode()
    with urlopen(Request('http://127.0.0.1:8191/v1', data=body, headers={'Content-Type':'application/json'}), timeout=70) as response:
        result = json.load(response)
    html = result.get('solution', {}).get('response', '')
    floors = Floors(html)
    print(json.dumps({'first_post_diagnostic': link, 'floor_labels': floors.labels, 'headers': floors.headers[:4]}), flush=True)
    for marker in ['authorposton', 'postnum', 'postmessage_']:
        pos = html.find(marker)
        print(json.dumps({'marker':marker, 'context':html[max(0,pos-220):pos+130] if pos >= 0 else 'absent'}), flush=True)
    print(json.dumps({'verified_original':original_content(html, link)[:250]}), flush=True)
except Exception as exc:
    print(json.dumps({'first_post_diagnostic_error':str(exc)}), flush=True)
