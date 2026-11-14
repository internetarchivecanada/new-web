"""Certificate Transparency (CT) logs via the certstream feed. Keeps non-wildcard certificate names under
known hosting platforms (most platforms use one wildcard certificate, so this catches only some), and
counts every name it sees so the pilot can say how much the CT stream covers."""
import asyncio, json, time
import websockets
from .common import connect, record, beat, log, platform_of

FEED = 'wss://certstream.calidog.io/'


async def run(db):
    certs = names = kept = 0
    last = time.time()
    async with websockets.connect(FEED, max_size=2**22, ping_interval=30) as ws:
        log('certstream connected')
        async for msg in ws:
            ev = json.loads(msg)
            if ev.get('message_type') != 'certificate_update':
                continue
            certs += 1
            leaf = ev['data']['leaf_cert']
            for name in leaf.get('all_domains') or []:
                names += 1
                if name.startswith('*.'):
                    continue
                if platform_of(name)[0]:
                    kept += record(db, f'https://{name}/', 'ct', f"{ev['data'].get('cert_index')}:{name}")
                    db.commit()
            if time.time() - last > 60:
                beat(db, 'ct', certs, kept, f'{names} names')
                log('ct', 'certs', certs, 'names', names, 'new sites', kept)
                last = time.time()


def main():
    db = connect()
    while True:
        try:
            asyncio.run(run(db))
        except Exception as e:
            log('ct error', repr(e))
        time.sleep(30)


if __name__ == '__main__':
    main()
