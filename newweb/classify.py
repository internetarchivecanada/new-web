"""Works out what a site was built with, what it is about, and whether to keep it off the public explorer.

Everything here is rules on the rendered page (HTML, a few JavaScript globals, the title and visible text),
so each label can be explained. Topics are keyword rules, not a trained model: good enough to browse by,
wrong on some sites.
"""
import re

# ---------- technology ----------
# (tag, group, test on the HTML text). Groups: "AI builder", "Site builder", "Framework", "Generator", "Library".
HTML_RULES = [
    ('Lovable', 'AI builder', r'lovable\.(dev|app)|gptengineer|lovable-tagger|Edit with Lovable'),
    ('Bolt', 'AI builder', r'bolt\.new|Made (with|in) Bolt|stackblitz\.com/edit'),
    ('v0', 'AI builder', r'v0\.dev|v0\.app|vusercontent\.net|generator" content="v0'),
    ('Replit', 'AI builder', r'replit\.(com|app|dev)/|Made with Replit|replit-badge'),
    ('Base44', 'AI builder', r'base44'),
    ('Claude', 'AI builder', r'claude\.(ai|site)/(public/)?artifacts|Made with Claude|claude-artifact'),
    ('ChatGPT', 'AI builder', r'chatgpt\.com/canvas|Made with ChatGPT'),
    ('Manus', 'AI builder', r'manus\.(im|space)'),
    ('Same', 'AI builder', r'same\.new|same-runtime'),
    ('Windsurf', 'AI builder', r'windsurf\.build'),
    ('Create', 'AI builder', r'create\.xyz|created\.app'),
    ('DeepSite', 'AI builder', r'enzostvs-deepsite|deepsite\.hf\.co|Made with DeepSite'),
    ('Websim', 'AI builder', r'websim\.(ai|com)/'),
    ('Google AI Studio', 'AI builder', r'aistudio\.google\.com|ai\.studio/apps|Built with Google AI Studio'),
    ('Rocket', 'AI builder', r'rocket\.new|Built with Rocket'),
    ('Firebase Studio', 'AI builder', r'studio\.firebase\.google\.com|Firebase Studio'),
    ('Framer', 'Site builder', r'framerusercontent\.com|generator" content="Framer'),
    ('Webflow', 'Site builder', r'data-wf-site|webflow\.(js|com)'),
    ('Wix', 'Site builder', r'generator" content="Wix|wixstatic\.com'),
    ('Squarespace', 'Site builder', r'squarespace\.com|static1\.squarespace'),
    ('Carrd', 'Site builder', r'carrd\.co'),
    ('Notion', 'Site builder', r'notion\.site|notion-static'),
    ('Google Sites', 'Site builder', r'sites\.google\.com'),
    ('WordPress', 'Generator', r'wp-content/|generator" content="WordPress'),
    ('Jekyll', 'Generator', r'generator" content="Jekyll|jekyll-theme|Begin Jekyll SEO tag'),
    ('Hugo', 'Generator', r'generator" content="Hugo'),
    ('Hexo', 'Generator', r'generator" content="Hexo'),
    ('Eleventy', 'Generator', r'generator" content="Eleventy'),
    ('Docusaurus', 'Generator', r'generator" content="Docusaurus|docusaurus'),
    ('MkDocs', 'Generator', r'generator" content="mkdocs|mkdocs-material'),
    ('Sphinx', 'Generator', r'_static/sphinx|generator" content="Sphinx|readthedocs'),
    ('Quarto', 'Generator', r'generator" content="quarto'),
    ('VitePress', 'Generator', r'generator" content="VitePress|vitepress'),
    ('Astro', 'Framework', r'generator" content="Astro|astro-island|/_astro/'),
    ('Next.js', 'Framework', r'/_next/static|__NEXT_DATA__|self\.__next_f'),
    ('Nuxt', 'Framework', r'/_nuxt/|__NUXT__'),
    ('Gatsby', 'Framework', r'id="___gatsby"'),
    ('SvelteKit', 'Framework', r'__sveltekit|data-sveltekit'),
    ('Remix', 'Framework', r'__remixContext|__remixManifest'),
    ('Angular', 'Framework', r'ng-version='),
    ('Vite', 'Framework', r'<script type="module"[^>]+src="[^"]*/assets/index-[\w-]+\.js'),
    ('Streamlit', 'Framework', r'data-testid="stApp|streamlit-container|static/js/main\.[0-9a-f]+\.js"[^>]*streamlit'),
    ('Gradio', 'Framework', r'gradio_config|gradio-app'),
    ('Flutter', 'Framework', r'flutter\.js|flutter_bootstrap'),
    ('Tailwind', 'Library', r'--tw-[a-z]|cdn\.tailwindcss\.com'),
    ('Bootstrap', 'Library', r'bootstrap(\.min)?\.(css|js)'),
    ('shadcn/ui', 'Library', r'data-radix-|data-slot="'),
    ('Three.js', 'Library', r'three(\.module)?(\.min)?\.js'),
    ('D3', 'Library', r'd3(\.v\d)?(\.min)?\.js|d3js\.org'),
    ('Leaflet', 'Library', r'leaflet(\.min)?\.(js|css)'),
    ('MapLibre / Mapbox', 'Library', r'maplibre-gl|mapbox-gl'),
    ('Chart.js', 'Library', r'chart(\.umd)?(\.min)?\.js|chartjs'),
    ('Plotly', 'Library', r'plotly(-[\d.]+)?(\.min)?\.js'),
    ('Pyodide', 'Library', r'pyodide'),
    ('jQuery', 'Library', r'jquery(-[\d.]+)?(\.min)?\.js'),
]
HTML_RULES = [(t, g, re.compile(rx, re.I)) for t, g, rx in HTML_RULES]

