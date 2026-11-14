"""Checks each discovered site about 1 hour, then 1, 7, 30, 60 and 90 days after it was first seen, so the
pilot can measure how fast these sites disappear. Recognises the "nothing deployed here" pages that hosting
platforms serve once a site is removed, which often come back with status 200 or a generic 404."""
import concurrent.futures as cf, re, ssl, time, urllib.error, urllib.parse, urllib.request
from .common import connect, log, UA

AGES = [0, 1, 7, 30, 60, 90]           # days after first_seen; age 0 runs one hour after discovery
GONE_SIGNS = [
    ('vercel', re.compile(r'DEPLOYMENT_NOT_FOUND|DEPLOYMENT_DISABLED|The deployment could not be found', re.I)),
    ('netlify', re.compile(r"Page not found.{0,400}Looks like you've followed a broken link|Site not found", re.I | re.S)),
    ('github', re.compile(r"There isn't a GitHub Pages site here", re.I)),
    ('heroku', re.compile(r'no-such-app|There.s nothing here, yet', re.I)),
    ('render', re.compile(r'x-render-routing|Service Suspended', re.I)),
    ('fly', re.compile(r'fly\.io.{0,200}(could not find|not found)', re.I | re.S)),
    ('cloudflare', re.compile(r'(This deployment|Nothing is here yet)|error code: 1001', re.I)),
    ('railway', re.compile(r'Application not found|Train has not arrived', re.I)),
    ('replit', re.compile(r'(Repl|Deployment) (not found|is not running)', re.I)),
    ('hf', re.compile(r'(Space|This Space) (is sleeping|has been paused|not found)|Runtime error', re.I)),
    ('glitch', re.compile(r'project not found|This project is not available', re.I)),
    ('streamlit', re.compile(r"(app|App) (is asleep|doesn.t exist)|You do not have access to this app", re.I)),
    ('suspended', re.compile(r'(account|site|app) (has been )?suspended', re.I)),
]
# Which signatures apply to which platform (the rest only on their own platform, to avoid false matches).
APPLIES = {'vercel': 'vercel', 'netlify': 'netlify', 'github': 'github-pages', 'heroku': 'heroku', 'render': 'render',
           'fly': 'fly', 'cloudflare': 'cloudflare-pages cloudflare-workers', 'railway': 'railway', 'replit': 'replit',
           'hf': 'huggingface', 'glitch': 'glitch', 'streamlit': 'streamlit'}
ASLEEP = re.compile(r'is (asleep|sleeping)|has been paused|wake (it )?up', re.I)
CTX = ssl.create_default_context()


def check(url, platform=''):
    out = {'status': None, 'final_url': None, 'bytes': None, 'title': None, 'error': None}
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'text/html,*/*'})
    try:
        r = urllib.request.urlopen(req, timeout=30, context=CTX)
        body, out['status'], out['final_url'] = r.read(300000), r.status, r.geturl()
    except urllib.error.HTTPError as e:
        body, out['status'], out['final_url'] = e.read(300000), e.code, e.geturl()
    except Exception as e:
        out['error'] = repr(e)[:300]
        msg = out['error']
        out['verdict'] = 'gone-dns' if ('Name or service not known' in msg or 'nodename nor servname' in msg
                                        or 'getaddrinfo failed' in msg) else 'unreachable'
        return out
    text = body.decode('utf-8', 'replace')
    out['bytes'] = len(body)
    m = re.search(r'<title[^>]*>(.*?)</title>', text, re.S | re.I)
    out['title'] = re.sub(r'\s+', ' ', m.group(1)).strip()[:200] if m else None
    for name, rx in GONE_SIGNS:
        if name in APPLIES and platform not in APPLIES[name].split():
            continue
        if rx.search(text[:50000]):
            out['verdict'] = 'asleep' if ASLEEP.search(text[:50000]) else f'gone-{name}'
            return out
    st = out['status']
    if st in (404, 410):
        out['verdict'] = 'gone-404'
    elif st in (401, 403):
        out['verdict'] = 'blocked'
    elif st >= 500:
        out['verdict'] = 'error'
    elif _host(out['final_url']) != _host(url):
        out['verdict'] = 'moved'          # still up, now on another host (often the owner's own domain)
    else:
        out['verdict'] = 'up'
    return out


def _host(u):
    h = urllib.parse.urlsplit(u).hostname or ''
    return h[4:] if h.startswith('www.') else h


def due(db, limit=2000):
    now = int(time.time())
    return db.execute('SELECT site, platform, first_seen, checks_done, first_url FROM sites WHERE next_check <= ? '
                      'ORDER BY next_check LIMIT ?', (now, limit)).fetchall()


def main():
    db = connect()
    with cf.ThreadPoolExecutor(24) as ex:
        while True:
            rows = due(db)
            if not rows:
                time.sleep(300)
                continue
            # Check the URL that was actually shared: a site's front page can 404 while the shared
            # page lives (github.io project sites under a user with no user site), and vice versa.
            urls = {r[0]: r[4] or f'https://{r[0]}/' for r in rows}
            plat = {r[0]: r[1] for r in rows}
            results = dict(zip(urls, ex.map(lambda s: check(urls[s], plat[s]), urls)))
            now = int(time.time())
            tally = {}
            for site, _, first_seen, done, _ in rows:
                r = results[site]
                tally[r['verdict']] = tally.get(r['verdict'], 0) + 1
                db.execute('INSERT INTO checks VALUES(?,?,?,?,?,?,?,?,?,?)',
                           (site, urls[site], now, (now - first_seen) / 86400, r['status'], r['verdict'],
                            r['final_url'], r['bytes'], r['title'], r['error']))
                done += 1
                nxt = first_seen + AGES[done] * 86400 if done < len(AGES) else None
                db.execute('UPDATE sites SET checks_done=?, next_check=?, last_verdict=? WHERE site=?',
                           (done, nxt, r['verdict'], site))
            db.commit()
            log('liveness', len(rows), 'checked', tally)


if __name__ == '__main__':
    main()
