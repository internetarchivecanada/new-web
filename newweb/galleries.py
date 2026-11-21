"""Public showcase pages of vibe-coding tools, read every 2 hours. Every link on them to a site on a hosting
platform is recorded, labelled with the tool that made it. Each page is allowed by its site's robots.txt
(checked 2026-11-21); the page is read once per round, like a person visiting it.
"""
import json, re, time, urllib.request
from .common import connect, record, beat, log, platform_of, site_key, UA

# (tool, page)
GALLERIES = [
    ('Lovable', 'https://lovable.dev/discover'),
    ('Lovable', 'https://madewithlovable.com/'),
    ('v0', 'https://v0.app/community'),
]
LINK = re.compile(r'https?://[a-z0-9][a-z0-9.-]+\.[a-z]{2,}(?:/[^\s"\'<>\\)]*)?', re.I)


def main():
    db = connect()
    while True:
        seen = kept = 0
        for tool, page in GALLERIES:
            try:
                body = urllib.request.urlopen(urllib.request.Request(page, headers={'User-Agent': UA}), timeout=60).read().decode('utf-8', 'replace')
            except Exception as e:
                log('galleries error', page, repr(e)); continue
            found = 0
            for u in dict.fromkeys(LINK.findall(body)):
                site = site_key(u)
                if not site or not platform_of(site.split('/')[0])[0]:
                    continue
                found += 1
                kept += record(db, 'https://' + site + '/', 'gallery', page, json.dumps({'tool': tool, 'gallery': page}))
            db.commit()
            seen += found
            log('galleries', page, 'links', found)
            time.sleep(5)
        beat(db, 'gallery', seen, kept)
        log('galleries round: links', seen, 'new sites', kept)
        time.sleep(7200)


if __name__ == '__main__':
    main()