# JavaScript run in the page after it renders; returns which globals/markers exist.
PROBE_JS = r'''() => {
  const w = window, d = document, out = [];
  const has = (k) => { try { return typeof w[k] !== 'undefined'; } catch (e) { return false; } };
  if (has('__NEXT_DATA__') || has('next')) out.push('Next.js');
  if (has('__NUXT__')) out.push('Nuxt');
  if (has('__VUE__') || d.querySelector('[data-v-app]')) out.push('Vue');
  if (has('__svelte') || d.querySelector('[class*="svelte-"]')) out.push('Svelte');
  if (has('React') || [...d.querySelectorAll('body *')].slice(0, 300).some(e => Object.keys(e).some(k => k.startsWith('__react')))) out.push('React');
  if (has('ng') || d.querySelector('[ng-version]')) out.push('Angular');
  if (has('jQuery')) out.push('jQuery');
  if (has('THREE')) out.push('Three.js');
  if (has('d3')) out.push('D3');
  if (has('L') && w.L && w.L.map) out.push('Leaflet');
  if (has('maplibregl') || has('mapboxgl')) out.push('MapLibre / Mapbox');
  if (has('Chart')) out.push('Chart.js');
  if (has('Plotly')) out.push('Plotly');
  if (has('pyodide') || has('loadPyodide')) out.push('Pyodide');
  if (has('gradio_config')) out.push('Gradio');
  try { if (getComputedStyle(d.documentElement).getPropertyValue('--tw-border-spacing-x') !== '' ||
            getComputedStyle(d.body).getPropertyValue('--tw-ring-offset-width') !== '') out.push('Tailwind'); } catch (e) {}
  if (d.querySelector('canvas')) out.push('_canvas');
  if (d.querySelector('[data-radix-popper-content-wrapper],[data-radix-collection-item],[data-slot]')) out.push('shadcn/ui');
  return out;
}'''

GROUP = {t: g for t, g, _ in HTML_RULES}
GROUP.update({'React': 'Framework', 'Vue': 'Framework', 'Svelte': 'Framework'})
# Coding agents, known from the source (an agent-signed commit, a tool's gallery) rather than from the page.
GROUP.update({t: 'AI builder' for t in ('Claude Code', 'Cursor', 'GitHub Copilot', 'OpenAI Codex')})

