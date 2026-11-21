"""GitHub repositories written with AI coding agents, and the websites they publish.

Every 10 minutes GitHub's commit search is asked for the last window's commits that an agent signed
(the "Co-authored-by" or "Generated with" lines Claude Code, Cursor, Copilot, Lovable and others add).
Each new repository is then checked for a website:
  1. its GitHub Pages site (<owner>.github.io/<repo>/), checked directly, which costs no API call;
  2. the website listed on the repository (its "homepage"), which needs one API call.
Without a GitHub token the API allows 10 searches a minute and 60 repository look-ups an hour, so the
look-ups are rationed; a read-only token in ~/.config/newweb/github.token raises that to 5,000 an hour.

Only public repositories are seen. Nothing about the people is kept beyond the public repository name.
"""
import json, os, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone
from .common import connect, record, beat, get_state, set_state, log, platform_of, site_key, BIG, UA

# (tool, search query). The tool is shown on the explorer as "built with".
QUERIES = [
    ('Claude Code', '"Generated with Claude Code"'),
    ('Claude Code', '"Co-Authored-By: Claude" noreply@anthropic.com'),
    ('Cursor', '"Co-authored-by: Cursor"'),
    ('GitHub Copilot', '"Co-authored-by: Copilot"'),
    ('Lovable', 'author:lovable-dev[bot]'),
    ('OpenAI Codex', '"Co-authored-by: Codex"'),
    ('Bolt', '"bolt.new"'),
]
WINDOW = 600            # seconds per search window
PAGES = 1               # up to 100 newest commits per query and window: keeps the volume modest
PER_ROUND = 150         # repositories checked per round (newest first); older unchecked ones are skipped
TOKEN_FILE = os.path.expanduser('~/.config/newweb/github.token')


def headers(api=True):
    h = {'User-Agent': UA}
    if api:
        h['Accept'] = 'application/vnd.github+json'
        if os.path.exists(TOKEN_FILE):
            h['Authorization'] = 'Bearer ' + open(TOKEN_FILE).read().strip()
    return h


def api(url):
    r = urllib.request.urlopen(urllib.request.Request(url, headers=headers()), timeout=60)
    return json.load(r), r.headers


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def setup(db):
    db.execute('CREATE TABLE IF NOT EXISTS ai_repos(repo TEXT PRIMARY KEY, tool TEXT, seen INTEGER, checked INTEGER, '
               'site TEXT, homepage TEXT)')
    db.execute('CREATE INDEX IF NOT EXISTS ai_repos_unchecked ON ai_repos(checked, seen)')
    db.commit()


def search(db, start, end):
    """Collect repositories with agent-signed commits between start and end. Returns new repo count."""
    new = 0
    for tool, q in QUERIES:
        for page in range(1, PAGES + 1):
            qs = urllib.parse.urlencode({'q': f'{q} committer-date:{iso(start)}..{iso(end)}', 'sort': 'committer-date',
                                         'order': 'desc', 'per_page': 100, 'page': page})
            try:
                d, _ = api('https://api.github.com/search/commits?' + qs)
            except urllib.error.HTTPError as e:
                if e.code in (403, 429):
                    log('aicommits search rate limited, waiting'); time.sleep(65); continue
                if e.code == 422:      # past the 1,000-result window
                    break
                raise
            for it in d.get('items', []):
                repo = it.get('repository') or {}
                if repo.get('fork') or repo.get('private'):
                    continue
                new += db.execute('INSERT OR IGNORE INTO ai_repos(repo, tool, seen) VALUES(?,?,?)',
                                  (repo['full_name'], tool, int(time.time()))).rowcount
            db.commit()
            time.sleep(7)      # stays under 10 searches a minute without a token
            if len(d.get('items', [])) < 100:
                break
    return new


def pages_url(repo):
    owner, name = repo.split('/', 1)
    if name.lower() == f'{owner.lower()}.github.io':
        return f'https://{owner.lower()}.github.io/'
    return f'https://{owner.lower()}.github.io/{name}/'


def answers(url):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=headers(api=False), method='GET'), timeout=20)
        return r.status < 400
    except Exception:
        return False


def check(db, budget):
    """Look for each new repository's website. `budget` = API look-ups allowed this round."""
    kept = looked = 0
    rows = db.execute('SELECT repo, tool, seen FROM ai_repos WHERE checked IS NULL ORDER BY seen DESC LIMIT ?', (PER_ROUND,)).fetchall()
    for repo, tool, seen in rows:
        found = []
        if answers(pages_url(repo)):
            found.append(pages_url(repo))
        homepage = None
        if budget > 0:
            try:
                d, _ = api('https://api.github.com/repos/' + repo)
                budget -= 1; looked += 1
                homepage = (d.get('homepage') or '').strip()
                if homepage and not homepage.startswith('http'):
                    homepage = 'https://' + homepage
                site = site_key(homepage) if homepage else None
                if site and not BIG.search(site.split('/')[0]) and homepage not in found:
                    found.append(homepage)
            except urllib.error.HTTPError as e:
                if e.code in (403, 429):
                    budget = 0
                elif e.code != 404:
                    raise
        extra = json.dumps({'repo': repo, 'tool': tool})
        for url in found:
            kept += record(db, url, 'aigh', repo, extra)
        db.execute('UPDATE ai_repos SET checked=?, site=?, homepage=? WHERE repo=?',
                   (int(time.time()), found[0] if found else None, homepage, repo))
        db.commit()
    # Whatever is left over is skipped (checked = 0), so the queue never grows without bound.
    db.execute('UPDATE ai_repos SET checked = 0 WHERE checked IS NULL AND seen < ?', (int(time.time()) - 1800,))
    db.commit()
    return len(rows), looked, kept


def main():
    db = connect()
    setup(db)
    end_done = int(get_state(db, 'aigh_until', int(time.time()) - 3600))
    while True:
        try:
            now = int(time.time()) - 120          # search results lag a little
            new = 0
            while end_done + WINDOW <= now:
                new += search(db, end_done, end_done + WINDOW)
                end_done += WINDOW
                set_state(db, 'aigh_until', end_done)
            budget = 4000 if os.path.exists(TOKEN_FILE) else 9   # ~60 an hour without a token
            rows, looked, kept = check(db, budget)
            waiting = db.execute('SELECT count(*) FROM ai_repos WHERE checked IS NULL').fetchone()[0]
            beat(db, 'aigh', new, kept, f'{waiting} repositories waiting')
            log('aicommits new repos', new, 'checked', rows, 'look-ups', looked, 'new sites', kept, 'waiting', waiting)
        except Exception as e:
            log('aicommits error', repr(e))
        time.sleep(WINDOW)


if __name__ == '__main__':
    main()
