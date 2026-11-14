"""Hacker News via the Algolia API. Every "Show HN" link counts (except big sites such as github.com);
other stories count only when they link to a site on a known hosting platform."""
import json, sys, time, urllib.parse, urllib.request
from .common import connect, record, beat, get_state, set_state, log, platform_of, site_key, BIG, UA

API = 'https://hn.algolia.com/api/v1/search_by_date'


def fetch(tags, since):
    hits, page = [], 0
    while True:
        q = urllib.parse.urlencode({'tags': tags, 'numericFilters': f'created_at_i>{since}', 'hitsPerPage': 1000, 'page': page})
        d = json.load(urllib.request.urlopen(urllib.request.Request(f'{API}?{q}', headers={'User-Agent': UA}), timeout=60))
        hits += d['hits']
        page += 1
        if page >= d.get('nbPages', 0):
            return hits


def run_once(db, since):
    seen = kept = 0
    newest = since
    for tags in ('show_hn', 'story'):
        for h in fetch(tags, since):
            seen += 1
            newest = max(newest, h['created_at_i'])
            url = h.get('url')
            if not url:
                continue
            site = site_key(url)
            if not site:
                continue
            host = site.split('/')[0]
            plat = platform_of(host)[0]
            if tags == 'show_hn':
                if BIG.search(host):
                    continue
            elif not plat:
                continue
            extra = json.dumps({'points': h.get('points'), 'comments': h.get('num_comments'), 'show_hn': tags == 'show_hn'})
            kept += record(db, url, 'hn', h['objectID'], extra, when=h['created_at_i'])
    db.commit()
    return seen, kept, newest


def main():
    db = connect()
    backfill_days = float(sys.argv[1]) if len(sys.argv) > 1 else 7
    since = int(get_state(db, 'hn_since', int(time.time() - backfill_days * 86400)))
    while True:
        try:
            seen, kept, since = run_once(db, since)
            set_state(db, 'hn_since', since)
            beat(db, 'hn', seen, kept)
            log('hn', 'seen', seen, 'new sites', kept)
        except Exception as e:
            log('hn error', repr(e))
        time.sleep(600)


if __name__ == '__main__':
    main()
