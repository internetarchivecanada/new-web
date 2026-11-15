"""Every 15 minutes: writes the running list of every discovered site (sites.tsv and a filterable index.html in
/Volumes/4tb-ext/data/newweb/list/), then the public explorer's data (export.py)."""
import html, json, os, time
from .common import connect, DB, log

OUT = os.path.join(os.path.dirname(DB), 'list')
COLS = ['site', 'platform', 'first_seen', 'first_source', 'sources', 'mentions', 'first_url', 'last_verdict',
        'checks_done', 'spn_status', 'wayback']

QUERY = '''SELECT s.site, s.platform, s.first_seen, s.first_source, s.sources, s.mentions, s.first_url, s.last_verdict,
           s.checks_done, c.status, c.timestamp FROM sites s LEFT JOIN captures c ON c.site = s.site
           ORDER BY s.first_seen DESC'''

PAGE = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>New Web Sites Found</title><style>
:root{--bg:#fff;--fg:#1a1a1a;--mute:#666;--line:#e3e3e3;--ok:#1a7f37;--bad:#b42318}
@media (prefers-color-scheme:dark){:root{--bg:#141414;--fg:#e8e8e8;--mute:#999;--line:#2c2c2c;--ok:#57c96d;--bad:#ff7b6b}}
body{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:14px/1.45 -apple-system,system-ui,sans-serif}
h1{font-size:20px;margin:0 0 4px}.sub{color:var(--mute);margin-bottom:12px}
input,select{font:inherit;padding:4px 6px;margin:0 6px 8px 0;background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:4px}
.wrap{overflow-x:auto}table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:4px 8px;border-bottom:1px solid var(--line);white-space:nowrap}
th{cursor:pointer;position:sticky;top:0;background:var(--bg)}td.u{max-width:420px;overflow:hidden;text-overflow:ellipsis}
a{color:inherit}.ok{color:var(--ok)}.bad{color:var(--bad)}.mute{color:var(--mute)}
</style></head><body><h1>New Web Sites Found</h1>
<div class="sub">__SUB__</div>
<input id="q" placeholder="Filter…" size="30"><select id="src"><option value="">All sources</option>__SRC__</select><select id="plat"><option value="">All platforms</option>__PLAT__</select><span id="n" class="mute"></span>
<div class="wrap"><table><thead><tr><th>First seen (UTC)</th><th>Site</th><th>Platform</th><th>Source</th><th>Mentions</th><th>Status</th><th>Saved</th></tr></thead><tbody id="b"></tbody></table></div>
<script>
const D=__DATA__;const b=document.getElementById('b'),q=document.getElementById('q'),src=document.getElementById('src'),plat=document.getElementById('plat'),n=document.getElementById('n');
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'})[c]);
let key=0,dir=-1;
function draw(){const f=q.value.toLowerCase(),s=src.value,p=plat.value;
 const r=D.filter(d=>(!f||(d[1]+' '+d[6]).toLowerCase().includes(f))&&(!s||d[4].split(',').includes(s))&&(!p||d[2]===p));
 r.sort((a,c)=>(a[key]>c[key]?1:a[key]<c[key]?-1:0)*dir);n.textContent=r.length.toLocaleString()+' sites';
 b.innerHTML=r.slice(0,3000).map(d=>{const v=d[7]||'not checked yet',cls=/^(up|moved)$/.test(v)?'ok':/^gone/.test(v)?'bad':'mute';
  const w=d[10]?`<a href="https://web.archive.org/web/${d[10]}/${esc(d[6])}" class="ok">${d[9]}</a>`:`<span class="${d[9]==='success'?'ok':'mute'}">${esc(d[9]||'queued')}</span>`;
  return `<tr><td>${new Date(d[0]*1000).toISOString().slice(0,16).replace('T',' ')}</td><td class="u"><a href="${esc(d[6])}" rel="noopener nofollow">${esc(d[1])}</a></td><td>${esc(d[2])}</td><td>${esc(d[4])}</td><td>${d[5]}</td><td class="${cls}">${esc(v)}</td><td>${w}</td></tr>`}).join('');}
[q,src,plat].forEach(e=>e.addEventListener('input',draw));
document.querySelectorAll('th').forEach((th,i)=>th.onclick=()=>{const k=[0,1,2,4,5,7,9][i];dir=key===k?-dir:-1;key=k;draw()});draw();
</script></body></html>'''


def write(db):
    os.makedirs(OUT, exist_ok=True)
    rows = db.execute(QUERY).fetchall()
    with open(os.path.join(OUT, 'sites.tsv.tmp'), 'w') as f:
        f.write('\t'.join(COLS) + '\n')
        for r in rows:
            r = list(r)
            r[2] = time.strftime('%Y-%m-%d %H:%M', time.gmtime(r[2]))
            wb = f'https://web.archive.org/web/{r[10]}/{r[6]}' if r[10] else ''
            f.write('\t'.join(str(x if x is not None else '').replace('\t', ' ').replace('\n', ' ') for x in r[:10] + [wb]) + '\n')
    os.replace(os.path.join(OUT, 'sites.tsv.tmp'), os.path.join(OUT, 'sites.tsv'))
    # Page columns: 0 first_seen, 1 site, 2 platform, 3 first source, 4 sources, 5 mentions, 6 url, 7 verdict,
    # 8 checks done, 9 SPN status, 10 Wayback timestamp
    data = [[r[2], r[0], r[1], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10]] for r in rows]
    saved = sum(1 for r in rows if r[9] == 'success')
    sub = (f'{len(rows):,} sites found since {time.strftime("%d %B %Y", time.gmtime(min((r[2] for r in rows), default=time.time())))}'
           f' · {saved:,} saved to the Wayback Machine · updated {time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())}'
           f' · <a href="sites.tsv">sites.tsv</a>')
    opts = lambda vals: ''.join(f'<option>{html.escape(v)}</option>' for v in vals)
    srcs = sorted({s for r in rows for s in (r[4] or '').split(',') if s})
    plats = [p for p, in db.execute('SELECT platform FROM sites GROUP BY platform ORDER BY count(*) DESC')]
    page = (PAGE.replace('__SUB__', sub).replace('__SRC__', opts(srcs)).replace('__PLAT__', opts(plats))
            .replace('__DATA__', json.dumps(data).replace('</', '<\\/')))
    with open(os.path.join(OUT, 'index.html.tmp'), 'w') as f:
        f.write(page)
    os.replace(os.path.join(OUT, 'index.html.tmp'), os.path.join(OUT, 'index.html'))
    return len(rows)


def main():
    db = connect()
    while True:
        try:
            log('list', write(db), 'sites')
            from . import export
            if os.path.isdir(os.path.dirname(export.EXPLORER)):
                log('explorer', export.write(db), 'sites shown')
        except Exception as e:
            log('list error', repr(e))
        time.sleep(900)


if __name__ == '__main__':
    main()
