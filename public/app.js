// New Web Explorer: loads data/sites.json and filters it in the browser. Every view has its own address
// (the filters are in the query string), and "More" is a real link, so the views can be archived.
(function () {
  'use strict';
  const PER_PAGE = 60;
  const form = document.getElementById('filters');
  const grid = document.getElementById('grid');
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const KEYS = ['q', 'sort', 'since', 'source', 'platform', 'tech', 'topic', 'lang', 'status', 'saved', 'starters', 'flagged', 'day', 'page'];
  const TECH_GROUP = {};
  const STATUS = { up: 'Up', moved: 'Moved', gone: 'Gone', trouble: 'Not answering', unchecked: 'Not checked yet' };
  const LANG = new Intl.DisplayNames(['en'], { type: 'language' });
  const langName = (c) => { try { return c ? LANG.of(c) : 'Not stated'; } catch (e) { return c; } };
  const PLATFORM = { 'github-pages': 'GitHub Pages', 'cloudflare-pages': 'Cloudflare Pages', 'cloudflare-workers': 'Cloudflare Workers',
    vercel: 'Vercel', netlify: 'Netlify', huggingface: 'Hugging Face', custom: 'Own domain', fly: 'Fly.io', render: 'Render',
    heroku: 'Heroku', railway: 'Railway', replit: 'Replit', lovable: 'Lovable', firebase: 'Firebase', surge: 'Surge',
    neocities: 'Neocities', carrd: 'Carrd', readthedocs: 'Read the Docs', 'gitlab-pages': 'GitLab Pages', streamlit: 'Streamlit',
    glitch: 'Glitch', deno: 'Deno Deploy', 'val-town': 'Val Town', framer: 'Framer', webflow: 'Webflow', notion: 'Notion',
    'codeberg-pages': 'Codeberg Pages', bolt: 'Bolt', v0: 'v0', base44: 'Base44', manus: 'Manus', claude: 'Claude' };
  const platName = (p) => PLATFORM[p] || p;
  // Flagged sites (adult, gambling, phishing, scam) are in a separate file, loaded only when a viewer asks for them.
  const FLAG = { adult: 'Adult', gambling: 'Gambling', phishing: 'Phishing', scam: 'Scam' };
  let ALL = [], FLAGGED = null, SOURCES = {}, STATS = {};
  const rowsToObjects = (j) => j.sites.map((r) => { const d = {}; j.fields.forEach((k, i) => { d[k] = r[i]; }); return d; });

  function params() {
    const u = new URLSearchParams(location.search), o = {};
    KEYS.forEach((k) => { if (u.get(k)) o[k] = u.get(k); });
    return o;
  }
  function href(o) {
    const u = new URLSearchParams();
    KEYS.forEach((k) => { if (o[k]) u.set(k, o[k]); });
    const s = u.toString();
    return s ? '?' + s : './';
  }
  const day = (t) => new Date(t * 1000).toISOString().slice(0, 10);
  const fmtDate = (t) => new Date(t * 1000).toLocaleDateString('en', { day: 'numeric', month: 'short', year: 'numeric' });
  const tsDate = (ts) => fmtDate(Date.UTC(+ts.slice(0, 4), +ts.slice(4, 6) - 1, +ts.slice(6, 8)) / 1000);

  function filter(o, ignore) {
    const q = (o.q || '').toLowerCase().trim();
    const now = Date.now() / 1000;
    const pool = o.flagged ? (FLAGGED || []) : ALL;
    return pool.filter((d) => {
      if (!o.starters && d.starter) return false;
      if (o.flagged && o.flagged !== 'all' && !d.flags.includes(o.flagged)) return false;
      if (q && !(d.title + ' ' + d.site + ' ' + d.desc).toLowerCase().includes(q)) return false;
      if (ignore !== 'since' && o.since && d.seen < now - o.since * 86400) return false;
      if (ignore !== 'day' && o.day && day(d.seen) !== o.day) return false;
      if (ignore !== 'source' && o.source && !d.sources.includes(o.source)) return false;
      if (ignore !== 'platform' && o.platform && d.platform !== o.platform) return false;
      if (ignore !== 'tech' && o.tech && !d.tech.includes(o.tech)) return false;
      if (ignore !== 'topic' && o.topic && !(o.topic === '_none' ? !d.topics.length : d.topics.includes(o.topic))) return false;
      if (ignore !== 'lang' && o.lang && d.lang !== (o.lang === '_none' ? '' : o.lang)) return false;
      if (ignore !== 'status' && o.status && d.status !== o.status) return false;
      if (ignore !== 'saved' && o.saved && !!d.wayback !== (o.saved === '1')) return false;
      return true;
    });
  }

  // Each menu shows counts for the other filters as they are set.
  function fillSelect(name, o, values, label, extra) {
    const sel = form.elements[name], keep = o[name] || '';
    const first = sel.options[0].outerHTML;
    const c = new Map();
    filter(o, name).forEach((d) => values(d).forEach((v) => c.set(v, (c.get(v) || 0) + 1)));
    if (keep && !c.has(keep)) c.set(keep, 0);
    let opts = [...c.entries()].sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(b[0]));
    let html = first;
    if (extra) html += extra(c);
    let lastGroup = null;
    if (name === 'tech') {
      opts.sort((a, b) => (TECH_GROUP[a[0]] || '').localeCompare(TECH_GROUP[b[0]] || '') || b[1] - a[1]);
    }
    opts.forEach(([v, n]) => {
      if (v === '_none') return;
      if (name === 'tech' && TECH_GROUP[v] !== lastGroup) {
        if (lastGroup !== null) html += '</optgroup>';
        lastGroup = TECH_GROUP[v];
        html += '<optgroup label="' + esc(lastGroup || 'Other') + '">';
      }
      html += '<option value="' + esc(v) + '">' + esc(label(v)) + ' (' + n.toLocaleString() + ')</option>';
    });
    if (lastGroup !== null) html += '</optgroup>';
    sel.innerHTML = html;
    sel.value = keep;
  }

  function card(d) {
    const wb = d.wayback ? 'https://web.archive.org/web/' + d.wayback + '/' + d.url : 'https://web.archive.org/web/*/' + d.url;
    const host = d.site;
    const title = d.title || host;
    const chips = [];
    chips.push('<a class="chip host" href="' + esc(href({ platform: d.platform })) + '">' + esc(platName(d.platform)) + '</a>');
    d.tech.filter((t) => t !== platName(d.platform)).slice(0, 4).forEach((t) => chips.push('<a class="chip tech" href="' + esc(href({ tech: t })) + '">' + esc(t) + '</a>'));
    d.topics.forEach((t) => chips.push('<a class="chip topic" href="' + esc(href({ topic: t })) + '">' + esc(t) + '</a>'));
    const where = d.sources.map((s) => {
      if (s === 'hn' && d.hn) return '<a href="https://news.ycombinator.com/item?id=' + esc(d.hn) + '">Hacker News' + (d.points ? ' (' + d.points + ' points)' : '') + '</a>';
      if (s === 'github' && d.repo) return '<a href="https://github.com/' + esc(d.repo) + '">GitHub</a>';
      if (s === 'aigh' && d.repo) return '<a href="https://github.com/' + esc(d.repo) + '">GitHub (AI-written code)</a>';
      if (s === 'devto' && d.article) return '<a href="' + esc(d.article) + '">DEV Community</a>';
      if (s === 'hf' && d.space) return '<a href="https://huggingface.co/spaces/' + esc(d.space) + '">Hugging Face</a>';
      return esc(SOURCES[s] || s);
    }).join(', ');
    const flags = d.flags || [];
    flags.forEach((f) => chips.unshift('<span class="chip flag">' + esc(FLAG[f] || f) + '</span>'));
    // No live link to a page flagged as phishing: only the Wayback copy.
    const live = flags.includes('phishing') ? '<span class="dead">No live link (phishing)</span>'
      : d.status === 'gone' ? '<span class="dead">Live site gone</span>'
      : '<a href="' + esc(d.url) + '" rel="nofollow noopener noreferrer">Live site&nbsp;↗</a>';
    const img = d.thumb ? '<img src="thumbs/' + esc(d.thumb) + '" alt="" loading="lazy" width="480" height="300">' : '<span class="noimg">No picture</span>';
    const shot = flags.length && d.thumb
      ? '<div class="shot veiled">' + img + '<button type="button" class="unveil">Show picture</button>' +
        '<span class="status s-' + esc(d.status) + '">' + esc(STATUS[d.status] || d.status) + '</span></div>'
      : '<a class="shot" href="' + esc(wb) + '">' + img + '<span class="status s-' + esc(d.status) + '">' + esc(STATUS[d.status] || d.status) + '</span></a>';
    return '<li class="card' + (flags.length ? ' flagged' : '') + '">' + shot +
      '<div class="body"><h2><a href="' + esc(wb) + '">' + esc(title) + '</a></h2>' +
      '<p class="addr">' + esc(host) + '</p>' +
      (d.desc ? '<p class="desc">' + esc(d.desc) + '</p>' : '') +
      '<p class="chips">' + chips.join('') + '</p>' +
      '<p class="meta">Found ' + esc(fmtDate(d.seen)) + ' on ' + where + '</p>' +
      '<p class="links"><a href="' + esc(wb) + '">' + (d.wayback ? 'Wayback copy, ' + esc(tsDate(d.wayback)) : 'All Wayback captures') + '</a>' + live + '</p>' +
      '</div></li>';
  }

  function days(o, list) {
    const c = new Map();
    filter(o, 'day').forEach((d) => { const k = day(d.seen); c.set(k, (c.get(k) || 0) + 1); });
    const keys = [...c.keys()].sort().slice(-45);
    const max = Math.max(1, ...keys.map((k) => c.get(k)));
    $('days').innerHTML = keys.length < 2 ? '' : '<span class="lbl">Found per day</span><div class="bars">' + keys.map((k) => {
      const on = o.day === k, n = c.get(k);
      return '<a class="bar' + (on ? ' on' : '') + '" href="' + esc(href(Object.assign({}, o, { day: on ? '' : k, page: '' }))) +
        '" title="' + esc(k + ': ' + n.toLocaleString() + ' sites') + '" aria-label="' + esc(k + ', ' + n + ' sites') + '"' + (on ? ' aria-current="true"' : '') +
        '><span style="height:' + Math.max(4, Math.round(60 * n / max)) + 'px"></span></a>';
    }).join('') + '</div>';
  }

  function render() {
    const o = params();
    if (o.flagged && !FLAGGED) {
      grid.innerHTML = ''; $('count').textContent = 'Loading flagged sites…';
      fetch('data/flagged.json', { cache: 'no-cache' }).then((r) => r.json()).then((j) => { FLAGGED = rowsToObjects(j); render(); })
        .catch(() => { FLAGGED = []; render(); });
      return;
    }
    KEYS.forEach((k) => {
      const el = form.elements[k];
      if (!el) return;
      if (el.type === 'checkbox') el.checked = !!o[k]; else if (el.tagName !== 'SELECT') el.value = o[k] || '';
    });
    form.elements.sort.value = o.sort || 'new';
    form.elements.since.value = o.since || '';
    form.elements.status.value = o.status || '';
    form.elements.saved.value = o.saved || '';
    form.elements.flagged.value = o.flagged || '';
    $('flagnote').hidden = !o.flagged;
    fillSelect('source', o, (d) => d.sources, (v) => SOURCES[v] || v);
    fillSelect('platform', o, (d) => [d.platform], platName);
    fillSelect('tech', o, (d) => d.tech, (v) => v);
    fillSelect('topic', o, (d) => d.topics.length ? d.topics : ['_none'], (v) => v,
      (c) => c.get('_none') ? '<option value="_none">No topic found (' + c.get('_none').toLocaleString() + ')</option>' : '');
    fillSelect('lang', o, (d) => [d.lang || '_none'], langName,
      (c) => c.get('_none') ? '<option value="_none">Not stated (' + c.get('_none').toLocaleString() + ')</option>' : '');
    const list = filter(o);
    const sort = o.sort || 'new';
    list.sort((a, b) => sort === 'old' ? a.seen - b.seen : sort === 'mentions' ? b.mentions - a.mentions || b.seen - a.seen
      : sort === 'points' ? (b.points || 0) - (a.points || 0) || b.seen - a.seen : b.seen - a.seen);
    const page = Math.max(1, parseInt(o.page || '1', 10));
    const shown = list.slice(0, page * PER_PAGE);
    grid.innerHTML = shown.map(card).join('');
    $('count').textContent = list.length.toLocaleString() + (list.length === 1 ? ' site' : ' sites') +
      (shown.length < list.length ? ', showing the first ' + shown.length.toLocaleString() : '');
    $('more').innerHTML = shown.length < list.length ? '<a class="btn" href="' + esc(href(Object.assign({}, o, { page: String(page + 1) }))) + '">Show more</a>' : '';
    days(o, list);
    const active = KEYS.filter((k) => o[k] && !['page', 'sort'].includes(k));
    $('active').innerHTML = active.length ? '<a href="./">Clear all filters</a>' : '';
    document.title = (o.q || o.topic || o.tech || o.platform ? [o.q, o.topic, o.tech, o.platform && platName(o.platform)].filter(Boolean).join(', ') + ' · ' : '') + 'New Web Explorer';
  }

  function go(o, push) {
    const h = href(o);
    history[push ? 'pushState' : 'replaceState'](null, '', h === './' ? location.pathname : h);
    render();
  }

  form.addEventListener('change', (e) => {
    const o = params();
    const el = e.target;
    o[el.name] = el.type === 'checkbox' ? (el.checked ? '1' : '') : el.value;
    o.page = '';
    go(o, true);
  });
  let t;
  form.elements.q.addEventListener('input', (e) => {
    clearTimeout(t);
    t = setTimeout(() => { const o = params(); o.q = e.target.value; o.page = ''; go(o, false); }, 250);
  });
  document.addEventListener('click', (e) => {
    const b = e.target.closest('button.unveil');
    if (b) { b.parentNode.classList.remove('veiled'); b.remove(); return; }
    const a = e.target.closest('a');
    if (!a || a.target || e.metaKey || e.ctrlKey || e.shiftKey) return;
    const url = new URL(a.href, location.href);
    if (url.origin === location.origin && url.pathname === location.pathname) {
      e.preventDefault();
      history.pushState(null, '', url.search || location.pathname);
      render();
      if (url.searchParams.get('page')) return;
      $('results').scrollIntoView({ block: 'start' });
    }
  });
  window.addEventListener('popstate', render);

  fetch('data/sites.json', { cache: 'no-cache' }).then((r) => r.json()).then((j) => {
    ALL = rowsToObjects(j);
    SOURCES = j.stats.sources;
    STATS = j.stats;
    (j.tech_groups || []).forEach(([t, g]) => { TECH_GROUP[t] = g; });
    // "Updated as of" in the header, in the viewer's time zone. The list is rewritten every 15 minutes,
    // so anything older than an hour means the jobs have stopped (a studio restart, for instance).
    const upd = new Date(STATS.updated * 1000);
    const stale = Date.now() - upd.getTime() > 3600 * 1000;
    $('updated').textContent = 'Updated as of ' + upd.toLocaleString('en', { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' }) +
      (stale ? ' (updates paused)' : '');
    $('updated').classList.toggle('stale', stale);
    $('stats').innerHTML = '<b>' + STATS.found.toLocaleString() + '</b> sites found since ' + esc(fmtDate(STATS.since)) +
      ' · <b>' + STATS.shown.toLocaleString() + '</b> pictured and shown here · <b>' + STATS.saved.toLocaleString() +
      '</b> saved to the Wayback Machine by this project' +
      (STATS.held_back ? ' · <a href="?flagged=all">' + STATS.held_back.toLocaleString() + ' flagged</a> and left out' : '');
    render();
  }).catch(() => { $('stats').textContent = 'The list could not be loaded. Please try again later.'; });
})();
