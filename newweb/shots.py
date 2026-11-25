"""Screenshots each discovered site that is up, and records what it was built with, what it is about and
whether it should stay off the public explorer. One look per site, soon after it is found, while it is live.

Thumbnails: <EXPLORER>/thumbs/<sha1(site)[:16]>.webp (480 px wide), on the internal disk so Caddy can serve them.
Uses system Chrome with its sandbox and one reused page per browser: on the studio, Chrome 157 crashes when
Playwright closes a page (see salon-explorer/app/shots.py).
"""
import hashlib, io, json, os, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from playwright.sync_api import sync_playwright
from PIL import Image
from .common import connect, beat, log
from . import classify, caplog

EXPLORER = os.environ.get('NEWWEB_EXPLORER', '/opt/services/new-web/public')
THUMBS = os.path.join(EXPLORER, 'thumbs')
VIEWPORT = {'width': 1280, 'height': 800}
THUMB_W = 480
UA_SUFFIX = 'WaybackMachineLabs-NewWeb/0.1 (Internet Archive; +https://wayback-labs.sf.archive.org/new-web/)'
BLOCK_TYPES = {'media', 'websocket', 'eventsource', 'manifest', 'texttrack'}

TEXT_JS = r'''() => {
  const m = (s) => { const e = document.querySelector(s); return e ? (e.getAttribute('content') || '').trim() : ''; };
  return {
    title: (document.title || m('meta[property="og:title"]') || '').trim(),
    description: m('meta[name="description"]') || m('meta[property="og:description"]'),
    lang: (document.documentElement.getAttribute('lang') || '').trim().slice(0, 12),
    h1: [...document.querySelectorAll('h1')].slice(0, 3).map(e => e.innerText.trim()).join(' | '),
    text: (document.body ? document.body.innerText : '').slice(0, 8000),
    generator: m('meta[name="generator"]'),
  };
}'''


def thumb_name(site):
    return hashlib.sha1(site.encode()).hexdigest()[:16] + '.webp'


def _route(r):
    # A route can outlive its page (navigation, crash, closed context). Letting that error escape makes
    # Playwright print a 4-line "unroute_all" warning per request, which once filled the disk (2026-11-22).
    try:
        r.abort() if r.request.resource_type in BLOCK_TYPES else r.continue_()
    except Exception:
        pass


def launch(p):
    browser = p.chromium.launch(channel='chrome', chromium_sandbox=True)
    major = browser.version.split('.')[0]
    ua = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) '
          f'Chrome/{major}.0.0.0 Safari/537.36 {UA_SUFFIX}')
    ctx = browser.new_context(viewport=VIEWPORT, user_agent=ua, accept_downloads=False, java_script_enabled=True)
    ctx.route('**/*', _route)
    page = ctx.new_page()
    page.set_default_timeout(20000)
    return browser, page


def look(page, url):
    resp = page.goto(url, wait_until='domcontentloaded', timeout=25000)
    try:
        page.wait_for_load_state('networkidle', timeout=6000)
    except Exception:
        pass
    page.wait_for_timeout(1200)
    status = resp.status if resp else None
    html = page.content()[:400000]
    info = page.evaluate(TEXT_JS)
    probes = page.evaluate(classify.PROBE_JS)
    png = page.screenshot(full_page=False)
    return status, page.url, html, info, probes, png


def save_thumb(png, path):
    img = Image.open(io.BytesIO(png)).convert('RGB')
    w, h = img.size
    img.resize((THUMB_W, max(1, round(h * THUMB_W / w)))).save(path, 'WEBP', quality=72, method=6)


