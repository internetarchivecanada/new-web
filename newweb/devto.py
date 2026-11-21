"""dev.to (DEV Community): new articles on tags where developers show what they built, every 15 minutes.
Any link to a site in the article counts (except big sites, and dev.to itself). The article is public and
linked from the explorer, like a Hacker News story.
"""
import json, re, time, urllib.parse, urllib.request
from .common import connect, record, beat, get_state, set_state, log, site_key, BIG, REFERENCE, UA

TAGS = ['showdev', 'sideprojects', 'vibecoding', 'buildinpublic', 'claudecode', 'webapp', 'portfolio', 'indiehackers']
API = 'https://dev.to/api/articles'
HREF = re.compile(r'href="(https?://[^"]+)"')


def get(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'}), timeout=60))


def main():
    db = connect()
    done = set(json.loads(get_state(db, 'devto_done', '[]')))
    while True:
        seen = kept = 0
        for tag in TAGS:
            try:
                arts = get(API + '?' + urllib.parse.urlencode({'tag': tag, 'per_page': 30, 'state': 'fresh'}))
                arts += get(API + '?' + urllib.parse.urlencode({'tag': tag, 'per_page': 30}))
            except Exception as e:
                log('devto error', tag, repr(e)); continue
            for a in arts:
                if a['id'] in done:
                    continue
                done.add(a['id']); seen += 1
                try:
                    body = get(f"{API}/{a['id']}").get('body_html') or ''
                except Exception:
                    continue
                for u in dict.fromkeys(HREF.findall(body)):
                    site = site_key(u)
                    if not site:
                        continue
                    host = site.split('/')[0]
                    if BIG.search(host) or REFERENCE.search(host) or host.endswith(('dev.to', 'forem.com', 'dev-to-uploads.s3.amazonaws.com')):
                        continue
                    kept += record(db, u, 'devto', str(a['id']), json.dumps({'article': a.get('url')}))
                db.commit()
                time.sleep(1)
            time.sleep(2)
        set_state(db, 'devto_done', json.dumps(sorted(done)[-5000:]))
        beat(db, 'devto', seen, kept)
        log('devto new articles', seen, 'new sites', kept)
        time.sleep(900)


if __name__ == '__main__':
    main()