# Default titles of starter templates: the site was published before anything was put in it.
STARTER = re.compile(r'^(Vite \+ (React|Vue|TS|Svelte|Preact|Lit)( \+ TS)?|React App|Create Next App|Vite App|'
                     r'Welcome to (nginx|Next\.js|Astro|your Vue\.js App)|Svelte ?Kit|SvelteKit app|Nuxt|Astro( Basics)?|'
                     r'Document|Untitled|Home|My (Website|Site|App|Portfolio)|lovable[- ]?(app|project)?|'
                     r'.*generated by create .*|Expo|Hello,? World!?)$', re.I)


def technology(html, probes):
    tags = {t for t, g, rx in HTML_RULES if rx.search(html)}
    tags |= {p for p in probes if not p.startswith('_')}
    # Next.js/Nuxt/Gatsby/Remix are React/Vue underneath; keep the more specific tag only.
    if tags & {'Next.js', 'Gatsby', 'Remix'}:
        tags.discard('React')
    if 'Nuxt' in tags:
        tags.discard('Vue')
    if 'SvelteKit' in tags:
        tags.discard('Svelte')
    return sorted(tags)


# ---------- topics ----------
TOPICS = [
    ('AI & agents', r'\b(ai|a\.i\.|llm|llms|gpt|chatgpt|claude|gemini|openai|anthropic|agent|agents|agentic|prompt|prompts|rag|embedding|'
                    r'machine learning|neural|transformer|diffusion|copilot|chatbot|mcp)\b'),
    ('Developer tools', r'\b(api|cli|sdk|developer|developers|devtools|github|open[- ]source|library|npm|pypi|framework|debug|'
                        r'deploy|kubernetes|docker|database|sql|typescript|javascript|python|rust|golang|compiler|linter|code review|terminal)\b'),
    ('Games & play', r'\b(game|games|gaming|play now|puzzle|wordle|chess|arcade|quiz|trivia|multiplayer|leaderboard|level \d+|minecraft|roguelike|sudoku)\b'),
    ('Data & maps', r'\b(dashboard|visuali[sz]ation|data ?viz|dataset|datasets|charts?|map|maps|mapping|gis|census|statistics|tracker|explorer|open data)\b'),
    ('Science & research', r'\b(research|paper|papers|thesis|dissertation|lab|laboratory|physics|chemistry|biology|genomics|neuroscience|'
                           r'astronomy|climate|ecology|mathematics|phd|professor|university|journal|preprint|arxiv)\b'),
    ('Education', r'\b(learn|learning|course|courses|tutorial|tutorials|lesson|lessons|students?|teachers?|teaching|classroom|school|'
                  r'flashcards?|study|exam|homework|curriculum)\b'),
    ('Personal & portfolio', r'\b(portfolio|about me|my name is|i\'m a|i am a|resume|résumé|cv|personal (site|website|page)|'
                             r'hi,? i\'m|my projects|my work)\b'),
    ('Writing & blogs', r'\b(blog|posts|essays?|newsletter|writing|notes|journal entries|substack|articles?|poetry|poems|fiction|stories)\b'),
    ('Business & startups', r'\b(startup|saas|pricing|customers|book a demo|get started|sign up|waitlist|enterprise|b2b|crm|marketing|'
                            r'sales|invoice|agency|consulting|landing page)\b'),
    ('Money & crypto', r'\b(finance|financial|invest|investing|stocks?|trading|budget|crypto|bitcoin|ethereum|solana|defi|nft|token|'
                       r'web3|blockchain|tax|taxes|mortgage|loan)\b'),
    ('Health & fitness', r'\b(health|medical|medicine|fitness|workout|nutrition|diet|mental health|therapy|sleep|meditation|patients?|clinic|wellness)\b'),
    ('Music & audio', r'\b(music|song|songs|audio|podcast|synth|synthesizer|beats?|playlist|spotify|album|guitar|piano|dj|sound)\b'),
    ('Art & design', r'\b(art|artist|artwork|design|designer|illustration|photography|photos?|gallery|generative art|creative coding|'
                     r'typography|fonts?|3d|animation|drawing|pixel)\b'),
    ('News & politics', r'\b(news|politics|political|election|elections|government|policy|congress|senate|democracy|vote|voting|journalism|'
                        r'war|ukraine|gaza|trump)\b'),
    ('Productivity', r'\b(productivity|todo|to-do|tasks?|calendar|notes app|habit|timer|pomodoro|kanban|planner|organi[sz]e|workflow|automation)\b'),
    ('Community & social', r'\b(community|forum|social|friends|chat|discord|meetup|events?|club|members|volunteer|nonprofit|church)\b'),
    ('Shopping', r'\b(shop|store|buy now|add to cart|cart|checkout|products?|sale|discount|e-?commerce|price|deals?)\b'),
    ('Travel & places', r'\b(travel|trip|trips|hotel|flights?|itinerary|city guide|restaurants?|food|recipes?|cooking|hiking|tourism)\b'),
    ('Documentation', r'\b(documentation|docs|getting started|installation|reference|changelog|readme|user guide|api reference)\b'),
]
TOPICS = [(t, re.compile(rx, re.I)) for t, rx in TOPICS]