def worker(queue, lock, stats):
    db = connect()
    with sync_playwright() as p:
        browser, page = launch(p)
        while True:
            with lock:
                if not queue:
                    break
                site, url = queue.pop()
            if not browser.is_connected():
                browser, page = launch(p)
            now = int(time.time())
            row = dict(site=site, shot=now, ok=0, thumb=None, title=None, description=None, lang=None,
                       tech='[]', topics='[]', flags='[]', starter=0, final_url=None, error=None)
            try:
                status, final, html, info, probes, png = look(page, url)
                row['final_url'] = final
                if status and status >= 400:
                    row['error'] = f'HTTP {status}'
                else:
                    name = thumb_name(site)
                    save_thumb(png, os.path.join(THUMBS, name))
                    text = ' '.join([info.get('h1') or '', info.get('text') or ''])
                    fl = classify.flags(info['title'], info['description'], text, html)
                    row.update(ok=1, thumb=name, title=(info['title'] or '')[:300],
                               description=(info['description'] or '')[:500], lang=info['lang'],
                               tech=json.dumps(classify.technology(html + ' generator" content="' + (info.get('generator') or ''), probes)),
                               topics=json.dumps(classify.topics(info['title'], info['description'], text)),
                               flags=json.dumps(fl), starter=int(classify.starter(info['title'], info.get('text'))))
            except Exception as e:
                row['error'] = (type(e).__name__ + ': ' + (str(e).splitlines() or [''])[0])[:300]
                if not browser.is_connected():
                    with lock:
                        stats['relaunch'] = stats.get('relaunch', 0) + 1
            db.execute('INSERT OR REPLACE INTO profiles VALUES(:site,:shot,:ok,:thumb,:title,:description,:lang,:tech,'
                       ':topics,:flags,:starter,:final_url,:error)', row)
            db.commit()
            ALIVE[0] = time.time()
            with lock:
                stats['ok' if row['ok'] else 'failed'] = stats.get('ok' if row['ok'] else 'failed', 0) + 1


# Time the last look finished. A page can hang the browser in a way no Playwright timeout catches
# (it froze for 10 hours on 2026-11-24), so a watchdog ends the process and launchd starts it again.
ALIVE = [time.time()]
STUCK = 600


def watchdog():
    while True:
        time.sleep(60)
        if time.time() - ALIVE[0] > STUCK:
            log('shots watchdog: no look finished in', STUCK, 's; exiting so launchd restarts the job')
            os._exit(1)


def due(db, n):
    # Sites that answered at their last check and have not been looked at yet, newest first.
    return db.execute("SELECT s.site, s.first_url FROM sites s LEFT JOIN profiles p ON p.site = s.site "
                      "WHERE p.site IS NULL AND s.last_verdict IN ('up', 'moved') "
                      "ORDER BY s.first_seen DESC LIMIT ?", (n,)).fetchall()


def main():
    os.makedirs(THUMBS, exist_ok=True)
    workers = int(os.environ.get('NEWWEB_SHOT_WORKERS', 2))
    db = connect()
    threading.Thread(target=watchdog, daemon=True).start()
    while True:
        rows = due(db, 200)
        if not rows:
            ALIVE[0] = time.time() + 300
            time.sleep(300)
            continue
        queue, lock, stats = list(reversed(rows)), threading.Lock(), {}
        t = ALIVE[0] = time.time()
        with ThreadPoolExecutor(workers) as ex:
            for _ in range(workers):
                ex.submit(worker, queue, lock, stats)
        beat(db, 'shots', len(rows), stats.get('ok', 0), json.dumps(stats))
        log('shots', len(rows), 'looked at in', round(time.time() - t), 's', stats)


if __name__ == '__main__':
    if len(sys.argv) > 1:      # test one URL: python -m newweb.shots https://example.com/
        with sync_playwright() as p:
            b, pg = launch(p)
            s, f, h, i, pr, png = look(pg, sys.argv[1])
            text = (i.get('h1') or '') + ' ' + (i.get('text') or '')
            print(json.dumps({'status': s, 'final': f, 'title': i['title'], 'lang': i['lang'],
                              'tech': classify.technology(h + ' generator" content="' + (i.get('generator') or ''), pr),
                              'topics': classify.topics(i['title'], i['description'], text),
                              'flags': classify.flags(i['title'], i['description'], text, h),
                              'starter': classify.starter(i['title'], i.get('text'))}, indent=1))
            b.close()
    else:
        caplog.install('shots')
        main()
