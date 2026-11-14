"""Prints a summary: collectors' heartbeats, new sites per day and source, platforms, and survival by check age."""
import time
from .common import connect

db = connect()
now = time.time()
print('== collectors')
for src, at, seen, kept, note in db.execute('SELECT * FROM heartbeat ORDER BY source'):
    print(f'  {src:9} last beat {int(now - at)} s ago, seen {seen}, new sites {kept} {note or ""}')
print('== sites:', db.execute('SELECT count(*) FROM sites').fetchone()[0],
      ' mentions:', db.execute('SELECT count(*) FROM mentions').fetchone()[0])
print('== new sites per day (UTC) by first source')
for row in db.execute("SELECT date(first_seen,'unixepoch') d, first_source, count(*) FROM sites "
                      "GROUP BY d, first_source ORDER BY d DESC, first_source LIMIT 40"):
    print('  ', *row)
print('== top platforms')
for row in db.execute('SELECT platform, count(*) n FROM sites GROUP BY platform ORDER BY n DESC LIMIT 25'):
    print('  ', *row)
print('== latest verdict by check number (1 = ~1 h, 2 = 1 d, 3 = 7 d, 4 = 30 d, 5 = 60 d, 6 = 90 d)')
for row in db.execute('SELECT checks_done, last_verdict, count(*) FROM sites WHERE checks_done>0 '
                      'GROUP BY 1, 2 ORDER BY 1, 3 DESC'):
    print('  ', *row)
