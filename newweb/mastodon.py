"""Mastodon (the fediverse) via public, no-login API endpoints, every 5 minutes:
- hashtag timelines on mastodon.social, which gathers posts from across the fediverse: any link to a site
  counts on tags where people show things they made (#vibecoding, #showdev, #sideproject ...);
- the public timelines of a few large servers that still serve them without a login: only links to sites
  on hosting platforms count, as for Bluesky.
Only the link, the time and a hash of the post's address are kept: nothing about who posted it.
"""
import hashlib, html, json, re, time, urllib.parse, urllib.request
from .common import connect, record, beat, get_state, set_state, log, platform_of, site_key, BIG, REFERENCE, UA

TAGS = ['vibecoding', 'vibecoded', 'showdev', 'sideproject', 'sideprojects', 'buildinpublic', 'claudecode',
        'madewithclaude', 'indiedev', 'indiehackers', 'webapp', 'myproject', 'smallweb', 'personalwebsite']
TAG_SERVER = 'mastodon.social'
PUBLIC = ['fosstodon.org', 'hachyderm.io', 'mas.to']
HREF = re.compile(r'href="(https?://[^"]+)"')


def get(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'}), timeout=60))


def links(st):
    st = st.get('reblog') or st
    out = [html.unescape(u) for u in HREF.findall(st.get('content') or '')]
    if st.get('card') and st['card'].get('url'):
        out.append(st['card']['url'])
    mentions = {m.get('url') for m in st.get('mentions') or []}
    tags = {t.get('url') for t in st.get('tags') or []}
    return [u for u in dict.fromkeys(out) if u not in mentions and u not in tags and '/tags/' not in u and '/@' not in u]


def poll(db, key, url, any_site):
    since = get_state(db, key)
    q = {'limit': 40}
    if since:
        q['since_id'] = since
    statuses = get(url + ('&' if '?' in url else '?') + urllib.parse.urlencode(q))
    kept = 0
    for st in statuses:
        ref = hashlib.sha256((st.get('uri') or st['id']).encode()).hexdigest()[:20]
        for u in links(st):
            site = site_key(u)
            if not site:
                continue
            host = site.split('/')[0]
            if BIG.search(host) or REFERENCE.search(host) or host.endswith(tuple(PUBLIC + [TAG_SERVER])):
                continue
            if any_site or platform_of(host)[0]:
                kept += record(db, u, 'mastodon', ref)
    if statuses:
        set_state(db, key, statuses[0]['id'])
    db.commit()
    return len(statuses), kept


def main():
    db = connect()
    while True:
        seen = kept = 0
        for tag in TAGS:
            try:
                s, k = poll(db, f'masto_tag_{tag}', f'https://{TAG_SERVER}/api/v1/timelines/tag/{tag}', True)
                seen += s; kept += k
            except Exception as e:
                log('mastodon error', tag, repr(e))
            time.sleep(2)
        for server in PUBLIC:
            try:
                s, k = poll(db, f'masto_public_{server}', f'https://{server}/api/v1/timelines/public?remote=false', False)
                seen += s; kept += k
            except Exception as e:
                log('mastodon error', server, repr(e))
            time.sleep(2)
        beat(db, 'mastodon', seen, kept)
        log('mastodon posts', seen, 'new sites', kept)
        time.sleep(300)


if __name__ == '__main__':
    main()