def topics(title, description, text):
    """Up to three topics. Title and description count three times as much as body text."""
    head = f'{title or ""} {description or ""}'
    body = (text or '')[:6000]
    scores = []
    for name, rx in TOPICS:
        s = 3 * len(rx.findall(head)) + min(len(rx.findall(body)), 8)
        if s >= 3:
            scores.append((s, name))
    scores.sort(reverse=True)
    return [n for _, n in scores[:3]]


# ---------- what not to show ----------
FLAGS = [
    ('adult', re.compile(r'\b(porn|xxx|nsfw|onlyfans|escort|escorts|nude|nudes|sex ?cam|hentai|camgirls?|18\+ only)\b', re.I)),
    ('phishing', re.compile(r'\b(seed phrase|recovery phrase|connect (your )?wallet|claim (your )?(airdrop|tokens?|reward)|wallet ?connect|'
                            r'verify your (account|identity|wallet)|validate your wallet|metamask|trust wallet|'
                            r'(sign|log) ?in to (your )?(paypal|apple|microsoft|office|outlook|netflix|amazon|bank|coinbase|binance)|'
                            r'account (has been )?(suspended|locked)|unusual (sign-in|activity))\b', re.I)),
    ('gambling', re.compile(r'\b(casino|online slots?|slot (gacor|online|demo|machines?)|demo slot|gacor|judi|togel|betting|'
                            r'sportsbook|poker|jackpot|bet now|free spins)\b', re.I)),
    ('scam', re.compile(r'\b(guaranteed (profit|returns)|double your (bitcoin|money|crypto)|investment plan|forex signals?|'
                        r'cheap (viagra|cialis)|buy followers)\b', re.I)),
]

ADULT_CJK = re.compile(r'FANZA|DMM\.R18|アダルト|エロ|無修正|AV女優|成人向け|18禁|色情|成人影片|成人视频|成人視頻|av女优|야동|성인용', re.I)


def flags(title, description, text, html):
    head = f'{title or ""} {description or ""} {(text or "")[:6000]}'
    out = []
    for name, rx in FLAGS:
        n = len(rx.findall(head))
        if n >= (1 if name in ('adult', 'phishing') else 2):
            out.append(name)
    # Adult pages in languages \b cannot split (Japanese, Chinese, Korean), and the self-applied adult labels.
    if (ADULT_CJK.search(head) or re.search(r'RTA-5042-1996-1400-1577-RTA|<meta[^>]+name=["\']?rating["\']?[^>]+content=["\']?'
                                            r'(adult|mature|RTA)', html, re.I)):
        out.append('adult')
    # A page whose only form asks for a password on a platform subdomain is a classic phishing kit.
    if re.search(r'type=["\']?password', html, re.I) and re.search(r'\b(paypal|apple id|microsoft|office ?365|outlook|netflix|'
                                                                 r'wells fargo|chase|bank of america|coinbase|binance|metamask)\b', head, re.I):
        out.append('phishing')
    return sorted(set(out))


def starter(title, text):
    return bool(title and STARTER.match(title.strip())) and len((text or '').strip()) < 400
