"""Read-only Facebook diagnostics. Print booleans/codes, never cookies or tokens."""
import http.cookiejar
import json
import os
import re
import secrets
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, Request, build_opener

BASE = 'https://www.facebook.com'
GROUP = '663672811292204'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'


class FacebookRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        host = urlparse(newurl).hostname or ''
        if host != 'facebook.com' and not host.endswith('.facebook.com'):
            raise ValueError('Unexpected redirect host')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def error_summary(value):
    errors = value.get('errors', []) if isinstance(value, dict) else []
    if isinstance(value, dict) and value.get('error'):
        errors = errors + [value['error']]
    summary = []
    for error in errors:
        if not isinstance(error, dict):
            continue
        text = str(error.get('message', error.get('summary', ''))).lower()
        summary.append({key: error[key] for key in ('code', 'error_subcode') if isinstance(error.get(key), int)} |
                       {'rate_limit': 'rate limit' in text, 'login': 'log' in text and 'in' in text,
                        'checkpoint': 'checkpoint' in text, 'query_error': 'query' in text or 'document' in text})
    return summary


def find_token(html, name):
    patterns = {
        'lsd': [r'"LSD",\[\],\{"token":"([^"]+)"', r'"lsd"\s*:\s*"([^"]+)"', r'name="lsd"\s+value="([^"]+)"'],
        'dtsg': [r'"DTSGInitialData",\[\],\{"token":"([^"]+)"', r'"DTSGInitData"[^\n]{0,120}?"token":"([^"]+)"'],
    }
    for pattern in patterns[name]:
        found = re.search(pattern, html)
        if found:
            return found[1]
    return ''


def main():
    cookie = os.environ.get('FACEBOOK_COOKIE', '')
    values = dict(part.strip().split('=', 1) for part in cookie.split(';') if '=' in part)
    print(json.dumps({'configuration': {'cookie_present': bool(cookie), 'c_user_present': bool(values.get('c_user')), 'xs_present': bool(values.get('xs'))}}), flush=True)
    if not values.get('c_user') or not values.get('xs'):
        return
    jar = http.cookiejar.CookieJar()
    for name, value in values.items():
        if re.fullmatch(r'[A-Za-z0-9_]+', name):
            jar.set_cookie(http.cookiejar.Cookie(0, name, value, None, False, '.facebook.com', True, True, '/', True, True, None, True, None, None, {}))
    opener = build_opener(FacebookRedirects(), HTTPCookieProcessor(jar))

    def request(path, data=None, extra_headers=None):
        try:
            req = Request(BASE + path, data=data, headers={'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.9',
                          'Referer': BASE + '/groups/' + GROUP + '/', **({'Content-Type': 'application/x-www-form-urlencoded', 'Origin': BASE} if data else {}), **(extra_headers or {})})
            with opener.open(req, timeout=35) as response:
                return response.status, response.read(12000000).decode('utf-8', errors='replace'), response.url
        except HTTPError as exc:
            return exc.code, exc.read(200000).decode('utf-8', errors='replace'), exc.url

    status, text, url = request('/ajax/dtsg/?__a=1')
    try:
        dtsg_data = json.loads(text.removeprefix('for (;;);'))
    except ValueError:
        dtsg_data = {}
    ajax_token = (dtsg_data.get('payload') or {}).get('token', '')
    print(json.dumps({'session_endpoint': {'http_status': status, 'token_present': bool(ajax_token),
                     'redirected_to_login': '/login' in urlparse(url).path, 'errors': error_summary(dtsg_data)}}), flush=True)

    status, html, url = request('/groups/' + GROUP + '/')
    lsd, dtsg = find_token(html, 'lsd'), find_token(html, 'dtsg') or ajax_token
    identities = re.findall(r'"(?:USER_ID|actorID|actorId)"\s*:\s*"(\d+)"', html)
    logged_in = values['c_user'] in identities
    print(json.dumps({'group_page': {'http_status': status, 'logged_in_account_matches': logged_in,
                     'lsd_present': bool(lsd), 'dtsg_present': bool(dtsg), 'checkpoint': '/checkpoint' in urlparse(url).path,
                     'redirected_to_login': '/login' in urlparse(url).path,
                     'embedded_story_markers': len(re.findall(r'"__typename"\s*:\s*"Story"', html))}}), flush=True)

    if not lsd or not logged_in:
        status, home, url = request('/')
        home_ids = re.findall(r'"(?:USER_ID|actorID|actorId)"\s*:\s*"(\d+)"', home)
        home_lsd = find_token(home, 'lsd')
        print(json.dumps({'homepage': {'http_status': status, 'logged_in_account_matches': values['c_user'] in home_ids,
                         'anonymous_identity_present': '0' in home_ids, 'lsd_present': bool(home_lsd),
                         'redirected_to_login': '/login' in urlparse(url).path,
                         'checkpoint': '/checkpoint' in urlparse(url).path,
                         'login_form_present': 'name="email"' in home and 'name="pass"' in home}}), flush=True)
        if home_lsd:
            lsd = home_lsd
            dtsg = find_token(home, 'dtsg') or dtsg
            logged_in = values['c_user'] in home_ids

    # One public-group request per variant; no retries or mutations.
    variables = {'id': GROUP, 'count': 3, 'cursor': None, 'scale': 1, 'useDefaultActor': False,
                 'feedLocation': 'GROUP', 'feedType': 'DISCUSSION', 'feedbackSource': 0,
                 'privacySelectorRenderLocation': 'COMET_STREAM', 'renderLocation': 'group',
                 'sortingSetting': 'CHRONOLOGICAL', 'stream_initial_count': 1, 'youthIntegrityHostID': GROUP}
    for label, token, csrf in [('rsshub_style', secrets.token_urlsafe(16), ajax_token), ('page_session_tokens', lsd, dtsg)]:
        if not token:
            print(json.dumps({label: {'skipped': 'No page session token available'}}), flush=True)
            continue
        body = {'lsd': token, 'jazoest': '2' + str(sum(ord(c) for c in token)),
                'fb_api_req_friendly_name': 'GroupsCometFeedRegularStoriesPaginationQuery',
                'doc_id': '28691921240463205', 'variables': json.dumps(variables)}
        if csrf:
            body['fb_dtsg'] = csrf
        if label == 'page_session_tokens' and logged_in:
            body.update({'__user': values['c_user'], 'av': values['c_user'], '__a': '1', '__comet_req': '15'})
        status, raw, _ = request('/api/graphql/', urlencode(body).encode(), {'x-fb-lsd': token})
        errors = []
        parsed_lines = 0
        for line in raw.removeprefix('for (;;);').splitlines():
            try:
                value = json.loads(line)
                errors.extend(error_summary(value))
                parsed_lines += 1
            except ValueError:
                pass
        print(json.dumps({label: {'http_status': status, 'json_lines': parsed_lines, 'errors': errors,
                         'story_markers': len(re.findall(r'"__typename"\s*:\s*"Story"', raw))}}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Exception text may contain request data; only its type is safe to log.
        print(json.dumps({'diagnostic_error_type': type(exc).__name__}), flush=True)
