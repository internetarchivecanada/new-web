"""Writes the explorer's data: <EXPLORER>/data/sites.json, data/stats.json and sitemap.xml.

Only sites that were looked at (shots.py) and not flagged as adult, phishing, gambling or scam go in sites.json.
Flagged sites go in data/flagged.json (same fields plus 'flags'), which the explorer loads only when a viewer turns
on the Flagged filter, and never in the sitemap.
Nothing about who posted a link goes in: for Hacker News the story itself is public and linked;
for GitHub the public repository; for Bluesky only that it was posted there.
"""
import json, os, time, urllib.parse
from collections import Counter
from .common import connect, log
from .classify import GROUP

EXPLORER = os.environ.get('NEWWEB_EXPLORER', '/opt/services/new-web/public')
BASE = 'https://wayback-labs.sf.archive.org/new-web/'
SOURCES = {'hn': 'Hacker News', 'bluesky': 'Bluesky', 'github': 'GitHub', 'hf': 'Hugging Face',
           'aigh': 'GitHub, AI-written code', 'mastodon': 'Mastodon', 'devto': 'DEV Community',
           'gallery': "AI tools' galleries", 'labs': 'Wayback Machine Labs', 'ct': 'Certificate logs'}

Q = '''SELECT s.site, s.first_url, s.platform, s.first_seen, s.sources, s.mentions, s.last_verdict, s.checks_done,
          p.thumb, p.title, p.description, p.lang, p.tech, p.topics, p.starter, c.timestamp, p.flags,
          (SELECT ref FROM mentions m WHERE m.site = s.site AND m.source = 'hn' LIMIT 1),
          (SELECT json_extract(extra, '$.repo') FROM mentions m WHERE m.site = s.site AND m.source IN ('github', 'aigh') LIMIT 1),
          (SELECT max(json_extract(extra, '$.points')) FROM mentions m WHERE m.site = s.site AND m.source = 'hn'),
          (SELECT ref FROM mentions m WHERE m.site = s.site AND m.source = 'hf' LIMIT 1),
          (SELECT group_concat(DISTINCT json_extract(extra, '$.tool')) FROM mentions m
             WHERE m.site = s.site AND json_extract(extra, '$.tool') IS NOT NULL),
          (SELECT json_extract(extra, '$.article') FROM mentions m WHERE m.site = s.site AND m.source = 'devto' LIMIT 1)
   FROM sites s JOIN profiles p ON p.site = s.site LEFT JOIN captures c ON c.site = s.site AND c.status = 'success'
   WHERE p.ok = 1 AND (p.flags = '[]') = ?
   ORDER BY s.first_seen DESC'''

FIELDS = ['site', 'url', 'platform', 'seen', 'sources', 'mentions', 'status', 'thumb', 'title', 'desc', 'lang',
          'tech', 'topics', 'starter', 'wayback', 'hn', 'repo', 'points', 'space', 'article']


def status_word(v):
    if not v:
        return 'unchecked'
    if v in ('up', 'moved'):
        return v
    if v.startswith('gone') or v == 'asleep':
        return 'gone'
    return 'trouble'          # error, blocked, unreachable: may come back


def rows(db, flagged=False):
    for r in db.execute(Q, (0 if flagged else 1,)):
        (site, url, plat, seen, sources, mentions, verdict, checks, thumb, title, desc, lang, tech, topics,
         starter, ts, flags, hn, repo, points, space, tools, article) = r
        tech = json.loads(tech or '[]')
        tech = [t for t in (tools or '').split(',') if t and t not in tech] + tech   # the agent first
        row = [site, url, plat, seen, [s for s in (sources or '').split(',') if s], mentions, status_word(verdict),
               thumb, (title or '')[:160], (desc or '')[:240], (lang or '').split('-')[0].lower()[:5],
               tech, json.loads(topics or '[]'), starter, ts, hn, repo, points, space, article]
        yield row + [json.loads(flags)] if flagged else row


