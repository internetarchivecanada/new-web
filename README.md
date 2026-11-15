# New web discovery pilot

Finds newly published small sites, explorers and web apps, and measures how fast they disappear. This is step 2 of
"Archiving the New Web of Apps" (13 November 2026): a one-month discovery test, then 30/60/90-day survival.

## Sources (each a long-running job on the studio)
| Job | Source | Keeps |
|---|---|---|
| `hn` | Hacker News (Algolia API, every 10 min, 7-day backfill on first start) | every "Show HN" link except big sites (github.com, YouTube…); other stories only when they link to a hosting platform |
| `bluesky` | Bluesky Jetstream firehose (all new posts) | links to sites on hosting platforms. Stores only the link, the post's at:// address and the time: no author or text |
| `gharchive` | GH Archive hourly GitHub event files (24-hour backfill) | pushes to `<user>.github.io` repositories; hosting-platform links in new repositories' descriptions and release notes |
| `spn` | Save Page Now | saves each new site's shared URL, newest first, 6 at a time with the account in ia.ini. If the account is refused (HTTP 401, as from 2026-11-14) it falls back to anonymous saves, one every 20 s, and re-checks the account hourly |
| `listing` | — | writes the running list every 15 min: `list/index.html` (filterable) and `list/sites.tsv` next to the database |
| `shots` | — | about an hour after a site is found and answers: a screenshot (480 px WEBP), its title, description, language, what it was built with and its topics (`classify.py`); flags adult, phishing, gambling and scam pages so the explorer leaves them out |
| `liveness` | — | checks the shared URL ~1 h, then 1, 7, 30, 60 and 90 days after first sighting; detects platforms' "nothing deployed here" pages |

"Hosting platform" = the suffix list in `newweb/common.py` (vercel.app, netlify.app, pages.dev, github.io, fly.dev,
onrender.com, replit.app, lovable.app, hf.space, streamlit.app and ~40 more).

Not yet: Certificate Transparency (CT) logs. `newweb/certstream.py` is written, but the public certstream feed
(certstream.calidog.io) accepts connections and sends nothing; CT needs its own log reader. Reddit and Product Hunt need
API keys.

## The explorer (studio tile `new-web`)
https://wayback-labs.sf.archive.org/new-web/ is a static tile: Caddy serves `public/` from `/opt/services/new-web`, a
checkout of this repo (DEPLOY.md in internetarchivecanada/waybacklabs). `public/index.html`, `app.js`, `style.css` and
`about.html` are tracked; `public/data/sites.json`, `public/thumbs/` and `public/sitemap.xml` are written there by the
`listing` and `shots` jobs and are never committed. Filters live in the query string (`?topic=…&tech=…&day=…`), so every
view has its own address.

## Data
SQLite at `/Volumes/4tb-ext/data/newweb/newweb.sqlite` on the studio: `sites` (one row per site, first seen, platform,
sources, next check), `mentions` (every sighting), `checks` (every liveness check), `heartbeat` (per collector).

## Running
Repository: https://github.com/internetarchivecanada/new-web (private). The studio copy is not a git clone:
`deploy` copies this checkout to `~/newweb` on the studio with rsync (leaving its `venv/` and `logs/` alone).
```
tools/studio.sh deploy    # rsync code, make venv
tools/studio.sh start     # screen sessions nw-hn, nw-bluesky, nw-gharchive, nw-liveness, nw-spn, nw-listing
tools/studio.sh status
tools/studio.sh list      # copy the list of found sites to the laptop
tools/studio.sh report
tools/studio.sh stop
```
Screen sessions do not survive a studio reboot: run `start` again after one.

`tools/studio.sh list` copies the list to the laptop.
