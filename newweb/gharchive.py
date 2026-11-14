"""GitHub via GH Archive's hourly event files. Two signals:
1. pushes to a repository named <user>.github.io (a personal GitHub Pages site), and
2. links to hosting-platform sites in new repositories' descriptions and in release notes."""
import gzip, io, json, re, sys, time, urllib.request
from datetime import datetime, timedelta, timezone
from .common import connect, record, beat, get_state, set_state, log, platform_of, site_key, UA

URL_RE = re.compile(r'https?://[^\s)\]>"\'`]+')


def hour_file(dt):
    return f'https://data.gharchive.org/{dt:%Y-%m-%d}-{dt.hour}.json.gz'


def process(db, dt):
    raw = urllib.request.urlopen(urllib.request.Request(hour_file(dt), headers={'User-Agent': UA}), timeout=300).read()
    seen = kept = 0
    for line in io.TextIOWrapper(gzip.GzipFile(fileobj=io.BytesIO(raw)), encoding='utf-8', errors='replace'):
        seen += 1
        if seen % 5000 == 0:
            db.commit()
        ev = json.loads(line)
        repo = (ev.get('repo') or {}).get('name', '')
        when = int(datetime.strptime(ev['created_at'], '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc).timestamp())
        owner, _, name = repo.partition('/')
        if ev['type'] in ('PushEvent', 'CreateEvent') and name.lower() == f'{owner.lower()}.github.io':
            kept += record(db, f'https://{name.lower()}/', 'github', f'{repo}#{ev["type"]}', json.dumps({'repo': repo}), when=when)
            continue
        p = ev.get('payload') or {}
        text = ''
        if ev['type'] == 'CreateEvent' and p.get('ref_type') == 'repository':
            text = p.get('description') or ''
        elif ev['type'] == 'ReleaseEvent':
            text = (p.get('release') or {}).get('body') or ''
        for url in URL_RE.findall(text[:20000]):
            url = url.rstrip('.,;:!')
            site = site_key(url)
            if site and platform_of(site.split('/')[0])[0]:
                kept += record(db, url, 'github', f'{repo}#{ev["id"]}', json.dumps({'repo': repo}), when=when)
    db.commit()
    return seen, kept


def main():
    db = connect()
    backfill_hours = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    nxt = get_state(db, 'gha_next')
    nxt = datetime.fromisoformat(nxt) if nxt else (datetime.now(timezone.utc) - timedelta(hours=backfill_hours + 2)).replace(minute=0, second=0, microsecond=0)
    while True:
        # GH Archive publishes each hour's file some minutes after the hour ends.
        if datetime.now(timezone.utc) < nxt + timedelta(hours=1, minutes=20):
            time.sleep(300)
            continue
        try:
            seen, kept = process(db, nxt)
            log('github', nxt.isoformat(), 'events', seen, 'new sites', kept)
            beat(db, 'github', seen, kept, nxt.isoformat())
            nxt += timedelta(hours=1)
            set_state(db, 'gha_next', nxt.isoformat())
        except urllib.error.HTTPError as e:
            log('github', nxt.isoformat(), 'HTTP', e.code)
            if e.code == 404 and datetime.now(timezone.utc) > nxt + timedelta(hours=6):
                nxt += timedelta(hours=1)  # GH Archive sometimes skips an hour
            time.sleep(300)
        except Exception as e:
            log('github error', repr(e))
            time.sleep(300)


if __name__ == '__main__':
    main()