FIRST_PAGE = 60          # the explorer's PER_PAGE


def write(db):
    data = list(rows(db))
    out = os.path.join(EXPLORER, 'data')
    os.makedirs(out, exist_ok=True)
    total = db.execute('SELECT count(*) FROM sites').fetchone()[0]
    looked = db.execute('SELECT count(*), sum(ok) FROM profiles').fetchone()
    flagged = db.execute("SELECT count(*) FROM profiles WHERE ok = 1 AND flags != '[]'").fetchone()[0]
    saved = db.execute("SELECT count(*) FROM captures WHERE status = 'success'").fetchone()[0]
    first = db.execute('SELECT min(first_seen) FROM sites').fetchone()[0]
    stats = {'updated': int(time.time()), 'found': total, 'looked_at': looked[0], 'pictured': looked[1] or 0,
             'shown': len(data), 'held_back': flagged, 'saved': saved, 'since': first,
             'sources': SOURCES, 'fields': FIELDS}
    payload = json.dumps({'stats': stats, 'fields': FIELDS, 'tech_groups': sorted(GROUP.items()), 'sites': data}, separators=(',', ':'), ensure_ascii=False)
    tmp = os.path.join(out, 'sites.json.tmp')
    with open(tmp, 'w') as f:
        f.write(payload)
    os.replace(tmp, os.path.join(out, 'sites.json'))
    # The explorer's first screen (newest first, starter pages left out, 60 cards) in a file of a few
    # kilobytes, so the cards and their pictures show at once while sites.json (megabytes) loads.
    seen, starter = FIELDS.index('seen'), FIELDS.index('starter')
    plain = [r for r in data if not r[starter]]
    first_page = sorted(plain, key=lambda r: -r[seen])[:FIRST_PAGE]
    with open(os.path.join(out, 'first.json.tmp'), 'w') as f:
        json.dump({'stats': stats, 'fields': FIELDS, 'tech_groups': sorted(GROUP.items()), 'total': len(plain), 'sites': first_page},
                  f, separators=(',', ':'), ensure_ascii=False)
    os.replace(os.path.join(out, 'first.json.tmp'), os.path.join(out, 'first.json'))
    held = list(rows(db, flagged=True))
    with open(os.path.join(out, 'flagged.json.tmp'), 'w') as f:
        json.dump({'fields': FIELDS + ['flags'], 'sites': held}, f, separators=(',', ':'), ensure_ascii=False)
    os.replace(os.path.join(out, 'flagged.json.tmp'), os.path.join(out, 'flagged.json'))
    with open(os.path.join(out, 'stats.json.tmp'), 'w') as f:
        json.dump(stats, f)
    os.replace(os.path.join(out, 'stats.json.tmp'), os.path.join(out, 'stats.json'))
    write_sitemap(data)
    return len(data)


def write_sitemap(data):
    """The page, plus one address per filter value, so a crawler can reach every view."""
    urls = [BASE, BASE + 'about.html']
    for key, idx in (('platform', 2), ('topic', 12), ('tech', 11), ('source', 4)):
        c = Counter()
        for d in data:
            vals = d[idx] if isinstance(d[idx], list) else [d[idx]]
            c.update(v for v in vals if v)
        urls += [BASE + '?' + urllib.parse.urlencode({key: v}) for v, _ in c.most_common(60)]
    days = sorted({time.strftime('%Y-%m-%d', time.gmtime(d[3])) for d in data}, reverse=True)
    urls += [BASE + '?' + urllib.parse.urlencode({'day': d}) for d in days[:120]]
    body = ''.join(f'<url><loc>{u.replace("&", "&amp;")}</loc></url>\n' for u in urls)
    tmp = os.path.join(EXPLORER, 'sitemap.xml.tmp')
    with open(tmp, 'w') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                + body + '</urlset>\n')
    os.replace(tmp, os.path.join(EXPLORER, 'sitemap.xml'))


if __name__ == '__main__':
    log('export', write(connect()), 'sites')
