"""Bluesky posts via Jetstream (the public JSON firehose). Keeps links to sites on known hosting platforms.
Stores only the link, the time and a one-way hash of the post's address (to count each post once): no author
identifier, handle or post text."""
import asyncio, hashlib, json, time
import websockets
from .common import connect, record, beat, log, platform_of, site_key

JETSTREAM = 'wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post'


def links(rec):
    out = set()
    for f in rec.get('facets') or []:
        for feat in f.get('features') or []:
            if feat.get('$type') == 'app.bsky.richtext.facet#link' and feat.get('uri'):
                out.add(feat['uri'])
    emb = rec.get('embed') or {}
    for e in (emb, emb.get('media') or {}):
        ext = e.get('external') or {}
        if ext.get('uri'):
            out.add(ext['uri'])
    return out


async def run(db):
    seen = kept = 0
    last = time.time()
    async with websockets.connect(JETSTREAM, max_size=2**22, ping_interval=30) as ws:
        log('bluesky connected')
        async for msg in ws:
            seen += 1
            ev = json.loads(msg)
            c = ev.get('commit') or {}
            if c.get('operation') != 'create':
                continue
            for url in links(c.get('record') or {}):
                site = site_key(url)
                if site and platform_of(site.split('/')[0])[0]:
                    ref = hashlib.sha256(f"at://{ev['did']}/{c['collection']}/{c['rkey']}".encode()).hexdigest()[:20]
                    kept += record(db, url, 'bluesky', ref)
                    db.commit()
            if time.time() - last > 60:
                beat(db, 'bluesky', seen, kept)
                log('bluesky', 'posts', seen, 'new sites', kept)
                last = time.time()


def main():
    db = connect()
    while True:
        try:
            asyncio.run(run(db))
        except Exception as e:
            log('bluesky error', repr(e))
        time.sleep(15)


if __name__ == '__main__':
    main()
