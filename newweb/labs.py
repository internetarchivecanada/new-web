"""Wayback Machine Labs: the tiles on https://wayback-labs.sf.archive.org/, read from its landing page every 6 hours.
Each tile is its own site (wayback-labs.sf.archive.org/<name>, or its own address for tiles hosted elsewhere),
with the tile's title and description, so they are pictured, checked and saved like every other site.
"""
import html, json, re, time, urllib.parse, urllib.request
from .common import connect, record, beat, log, site_key, platform_of, UA

LANDING = 'https://wayback-labs.sf.archive.org/'
CARD = re.compile(r'<a class="card[^"]*" href="([^"]+)"[^>]*>(.*?)</a>', re.S)
TITLE = re.compile(r'<div class="title">(.*?)</div>', re.S)
DESC = re.compile(r'<div class="desc">(.*?)</div>', re.S)


def text(m):
    return html.unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip() if m else ''


def main():
    db = connect()
    while True:
        try:
            page = urllib.request.urlopen(urllib.request.Request(LANDING, headers={'User-Agent': UA}), timeout=60).read().decode('utf-8', 'replace')
            cards = CARD.findall(page)
            kept = 0
            for href, inner in cards:
                url = urllib.parse.urljoin(LANDING, html.unescape(href))
                site = site_key(url)
                if not site or site == 'wayback-labs.sf.archive.org':
                    continue
                host = site.split('/')[0]
                plat = 'wayback-labs' if host == 'wayback-labs.sf.archive.org' else (platform_of(host)[0] or 'custom')
                extra = json.dumps({'title': text(TITLE.search(inner)), 'description': text(DESC.search(inner))})
                kept += record(db, url, 'labs', href, extra, platform=plat)
            db.commit()
            beat(db, 'labs', len(cards), kept)
            log('labs tiles', len(cards), 'new sites', kept)
        except Exception as e:
            log('labs error', repr(e))
        time.sleep(6 * 3600)


if __name__ == '__main__':
    main()
