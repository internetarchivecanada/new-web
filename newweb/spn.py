"""Sends each newly discovered site's shared URL to Save Page Now (SPN2), using the IA keys in
~/.config/internetarchive/ia.ini. A few captures in flight at a time; backs off when SPN says to.
Skips URLs the Wayback Machine already captured in the last 30 days.

If the account is refused (HTTP 401, as happened from 2026-11-14 although the keys still work on archive.org),
it falls back to anonymous saves (GET /save/<url>), one every 20 seconds, and re-checks the account hourly."""
import configparser, json, os, time, urllib.error, urllib.parse, urllib.request
from .common import connect, beat, log

INFLIGHT = int(os.environ.get('NEWWEB_SPN_INFLIGHT', 6))
cfg = configparser.ConfigParser()
cfg.read(os.path.expanduser('~/.config/internetarchive/ia.ini'))
H = {'Authorization': f"LOW {cfg['s3']['access']}:{cfg['s3']['secret']}", 'Accept': 'application/json',
     'User-Agent': 'WaybackMachineLabs-NewWebStudy/0.1'}


def call(url, data=None):
    body = urllib.parse.urlencode(data).encode() if data else None
    return json.load(urllib.request.urlopen(urllib.request.Request(url, body, H), timeout=60))


def account_ok():
    try:
        call('https://web.archive.org/save/status/user')
        return True
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False
        raise


def anonymous(db, seconds):
    """Anonymous Save Page Now: synchronous, slow and rate-limited, so one URL at a time."""
    end, n, ok, pause = time.time() + seconds, 0, 0, 20
    while time.time() < end:
        rows = pick(db, 1, {})
        if not rows:
            time.sleep(60); continue
        site, url = rows[0]
        now = int(time.time())
        req = urllib.request.Request('https://web.archive.org/save/' + url, headers={'User-Agent': H['User-Agent']}, method='GET')
        status, ts, http, msg = 'error', None, None, ''
        try:
            r = urllib.request.urlopen(req, timeout=180)
            final = r.geturl(); http = r.status
            m = __import__('re').search(r'/web/(\d{14})/', final)
            status, ts = ('success', m.group(1)) if m else ('unknown', None)
            pause = 20
        except urllib.error.HTTPError as e:
            http, msg = e.code, e.read(300).decode('utf8', 'replace')
            if e.code == 429:
                log('spn anonymous 429, waiting'); pause = min(pause * 2, 600); time.sleep(pause); continue
            status = 'refused'
        except Exception as e:
            msg = repr(e)[:300]
        db.execute('INSERT OR REPLACE INTO captures VALUES(?,?,?,?,?,?,?,?,?)',
                   (site, url, 'anonymous', now, int(time.time()), status, ts, http, msg[:300]))
        db.commit()
        n += 1; ok += status == 'success'
        if n % 10 == 0:
            beat(db, 'spn', n, ok, 'anonymous mode'); log('spn anonymous', n, 'success', ok)
        time.sleep(pause)


def pick(db, n, busy):
    q = ('SELECT s.site, s.first_url FROM sites s LEFT JOIN captures c ON c.site = s.site '
         'WHERE c.site IS NULL ORDER BY s.first_seen DESC LIMIT ?')   # newest first: they are the likeliest to vanish
    return [r for r in db.execute(q, (n + len(busy),)) if r[0] not in busy][:n]


def main():
    db = connect()
    inflight = {}          # site -> (job_id, url, submitted)
    done = ok = 0
    backoff = 0
    last_beat = 0
    next_auth = 0
    while True:
        if not inflight and time.time() >= next_auth and not account_ok():
            log('spn account refused (401): anonymous mode for 1 h')
            anonymous(db, 3600)
            continue
        if time.time() >= next_auth:
            next_auth = time.time() + 3600
        # Submit
        refused = False
        if time.time() >= backoff:
            for site, url in pick(db, INFLIGHT - len(inflight), inflight):
                try:
                    r = call('https://web.archive.org/save', {'url': url, 'skip_first_archive': 1,
                                                              'if_not_archived_within': '30d', 'delay_wb_availability': 0})
                except urllib.error.HTTPError as e:
                    log('spn submit HTTP', e.code, site)
                    if e.code == 401:
                        # The status check can pass while saves are refused (2026-11-14): go anonymous, record nothing.
                        refused = True
                        break
                    if e.code in (429, 503, 502):
                        backoff = time.time() + 120
                        break
                    r = {'status': 'error', 'message': f'HTTP {e.code}'}
                except Exception as e:
                    log('spn submit error', repr(e)); backoff = time.time() + 60; break
                now = int(time.time())
                if r.get('job_id'):
                    inflight[site] = (r['job_id'], url, now)
                    db.execute('INSERT OR REPLACE INTO captures(site,url,job_id,submitted,status) VALUES(?,?,?,?,?)',
                               (site, url, r['job_id'], now, 'pending'))
                elif 'already' in (r.get('message') or '') or r.get('timestamp'):
                    db.execute('INSERT OR REPLACE INTO captures VALUES(?,?,?,?,?,?,?,?,?)',
                               (site, url, None, now, now, 'recent', r.get('timestamp'), None, r.get('message')))
                else:
                    msg = r.get('message') or json.dumps(r)[:300]
                    if r.get('status_ext') in ('error:user-session-limit', 'error:too-many-daily-captures') or 'limit' in msg.lower():
                        log('spn limit', msg); backoff = time.time() + 300; break
                    db.execute('INSERT OR REPLACE INTO captures VALUES(?,?,?,?,?,?,?,?,?)',
                               (site, url, None, now, now, 'refused', None, None, msg[:300]))
            db.commit()
        if refused and not inflight:
            log('spn save refused (401): anonymous mode for 1 h')
            anonymous(db, 3600)
            next_auth = time.time()
            continue
        # Poll
        time.sleep(20)
        for site, (job, url, sub) in list(inflight.items()):
            try:
                st = call('https://web.archive.org/save/status/' + job)
            except Exception as e:
                log('spn status error', repr(e)); time.sleep(30); break
            if st.get('status') == 'pending' and time.time() - sub < 900:
                continue
            status = st.get('status') if st.get('status') != 'pending' else 'timeout'
            db.execute('UPDATE captures SET finished=?, status=?, timestamp=?, http_status=?, message=? WHERE site=?',
                       (int(time.time()), status, st.get('timestamp'), st.get('http_status'),
                        (st.get('message') or st.get('status_ext') or '')[:300], site))
            del inflight[site]
            done += 1; ok += status == 'success'
        db.commit()
        if time.time() - last_beat > 60:
            beat(db, 'spn', done, ok, f'{len(inflight)} in flight')
            log('spn finished', done, 'success', ok, 'in flight', len(inflight))
            last_beat = time.time()


if __name__ == '__main__':
    main()
