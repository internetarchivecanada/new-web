"""Shared pieces: which hosts count as "new web of apps" sites, how a URL maps to a site, and the database."""
import os, re, sqlite3, time, urllib.parse

DB = os.environ.get('NEWWEB_DB', '/Volumes/4tb-ext/data/newweb/newweb.sqlite')
UA = 'WaybackMachineLabs-NewWebStudy/0.1 (+https://wayback-labs.sf.archive.org/)'

# Hosting platforms where people (and their AI agents) publish small sites and apps.
# Suffix -> platform name. A site on one of these is a subdomain (or, for github.io, a path).
PLATFORMS = {
    'vercel.app': 'vercel', 'netlify.app': 'netlify', 'netlify.com': 'netlify', 'pages.dev': 'cloudflare-pages',
    'workers.dev': 'cloudflare-workers', 'github.io': 'github-pages', 'gitlab.io': 'gitlab-pages',
    'fly.dev': 'fly', 'onrender.com': 'render', 'herokuapp.com': 'heroku', 'railway.app': 'railway',
    'up.railway.app': 'railway', 'replit.app': 'replit', 'repl.co': 'replit', 'replit.dev': 'replit',
    'lovable.app': 'lovable', 'lovable.dev': 'lovable', 'bolt.new': 'bolt', 'netlify.live': 'netlify',
    'v0.dev': 'v0', 'vusercontent.net': 'v0', 'streamlit.app': 'streamlit', 'hf.space': 'huggingface',
    'glitch.me': 'glitch', 'surge.sh': 'surge', 'web.app': 'firebase', 'firebaseapp.com': 'firebase',
    'deno.dev': 'deno', 'val.run': 'val-town', 'web.val.run': 'val-town', 'framer.website': 'framer',
    'framer.app': 'framer', 'webflow.io': 'webflow', 'carrd.co': 'carrd', 'neocities.org': 'neocities',
    'codeberg.page': 'codeberg-pages', 'pythonanywhere.com': 'pythonanywhere', 'koyeb.app': 'koyeb',
    'ngrok.app': 'ngrok', 'ngrok-free.app': 'ngrok', 'tiiny.site': 'tiiny', 'super.site': 'super',
    'notion.site': 'notion', 'claude.site': 'claude', 'manus.space': 'manus', 'base44.app': 'base44',
    'same.new': 'same', 'create.xyz': 'create', 'created.app': 'create', 'windsurf.build': 'windsurf',
    'readthedocs.io': 'readthedocs', 'blogspot.com': None, 'wordpress.com': None, 'substack.com': None,
}
# Hosts that are platforms' own pages, not user sites.
NOT_SITES = {'www', 'app', 'api', 'docs', 'blog', 'status', 'dashboard', 'help', 'support', 'cdn', 'static'}
# Big sites that Show HN posts often point to but that are not new sites in themselves.
BIG = re.compile(r'(^|\.)(github\.com|gitlab\.com|youtube\.com|youtu\.be|x\.com|twitter\.com|apps\.apple\.com|'
                 r'play\.google\.com|chromewebstore\.google\.com|addons\.mozilla\.org|medium\.com|reddit\.com|'
                 r'news\.ycombinator\.com|producthunt\.com|npmjs\.com|pypi\.org|crates\.io|huggingface\.co|'
                 r'arxiv\.org|google\.com|docs\.google\.com|drive\.google\.com|linkedin\.com|bsky\.app|'
                 r'archive\.org|wikipedia\.org|substack\.com|marketplace\.visualstudio\.com)$')


# Reference and vendor sites that show-and-tell posts link to but that are not the thing being shown.
REFERENCE = re.compile(r'(^|\.)(wikipedia\.org|mozilla\.org|stackoverflow\.com|stackexchange\.com|w3\.org|w3schools\.com|'
                       r'react\.dev|reactjs\.org|nextjs\.org|vuejs\.org|svelte\.dev|angular\.dev|nodejs\.org|deno\.com|bun\.sh|'
                       r'python\.org|rust-lang\.org|go\.dev|typescriptlang\.org|tailwindcss\.com|vitejs\.dev|astro\.build|'
                       r'vercel\.com|netlify\.com|cloudflare\.com|supabase\.com|firebase\.google\.com|aws\.amazon\.com|'
                       r'anthropic\.com|claude\.ai|claude\.com|openai\.com|chatgpt\.com|cursor\.com|cursor\.sh|lovable\.dev|'
                       r'bolt\.new|v0\.dev|v0\.app|replit\.com|docker\.com|kubernetes\.io|postgresql\.org|mongodb\.com|'
                       r'buymeacoffee\.com|ko-fi\.com|patreon\.com|gumroad\.com|discord\.gg|discord\.com|t\.me|'
                       r'instagram\.com|facebook\.com|tiktok\.com|threads\.net|mastodon\.social|dev\.to|hashnode\.com|'
                       r'substack\.com|notion\.so|figma\.com|canva\.com|unsplash\.com|shields\.io|imgur\.com|giphy\.com|'
                       r'doi\.org|nih\.gov|researchgate\.net|springer\.com|sciencedirect\.com|nature\.com|acm\.org|ieee\.org|acsm\.org)$'
                       r'|\.(edu|gov|mil|ac\.[a-z]{2}|edu\.[a-z]{2}|gov\.[a-z]{2})$', re.I)


