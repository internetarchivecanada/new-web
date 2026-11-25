"""Hugging Face Spaces: every new public Space, from the Hub's list sorted by creation time (no key needed).

A new Space is usually empty or still building when it is created, so a Space is only recorded (and so saved and
pictured) once it is running: each is looked at again from 2 hours after creation, then every 3 hours, for up to
2 days. Spaces that never run (no app file, build or config errors) are dropped and counted.

The site saved is the Space's own app address (<owner>-<name>.hf.space, or .static.hf.space for static Spaces),
which is what a visitor sees inside the huggingface.co/spaces page.
"""
import json, time, urllib.parse, urllib.request
from datetime import datetime
from .common import connect, record, beat, get_state, set_state, log, UA

API = 'https://huggingface.co/api/spaces'
FIRST_LOOK = 2 * 3600      # after creation
AGAIN = 3 * 3600
GIVE_UP = 2 * 86400
DEAD = {'NO_APP_FILE', 'BUILD_ERROR', 'CONFIG_ERROR', 'RUNTIME_ERROR', 'DELETED'}


def get(url):
    r = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'}), timeout=60)
    return json.load(r), r.headers.get('Link', '')


def ts(s):
    return int(datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp())


def new_spaces(since):
    """Spaces created after `since`, newest first, following the Hub's page links."""
    url = API + '?' + urllib.parse.urlencode({'sort': 'createdAt', 'direction': -1, 'limit': 1000})
    out = []
    while url:
        page, link = get(url)
        for s in page:
            if ts(s['createdAt']) <= since:
                return out
            if not s.get('private'):
                out.append(s)
        url = link.split('<', 1)[1].split('>', 1)[0] if 'rel="next"' in link else None
        time.sleep(1)
    return out


def setup(db):
    db.execute('CREATE TABLE IF NOT EXISTS hf_pending(id TEXT PRIMARY KEY, created INTEGER, next INTEGER, tries INTEGER DEFAULT 0, '
               'sdk TEXT, title TEXT, descr TEXT)')
    db.commit()


def queue(db, spaces):
    for s in spaces:
        c, card = ts(s['createdAt']), s.get('cardData') or {}
        db.execute('INSERT OR IGNORE INTO hf_pending(id, created, next, sdk, title, descr) VALUES(?,?,?,?,?,?)',
                   (s['id'], c, c + FIRST_LOOK, s.get('sdk'), (card.get('title') or '')[:200], (card.get('short_description') or '')[:300]))
    db.commit()


def look(db, limit=400):
    """Check due Spaces; record the running ones. Returns (looked, recorded, dropped)."""
    now = int(time.time())
    rows = db.execute('SELECT id, created, tries, sdk, title, descr FROM hf_pending WHERE next <= ? ORDER BY created DESC LIMIT ?',
                      (now, limit)).fetchall()
    kept = dropped = 0
    for sid, created, tries, sdk, title, descr in rows:
        try:
            d, _ = get(f'{API}/{urllib.parse.quote(sid, safe="/")}')
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 404):          # deleted or made private
                db.execute('DELETE FROM hf_pending WHERE id=?', (sid,)); dropped += 1; continue
            if e.code == 429 or e.code >= 500:
                raise
            # Other errors are about this one Space (the Hub answers 400 for some broken ones): try it again
            # later, give up after two days, and go on with the rest instead of ending the round.
            if now - created > GIVE_UP:
                db.execute('DELETE FROM hf_pending WHERE id=?', (sid,)); dropped += 1
            else:
                db.execute('UPDATE hf_pending SET next=?, tries=tries+1 WHERE id=?', (now + AGAIN, sid))
            db.commit()
            continue
        stage = (d.get('runtime') or {}).get('stage', '')
        host = d.get('host')
        if stage in ('RUNNING', 'SLEEPING') and host and not d.get('disabled'):
            extra = json.dumps({'space': sid, 'sdk': sdk, 'title': title, 'description': descr, 'likes': d.get('likes', 0)})
            kept += record(db, host.rstrip('/') + '/', 'hf', sid, extra, platform='huggingface', when=created)
            db.execute('DELETE FROM hf_pending WHERE id=?', (sid,))
        elif stage in DEAD or now - created > GIVE_UP:
            db.execute('DELETE FROM hf_pending WHERE id=?', (sid,)); dropped += 1
        else:                                       # building, starting, paused: look again later
            db.execute('UPDATE hf_pending SET next=?, tries=tries+1 WHERE id=?', (now + AGAIN, sid))
        db.commit()
        time.sleep(0.5)
    return len(rows), kept, dropped


def main():
    db = connect()
    setup(db)
    since = int(get_state(db, 'hf_since', int(time.time() - 86400)))   # first start: the last day's Spaces
    while True:
        try:
            spaces = new_spaces(since)
            if spaces:
                queue(db, spaces)
                since = max(ts(s['createdAt']) for s in spaces)
                set_state(db, 'hf_since', since)
            looked, kept, dropped = look(db)
            waiting = db.execute('SELECT count(*) FROM hf_pending').fetchone()[0]
            beat(db, 'hf', len(spaces), kept, f'{waiting} waiting to run')
            log('hf new spaces', len(spaces), 'looked at', looked, 'running and new', kept, 'dropped', dropped, 'waiting', waiting)
        except Exception as e:
            log('hf error', repr(e))
        time.sleep(600)


if __name__ == '__main__':
    main()