# Addresses that hold many separate sites, one per first path segment (like <user>.github.io/<project>).
PATH_SITES = {'wayback-labs.sf.archive.org'}


def platform_of(host):
    """Return (platform, suffix) when host is a user site on a known platform, else (None, None)."""
    host = host.lower().rstrip('.')
    parts = host.split('.')
    for i in range(1, len(parts)):
        suf = '.'.join(parts[i:])
        if suf in PLATFORMS:
            sub = parts[:i]
            if not PLATFORMS[suf] or sub[-1] in NOT_SITES and len(sub) == 1:
                return None, None
            return PLATFORMS[suf], suf
    return None, None


def site_key(url):
    """Normalise a URL to the site it belongs to. github.io/gitlab.io project sites keep their first path segment."""
    try:
        u = urllib.parse.urlsplit(url.strip())
    except ValueError:
        return None
    if u.scheme not in ('http', 'https') or not u.hostname:
        return None
    host = u.hostname.lower().rstrip('.')
    if host.startswith('www.'):
        host = host[4:]
    if host in PATH_SITES:              # many sites under one address, one per first path segment
        seg = [s for s in u.path.split('/') if s][:1]
        return f'{host}/{seg[0]}' if seg else host
    if host.endswith(('.github.io', '.gitlab.io', '.codeberg.page')):
        seg = [s for s in u.path.split('/') if s][:1]
        if seg and '.' not in seg[0]:
            return f'{host}/{seg[0]}'
    return host


def connect():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    db = sqlite3.connect(DB, timeout=60)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA busy_timeout=60000')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS sites(
        site TEXT PRIMARY KEY, platform TEXT, first_url TEXT, first_source TEXT,
        first_seen INTEGER, last_seen INTEGER, mentions INTEGER DEFAULT 1, sources TEXT,
        checks_done INTEGER DEFAULT 0, next_check INTEGER, last_verdict TEXT);
    CREATE INDEX IF NOT EXISTS sites_next ON sites(next_check);
    CREATE TABLE IF NOT EXISTS mentions(
        site TEXT, url TEXT, source TEXT, ref TEXT, seen INTEGER, extra TEXT,
        UNIQUE(source, ref, url));
    CREATE INDEX IF NOT EXISTS mentions_site ON mentions(site);
    CREATE TABLE IF NOT EXISTS checks(
        site TEXT, url TEXT, checked INTEGER, age_days REAL, status INTEGER, verdict TEXT,
        final_url TEXT, bytes INTEGER, title TEXT, error TEXT);
    CREATE INDEX IF NOT EXISTS checks_site ON checks(site, checked);
    CREATE TABLE IF NOT EXISTS captures(site TEXT PRIMARY KEY, url TEXT, job_id TEXT, submitted INTEGER,
        finished INTEGER, status TEXT, timestamp TEXT, http_status INTEGER, message TEXT);
    CREATE TABLE IF NOT EXISTS profiles(site TEXT PRIMARY KEY, shot INTEGER, ok INTEGER, thumb TEXT, title TEXT,
        description TEXT, lang TEXT, tech TEXT, topics TEXT, flags TEXT, starter INTEGER, final_url TEXT, error TEXT);
    CREATE TABLE IF NOT EXISTS state(k TEXT PRIMARY KEY, v TEXT);
    CREATE TABLE IF NOT EXISTS heartbeat(source TEXT PRIMARY KEY, at INTEGER, seen INTEGER, kept INTEGER, note TEXT);
    ''')
    return db


def record(db, url, source, ref, extra=None, platform=None, when=None):
    """Store one mention; create or update the site. Returns True when the site is new."""
    site = site_key(url)
    if not site:
        return False
    if platform is None:
        platform = platform_of(site.split('/')[0])[0] or 'custom'
    now = int(when or time.time())
    cur = db.execute('INSERT OR IGNORE INTO mentions VALUES(?,?,?,?,?,?)', (site, url[:2000], source, ref, now, extra))
    if not cur.rowcount:
        return False
    new = db.execute('INSERT OR IGNORE INTO sites(site, platform, first_url, first_source, first_seen, last_seen, sources, next_check)'
                     ' VALUES(?,?,?,?,?,?,?,?)', (site, platform, url[:2000], source, now, now, source, max(now, int(time.time())) + 3600)).rowcount
    if not new:
        db.execute("UPDATE sites SET last_seen=?, mentions=mentions+1, sources=CASE WHEN instr(','||sources||',', ','||?||',')"
                   " THEN sources ELSE sources||','||? END WHERE site=?", (now, source, source, site))
    return bool(new)


def beat(db, source, seen, kept, note=''):
    db.execute('INSERT OR REPLACE INTO heartbeat VALUES(?,?,?,?,?)', (source, int(time.time()), seen, kept, note))
    db.commit()


def get_state(db, k, default=None):
    r = db.execute('SELECT v FROM state WHERE k=?', (k,)).fetchone()
    return r[0] if r else default


def set_state(db, k, v):
    db.execute('INSERT OR REPLACE INTO state VALUES(?,?)', (k, str(v)))
    db.commit()


def log(*a):
    print(time.strftime('%Y-%m-%d %H:%M:%S'), *a, flush=True)
