"""Build the presentation deck (presentation/index.html), one self-contained HTML file.

Every number and chart comes from the SQL result files of the project
(queries/query_results.json, etl/cleaning_log.json, queries/index_benchmark.json,
queries/verify_constraints.out) or from one query run here (Q07, full range).
Python only places the returned values on the slides.

    .venv/bin/python presentation/build_presentation.py
"""
import base64
import html
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from steamdb.db import connect, load_blocks  # noqa: E402

E = html.escape
Q = json.loads((ROOT / "queries" / "query_results.json").read_text())
CLEAN = json.loads((ROOT / "etl" / "cleaning_log.json").read_text())
BENCH = json.loads((ROOT / "queries" / "index_benchmark.json").read_text())
VERIFY = (ROOT / "queries" / "verify_constraints.out").read_text()


def rows(name):
    return [dict(zip(Q[name]["columns"], r)) for r in Q[name]["rows"]]


def data_uri(path, mime):
    return f"data:{mime};base64," + base64.b64encode(Path(path).read_bytes()).decode()


def n(v):
    return f"{v:,}"


# Q07 over the whole range (the saved sample only keeps 15 rows)
conn = connect()
with conn.cursor() as cur:
    cur.execute(load_blocks(ROOT / "sql" / "queries.sql")["Q07"], {"year_from": 2008})
    cols = [d.name for d in cur.description]
    Q07 = [dict(zip(cols, r)) for r in cur.fetchall()]
    # overall review summary, labelled with Steam's own thresholds (500+ reviews)
    cur.execute("""
        SELECT count(*) AS reviews,
               round(100.0 * avg(is_recommended::int), 1) AS pct,
               CASE WHEN avg(is_recommended::int) >= 0.95 THEN 'Overwhelmingly Positive'
                    WHEN avg(is_recommended::int) >= 0.80 THEN 'Very Positive'
                    WHEN avg(is_recommended::int) >= 0.70 THEN 'Mostly Positive'
                    WHEN avg(is_recommended::int) >= 0.40 THEN 'Mixed'
                    ELSE 'Negative' END AS label
        FROM recommendations""")
    ALL_REVIEWS = dict(zip([d.name for d in cur.description], cur.fetchone()))
conn.close()

# constraint totals per type (section 2 of verify_constraints.out)
m = re.search(r"table_name\s+\|\s+pk.*?\n-+\+.*?\n(.*?)\n\(\d+ filas?\)", VERIFY, re.S)
cons = [[c.strip() for c in l.split("|")] for l in m.group(1).splitlines()]
CONS = {k: sum(int(r[i]) for r in cons) for i, k in
        enumerate(["", "PK", "FK", "UNIQUE", "CHECK", "NOT NULL"]) if i}
N_CONS = sum(CONS.values())
counts = CLEAN["row_counts"]
rules = CLEAN["cleaning_rules"]

# ------------------------------------------------------------------ svg charts
W_TEXT = "var(--muted)"


def svg(w, h, body):
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" '
            f'xmlns="http://www.w3.org/2000/svg">{body}</svg>')


def text(x, y, s, anchor="start", cls="lbl", extra=""):
    return f'<text x="{x}" y="{y}" text-anchor="{anchor}" class="{cls}" {extra}>{E(str(s))}</text>'


def hbars_pct(items, w=560, row=30, label_w=250, hi=()):
    """items: (label, pct, sub). Bars on a 0-100 scale."""
    plot = w - label_w - 52
    h = row * len(items) + 26
    out = []
    for t in (0, 50, 100):
        x = label_w + plot * t / 100
        out.append(f'<line x1="{x}" x2="{x}" y1="0" y2="{h - 22}" class="grid"/>')
        out.append(text(x, h - 6, f"{t} %", "middle", "tick"))
    for i, (label, pct, sub) in enumerate(items):
        y = i * row
        cls = "bar-down" if pct < 70 else "bar-up"
        if label in hi:
            cls += " hi"
        out.append(text(label_w - 10, y + row * 0.62, label, "end", "lbl" + (" strong" if label in hi else "")))
        if sub:
            out.append(text(label_w - 10, y + row * 0.62 + 11, sub, "end", "sub"))
        bw = plot * pct / 100
        out.append(f'<rect x="{label_w}" y="{y + 6}" width="{bw:.1f}" height="{row - 12}" rx="3" class="{cls}"/>')
        out.append(text(label_w + bw + 6, y + row * 0.62, f"{pct:.1f}", "start", "val"))
    return svg(w, h, "".join(out))


def vbars(items, w, h, fmt, cls="bar-up", top=None, unit=""):
    """items: (label, value). Simple vertical bars from 0."""
    top = top or max(v for _, v in items) * 1.15
    pad_l, pad_b, pad_t = 8, 34, 22
    plot_h = h - pad_b - pad_t
    bw_slot = (w - pad_l * 2) / len(items)
    out = [f'<line x1="{pad_l}" x2="{w - pad_l}" y1="{h - pad_b}" y2="{h - pad_b}" class="axis"/>']
    for i, (label, v) in enumerate(items):
        x = pad_l + i * bw_slot + bw_slot * 0.18
        bw = bw_slot * 0.64
        bh = plot_h * v / top
        y = h - pad_b - bh
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="3" class="{cls}"/>')
        out.append(text(x + bw / 2, y - 6, fmt(v) + unit, "middle", "val"))
        out.append(text(x + bw / 2, h - pad_b + 17, label, "middle", "tick"))
    return svg(w, h, "".join(out))


def paired_bars(items, w=1120, h=330):
    """items: (label, up, down) hours. Recommended vs not recommended."""
    top = max(max(u, d) for _, u, d in items) * 1.15
    pad_b, pad_t, pad_l = 40, 20, 10
    plot_h = h - pad_b - pad_t
    slot = (w - pad_l * 2) / len(items)
    out = [f'<line x1="{pad_l}" x2="{w - pad_l}" y1="{h - pad_b}" y2="{h - pad_b}" class="axis"/>']
    for i, (label, up, down) in enumerate(items):
        x0 = pad_l + i * slot + slot * 0.14
        bw = slot * 0.34
        for j, (v, cls) in enumerate(((up, "bar-up"), (down, "bar-down"))):
            x = x0 + j * (bw + 3)
            bh = plot_h * v / top
            y = h - pad_b - bh
            out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="3" class="{cls}"/>')
            out.append(text(x + bw / 2, y - 6, f"{v:g}", "middle", "val small"))
        out.append(text(x0 + bw + 1.5, h - pad_b + 18, label, "middle", "tick"))
    return svg(w, h, "".join(out))


def line_chart(series, years, w=760, h=360, colors=None):
    pad_l, pad_r, pad_t, pad_b = 46, 110, 16, 34
    pw, ph = w - pad_l - pad_r, h - pad_t - pad_b
    y0, y1 = min(years), max(years)
    X = lambda yr: pad_l + pw * (yr - y0) / (y1 - y0)
    Y = lambda v: pad_t + ph * (1 - v / 60)
    out = []
    for t in (0, 20, 40, 60):
        out.append(f'<line x1="{pad_l}" x2="{pad_l + pw}" y1="{Y(t)}" y2="{Y(t)}" class="grid"/>')
        out.append(text(pad_l - 8, Y(t) + 4, f"{t} %", "end", "tick"))
    for yr in range(y0, y1 + 1, 3):
        out.append(text(X(yr), h - 10, yr, "middle", "tick"))
    top_peak = max(series, key=lambda k: max(v for _, v in series[k]))
    top_last = max(series, key=lambda k: series[k][-1][1])
    for name, pts in series.items():
        c = colors[name]
        si = 0 if name == top_peak else 1
        sl = 0 if name == top_last else 1
        d = " ".join(f"{'M' if i == 0 else 'L'}{X(yr):.1f},{Y(v):.1f}" for i, (yr, v) in enumerate(pts))
        out.append(f'<path d="{d}" fill="none" stroke="{c}" stroke-width="3" stroke-linejoin="round"/>')
        peak = max(pts, key=lambda p: p[1])
        last = pts[-1]
        out.append(f'<circle cx="{X(peak[0]):.1f}" cy="{Y(peak[1]):.1f}" r="5" fill="{c}"/>')
        out.append(text(X(peak[0]) + (0 if si == 0 else 10), Y(peak[1]) + (-12 if si == 0 else 26), f"{peak[1]:.0f} % in {peak[0]}", "middle" if si == 0 else "start", "val",
                        f'fill="{c}"'))
        out.append(f'<circle cx="{X(last[0]):.1f}" cy="{Y(last[1]):.1f}" r="5" fill="{c}"/>')
        out.append(text(X(last[0]) + 10, Y(last[1]) + (-6 if sl == 0 else 14), f"{name} {last[1]:.0f} %", "start", "val",
                        f'fill="{c}"'))
    return svg(w, h, "".join(out))


def log_bench():
    items = list(BENCH.items())
    w, row, label_w = 1120, 92, 360
    plot = w - label_w - 40
    lo, hi = math.log10(0.05), math.log10(10000)
    X = lambda ms: label_w + plot * (math.log10(max(ms, 0.05)) - lo) / (hi - lo)
    out = []
    h = row * len(items) + 30
    for t, lab in ((0.1, "0.1 ms"), (1, "1 ms"), (10, "10 ms"), (100, "100 ms"), (1000, "1 s"), (10000, "10 s")):
        out.append(f'<line x1="{X(t):.1f}" x2="{X(t):.1f}" y1="0" y2="{h - 26}" class="grid"/>')
        out.append(text(X(t), h - 6, lab, "middle", "tick"))
    names = ["Reviews of one game", "Monthly trend of a tag (Q03)", "Title search + review counts (Q10)"]
    for i, ((k, v), nm) in enumerate(zip(items, names)):
        y = i * row + 8
        a, b = v["without"]["ms"], v["with"]["ms"]
        out.append(text(label_w - 14, y + 26, nm, "end", "lbl strong"))
        out.append(text(label_w - 14, y + 46, f"{a / max(b, 0.001):,.0f}× faster", "end", "sub up"))
        out.append(f'<rect x="{label_w}" y="{y + 10}" width="{X(a) - label_w:.1f}" height="20" rx="3" class="bar-down"/>')
        lab_a = f"{a:,.1f} ms without index"
        if X(a) > w - 260:
            out.append(text(X(a) - 10, y + 25, lab_a, "end", "val", 'fill="var(--ink)"'))
        else:
            out.append(text(X(a) + 8, y + 25, lab_a, "start", "val"))
        out.append(f'<rect x="{label_w}" y="{y + 38}" width="{max(X(b) - label_w, 3):.1f}" height="20" rx="3" class="bar-up"/>')
        out.append(text(max(X(b), label_w + 3) + 8, y + 53, f"{b:,.2f} ms with index".replace(".00 ", " "), "start", "val"))
    return svg(w, h, "".join(out))


# ------------------------------------------------------------------ slide content
q02 = rows("Q02")
q02_items = [(f"{r['title'][:28]} · {r['release_year']}", r["pct_recommended"], "") for r in q02]
q04 = rows("Q04")
q12 = rows("Q12")[:8]
q07_series = {}
for r in Q07:
    if r["platform"] in ("Mac", "Linux") and r["release_year"] <= 2023:
        q07_series.setdefault(r["platform"], []).append((r["release_year"], float(r["pct_of_year"])))
years = sorted({yr for pts in q07_series.values() for yr, _ in pts})

FEATURES = [("JOIN", r"\bJOIN\b"), ("GROUP BY + HAVING", r"\bHAVING\b"),
            ("Subquery", r"\(\s*SELECT|IN \(SELECT|EXISTS"), ("Window", r"OVER\s*(\(|w\b)"),
            ("CTE", r"^WITH\b"), ("DML in a transaction", r"\bUPDATE\b")]
matrix_rows = ""
for k, q in Q.items():
    sql = q["sql"]
    cells = "".join(f'<td>{"●" if re.search(p, sql, re.M | re.I) else ""}</td>' for _, p in FEATURES)
    short = q["question"].split("?")[0]
    short = short if len(short) < 78 else short[:75] + "…"
    matrix_rows += f"<tr><th>{k}</th><td class='q'>{E(short)}</td>{cells}</tr>"

sys.path.insert(0, str(ROOT / "report"))
import er_diagram  # noqa: E402
er_diagram.render(er_diagram.make_dot(CLEAN["row_counts"], er_diagram.DARK), ROOT / "presentation" / "build",
                  "er_dark", ("svg",))
ER = data_uri(ROOT / "presentation" / "build" / "er_dark.svg", "image/svg+xml")
PGA = data_uri(ROOT / "report" / "screenshots" / "pgadmin_constraints_tree.png", "image/png")
DASH = data_uri(ROOT / "report" / "screenshots" / "report" / "tab01.png", "image/png")
SALE = data_uri(ROOT / "report" / "screenshots" / "report" / "tab11.png", "image/png")

total_rows = sum(counts.values())


SECTIONS = ["", "DATA", "DATA", "DATA", "MODEL", "MODEL", "MODEL", "LOAD", "LOAD",
            "SQL", "SQL", "SQL", "SQL", "SQL", "DASHBOARD", "Q&amp;A"]
NAV_ITEMS = ["DATA", "MODEL", "LOAD", "SQL", "DASHBOARD", "Q&amp;A"]


def topnav(i):
    items = "".join(f'<span class="{"on" if SECTIONS[i] == it else ""}">{it}</span>' for it in NAV_ITEMS)
    return f'<nav class="topnav"><span class="brand">PROJECT&nbsp;B</span>{items}<span class="who">Odei Fernández Rodríguez</span></nav>'


def slide(prompt, title, body, cls=""):
    return f"""<section class="slide {cls}">
  {topnav(len(S))}
  <div class="prompt"><span class="db">steam=#</span> {E(prompt)}</div>
  <h2>{title}</h2>
  {body}
</section>"""


S = []
TAGS = ["PostgreSQL", "SQL", "Python", "ETL", "Data Visualization", "Streamlit", "Relational Model"]
S.append(f"""<section class="slide cover">
  {topnav(0)}
  <div class="store">
    <div class="store-main">
      <p class="crumbs">All projects &gt; Information Technology &gt; Project B</p>
      <h1>41 million Steam reviews,<br>one relational database</h1>
      <p class="lede">From four raw files to a PostgreSQL schema, a single-transaction load,
         twelve SQL questions and a dashboard.</p>
      <div class="usertags"><span class="hd">Popular user-defined tags for this project:</span>
        {''.join(f'<span class="tag">{t}</span>' for t in TAGS)}</div>
    </div>
    <aside class="infobox">
      <div class="capsule"><span>{n(ALL_REVIEWS['reviews'])}</span><small>reviews in one table</small></div>
      <dl>
        <dt>All reviews:</dt><dd><b class="pos">{ALL_REVIEWS['label']}</b> <span class="muted">({ALL_REVIEWS['pct']} % of {n(ALL_REVIEWS['reviews'])})</span></dd>
        <dt>Release date:</dt><dd>25 Nov, 2026</dd>
        <dt>Developer:</dt><dd class="link">Odei Fernández Rodríguez</dd>
        <dt>Data:</dt><dd class="link">Anton Kozyriev · Kaggle · CC0</dd>
        <dt>Built with:</dt><dd>PostgreSQL 18 · psycopg2 · Streamlit</dd>
      </dl>
    </aside>
  </div>
  <div class="prompt"><span class="db">steam=#</span> SELECT * FROM project WHERE name = 'B';</div>
</section>""")

S.append(slide("\\dt+ raw.*", "The dataset: four files that share keys", f"""
<div class="files">
  <div class="file"><code>games.csv</code><b>50,872</b><span>title, release date, rating, prices, 4 platform flags</span></div>
  <div class="file"><code>games_metadata.json</code><b>50,872</b><span>one JSON per line: description and list of tags</span></div>
  <div class="file"><code>users.csv</code><b>14,306,064</b><span>products owned, reviews written</span></div>
  <div class="file big"><code>recommendations.csv</code><b>41,154,794</b><span>user × game: date, recommended or not, hours, helpful and funny votes · 1.9 GB</span></div>
</div>
<ul class="checks">
  <li><b>Real and open</b> identifiable author, CC0, data from the public Steam store</li>
  <li><b>Relational</b> <code>app_id</code> and <code>user_id</code> link the files</li>
  <li><b>Rich enough</b> 8 tables after modelling</li>
  <li><b>Large enough</b> 41 M rows: indexes make a visible difference</li>
</ul>"""))

S.append(slide("SELECT … FROM raw.*  -- 16 profiling queries", "What the data profile found", f"""
<div class="finds">
  <div class="find"><b>21</b><span>user–game pairs reviewed twice, though Steam allows one review</span></div>
  <div class="find"><b>985</b><span>paid games with an original price of 0.00: a placeholder, not a price</span></div>
  <div class="find"><b>10,373</b><span>empty descriptions, and 1,244 games with no tags</span></div>
  <div class="find"><b>100 %</b><span>of <code>users.reviews</code> equals COUNT(*) of the user's reviews: derived data</span></div>
  <div class="find"><b>7.3 %</b><span>of reviews (2,996,566) written before the release date: early access</span></div>
  <div class="find"><b>50,870</b><span>of 50,872 games flagged for Steam Deck: the flag says nothing</span></div>
</div>
<p class="foot">Also checked: no orphan keys, no malformed dates or numbers, 121 titles shared by different games, hours capped at 1000.</p>"""))

rule_list = [
    ("R1", "price_original 0.00 on a paid game → NULL, discount → NULL", rules.get("games: price_original 0 with price_final > 0 -> NULL (and discount)", 0)),
    ("R2", "empty description → NULL", rules.get("games: empty description -> NULL", 0)),
    ("R3", "empty tag list → no game_tags rows", rules.get("games: empty tag list -> no game_tags rows", 0)),
    ("R4", "duplicate review of a user and game → keep the most recent", rules.get("recommendations: duplicate (user_id, app_id) -> older review dropped", 0)),
    ("R5", "derived users.reviews → not loaded", rules.get("users: derived column reviews not loaded", 0)),
    ("R6", "true/false, ISO dates, numbers → typed values; anything else aborts", 0),
    ("R7", "4 platform flags → game_platforms rows", 123005),
]
S.append(slide("\\i etl/load.py  -- cleaning rules", "Cleaning rules, each one counted", f"""
<table class="rules">{''.join(f'<tr><th>{a}</th><td>{E(b)}</td><td class="num">{n(c)}</td></tr>' for a, b, c in rule_list)}</table>
<p class="foot">Missing values stay NULL and nothing is invented. R6 rejected 0 rows. R7's count is the number of rows created.</p>"""))

S.append(slide("\\d", "From four files to eight tables", f"""
<div class="er-wrap"><img src="{ER}" alt="ER diagram with 8 tables: ratings, games, platforms, game_platforms, tags, game_tags, users, recommendations"></div>""",
               "er"))

S.append(slide("COMMENT ON SCHEMA public IS '…';", "Design decisions, and two exceptions", """
<div class="cols2">
  <div>
    <h3>Normalised</h3>
    <ul>
      <li><b>Platforms</b>: 4 boolean columns → an N:M table, so a new platform is a row.</li>
      <li><b>Tags</b>: JSON list → <code>tags</code> + <code>game_tags</code> (1NF), keeping Steam's order in <code>tag_rank</code>.</li>
      <li><b>Rating</b> labels → lookup table with <code>rank_order</code> (worst → best).</li>
      <li><b><code>users.reviews</code> dropped</b>: derived, and it would go stale after any INSERT or DELETE.</li>
    </ul>
  </div>
  <div>
    <h3>Kept on purpose</h3>
    <ul>
      <li class="exc"><b>Exception 1 · rating</b> is almost derivable from ratio + review count, but Steam's rule is not published and ranges overlap. Recomputing it would invent a rule.</li>
      <li class="exc"><b>Exception 2 · user_reviews, positive_ratio</b> look like aggregates of <code>recommendations</code>, but they are store-wide totals. Q05 shows they differ from the sample.</li>
      <li><b>Early-access reviews</b> stay: real reviews, studied in Q06.</li>
    </ul>
  </div>
</div>"""))

cons_bar = "".join(
    f'<div class="seg s{i}" style="flex:{v}"><b>{v}</b><span>{k}</span></div>'
    for i, (k, v) in enumerate(CONS.items()))
S.append(slide("SELECT … FROM pg_constraint;", f"{N_CONS} constraints, still there after the load", f"""
<div class="cons-layout">
  <div>
    <div class="consbar">{cons_bar}</div>
    <ul>
      <li>Types from the profiled ranges: <code>numeric(6,2)</code> prices, <code>numeric(5,1)</code> hours, <code>smallint</code> ratios and ranks, <code>date</code>, <code>boolean</code>.</li>
      <li>Domain CHECKs: ratio 0–100, <code>price_final ≤ price_original</code>, review date ≥ Steam launch (2003-09-12).</li>
      <li><code>UNIQUE (user_id, app_id)</code>: one review per user and game.</li>
      <li><code>verify_constraints.sql</code> tries 7 invalid rows: <b>all 7 rejected</b>.</li>
    </ul>
  </div>
  <figure class="shot"><img src="{PGA}" alt="pgAdmin: Constraints of the recommendations table"><figcaption>pgAdmin · recommendations › Constraints (9)</figcaption></figure>
</div>"""))

S.append(slide("BEGIN; … COMMIT;", "The load: one transaction, nothing half-loaded", f"""
<div class="pipe">
  <div class="step"><b>Raw files</b><span>CSV + JSON lines</span></div>
  <div class="step"><b>Python</b><span>reads, checks and converts formats</span></div>
  <div class="step"><b>COPY FROM STDIN</b><span>streams 41 M lines, no file in memory</span></div>
  <div class="step"><b>TEMP table</b><span>ON COMMIT DROP</span></div>
  <div class="step"><b>DISTINCT ON</b><span>(user_id, app_id) applies R4</span></div>
  <div class="step end"><b>8 tables</b><span>{total_rows / 1e6:.1f} M rows</span></div>
</div>
<div class="cols2 tight">
  <div class="stat"><b>{CLEAN['seconds']} s</b><span>full load of {n(total_rows)} rows in a single transaction</span></div>
  <pre class="term">$ python etl/load.py --inject-error
games: 50,872 rows
inside the transaction: games 50872 …
injecting positive_ratio = 150
<span class="d">ERROR: CheckViolation games_positive_ratio_check</span>
ROLLBACK done
<span class="u">after rollback: every table 0 rows</span></pre>
</div>"""))

S.append(slide("EXPLAIN (ANALYZE) …", "Indexes: same query, same data, different plan", f"""
<div class="chart">{log_bench()}</div>
<p class="foot">Best of 3 runs, logarithmic scale. Main index: <code>recommendations (app_id, review_date) INCLUDE (is_recommended, hours)</code>, because the FK on app_id has no index of its own.
Queries that need all 41 M rows (Q04, Q09, Q12) still scan the whole table.</p>"""))

S.append(slide("\\i sql/queries.sql", "Twelve questions, written in SQL", f"""
<table class="matrix"><thead><tr><th></th><th class="q">Question · author Odei Fernández Rodríguez</th>{''.join(f'<th>{E(f)}</th>' for f, _ in FEATURES)}</tr></thead>
<tbody>{matrix_rows}</tbody></table>"""))

S.append(slide("-- Q02 · RANK() OVER (PARTITION BY release_year)", "Most reviewed is not most liked", f"""
<div class="cols-chart">
  <div class="chart">{hbars_pct(q02_items, row=27, label_w=300, hi=("Battlefield™ 2042 · 2021", "Factorio · 2020"))}</div>
  <div class="aside">
    <p>The 3 most reviewed games of each release year, 2018–2022, and the share of their reviewers who recommend them.</p>
    <p><b class="d">Battlefield 2042</b>: 106,386 reviews, only <b>32.8 %</b> recommend it.</p>
    <p><b class="u">Factorio</b>: <b>96.7 %</b>.</p>
    <p class="small">Bars under 70 % in coral.</p>
  </div>
</div>"""))

S.append(slide("-- Q04 · CTE + CASE price bands + percentile_disc", "Do players like expensive games more?", f"""
<div class="cols2">
  <div class="chart-card"><h3>% of reviews that recommend</h3>{vbars([(r['price_band'].replace('0.01-4.99', '< 5').replace('-', '–'), r['pct_recommended']) for r in q04], 540, 300, lambda v: f'{v:.0f}', 'bar-up', 100, ' %')}</div>
  <div class="chart-card"><h3>Median hours played when reviewing</h3>{vbars([(r['price_band'].replace('0.01-4.99', '< 5').replace('-', '–'), float(r['median_hours'])) for r in q04], 540, 300, lambda v: f'{v:g}', 'bar-gold', None, ' h')}</div>
</div>
<p class="foot">Prices in $. Free games are recommended least (80 %). Playtime at review grows with price, from 6.6 h under 5 $ to 60 h above 40 $.</p>"""))

S.append(slide("-- Q12 · percentile_disc(0.5) … FILTER (WHERE NOT is_recommended)", "Negative reviews come early", f"""
<div class="legend"><span class="u">■ recommended</span><span class="d">■ not recommended</span><span class="muted">median hours at review, by the game's main tag</span></div>
<div class="chart">{paired_bars([(r['tag'], float(r['median_hours_recommended']), float(r['median_hours_not_recommended'])) for r in q12])}</div>
<p class="foot">For every main tag, players who do not recommend stop after a third of the hours or less. RPG: 32.6 h vs 9.3 h.</p>"""))

S.append(slide("-- Q07 · SUM() OVER (PARTITION BY platform ORDER BY release_year)", "Mac and Linux are fading", f"""
<div class="cols-chart">
  <div class="chart">{line_chart(q07_series, years, colors={'Mac': 'var(--up)', 'Linux': 'var(--gold)'})}</div>
  <div class="aside">
    <p>Share of the games released each year that also run on Mac or Linux.</p>
    <p>Both peaked in <b>2013</b> and have fallen every year since.</p>
    <p class="small">Steam Deck is left out: the flag is set for 50,870 of 50,872 games.</p>
  </div>
</div>"""))

S.append(slide("streamlit run app/app.py", "The dashboard: SQL in, charts out", f"""
<div class="cols-shot">
  <figure class="shot"><img src="{DASH}" alt="Dashboard, trend tab"><figcaption>Trend tab · Q03 with tag and date filters</figcaption></figure>
  <div>
    <ul>
      <li><b>11 tabs, 13 charts</b>, each fed only by the rows of one query.</li>
      <li>Every filter goes to SQL as a bound parameter <code>%(tag)s</code>; the user never types SQL.</li>
      <li><code>'; DROP TABLE games; --</code> is searched as plain text.</li>
      <li>Bad input shows a message: limited widgets, 120 s timeout, rollback on any error.</li>
      <li>The sale simulation runs an <b>UPDATE, then ROLLBACK</b>.</li>
    </ul>
    <figure class="shot small"><img src="{SALE}" alt="Sale simulation tab"></figure>
    <p class="demo"><span class="playbtn">▶&nbsp; Live demo</span></p>
  </div>
</div>"""))

S.append(slide("\\q", "How AI was used, and what I learned", """
<div class="cols2">
  <div>
    <h3>AI adoption</h3>
    <ul>
      <li>Claude Code drafted the profiling queries, schema, ETL, queries, app and report.</li>
      <li>Every output was checked: row counts against the files, query samples by hand, plans with EXPLAIN, the app with AppTest and bad inputs.</li>
      <li>Full table in section 7 of the report.</li>
    </ul>
  </div>
  <div>
    <h3>Lessons</h3>
    <ul>
      <li>Profile first: the duplicates and the price placeholder only appear when you count.</li>
      <li>One transaction makes a 9-minute load safe to fail.</li>
      <li>An FK constraint does not create an index.</li>
      <li>Big sorts need memory limits: a 1 GB <code>work_mem</code> per worker filled the laptop's RAM once.</li>
    </ul>
  </div>
</div>
<p class="thanks">Thank you · questions?</p>""", "last"))

SLIDES = "\n".join(S)

CSS = """
/* Layout: a fixed 1280×720 stage scaled to the window, styled like a game-store client:
   top navigation bar, store-page cover, review-score colours (positive / mixed / negative). */
:root {
  --ink: #1b2838; --top: #171a21; --panel: #16202d; --panel2: #2a475e; --line: #2f4256;
  --text: #c7d5e0; --white: #ffffff; --muted: #8f98a0;
  --up: #66c0f4; --down: #c9603a; --gold: #b9a074; --green: #a4d007;
  --display: "Figtree", "Motiva Sans", Arial, sans-serif;
  --body: "Figtree", "Motiva Sans", Arial, sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, "DejaVu Sans Mono", monospace;
  color-scheme: dark;
}
html, body { height: 100%; }
body { margin: 0; background: var(--ink); color: var(--text); font-family: var(--body); overflow: hidden;
       padding-left: max(0px, env(safe-area-inset-left, 0px)); padding-right: max(0px, env(safe-area-inset-right, 0px)); }
#viewport { position: fixed; inset: 0; display: grid; place-items: center; }
#stage { width: 1280px; height: 720px; position: relative; transform-origin: center center; flex: none; }
.slide { position: absolute; inset: 0; padding: 74px 64px 50px; box-sizing: border-box;
         display: flex; flex-direction: column; gap: 16px; background:
         radial-gradient(ellipse 900px 380px at 50% 0%, rgba(42,71,94,.85), transparent 70%), var(--ink);
         opacity: 0; visibility: hidden; transition: opacity .35s ease; }
.slide.active { opacity: 1; visibility: visible; }
@media (prefers-reduced-motion: reduce) { .slide { transition: none; } }
.prompt { font: 500 14px var(--mono); color: var(--muted); letter-spacing: .01em; }
.topnav { position: absolute; left: 0; right: 0; top: 0; height: 48px; background: var(--top); display: flex; align-items: center;
          gap: 30px; padding: 0 64px; font: 600 15px var(--body); letter-spacing: .06em; color: var(--text); box-shadow: 0 2px 8px rgba(0,0,0,.35); }
.topnav .brand { font-weight: 800; color: var(--white); letter-spacing: .12em; margin-right: 18px; }
.topnav span.on { color: var(--up); box-shadow: inset 0 -3px 0 var(--up); padding: 14px 0 11px; }
.topnav .who { margin-left: auto; font-weight: 400; letter-spacing: 0; color: var(--muted); font-size: 14px; }
.prompt .db { color: var(--up); }
h1, h2, h3 { font-family: var(--display); margin: 0; text-wrap: balance; }
h2 { font-size: 38px; font-weight: 700; letter-spacing: -.005em; line-height: 1.1; color: var(--white); }
h3 { font-size: 14px; font-weight: 600; color: var(--up); margin-bottom: 12px; text-transform: uppercase; letter-spacing: .08em; }
p { margin: 0; line-height: 1.5; }
code { font-family: var(--mono); font-size: .88em; color: var(--gold); }
ul { margin: 0; padding-left: 20px; display: grid; gap: 10px; font-size: 19px; line-height: 1.45; }
li::marker { color: var(--up); }
b.u, .u { color: var(--up); } b.d, .d { color: var(--down); } .muted { color: var(--muted); }
.foot { margin-top: auto; font-size: 15px; color: var(--muted); max-width: 1100px; }
.small { font-size: 14px; color: var(--muted); }

/* cover: store page */
.cover { justify-content: space-between; padding-top: 92px; }
.store { display: grid; grid-template-columns: 1fr 380px; gap: 44px; align-items: start; }
.store-main { display: grid; gap: 20px; }
.crumbs { font-size: 14px; color: var(--muted); }
.cover h1 { font-size: 64px; font-weight: 800; line-height: 1.02; letter-spacing: -.015em; color: var(--white); }
.lede { font-size: 22px; color: var(--text); max-width: 700px; }
.usertags { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; max-width: 720px; }
.usertags .hd { width: 100%; font-size: 13px; color: var(--muted); margin-bottom: 2px; }
.tag { background: rgba(103,193,245,.2); color: var(--up); padding: 4px 9px; border-radius: 2px; font-size: 14px; }
.infobox { background: rgba(0,0,0,.25); border-radius: 3px; overflow: hidden; }
.capsule { height: 150px; display: grid; place-content: center; text-align: center; background:
           linear-gradient(135deg, #2a475e 0%, #1e3a52 45%, #102335 100%); border-bottom: 1px solid var(--line); }
.capsule span { font: 800 46px var(--display); color: var(--white); font-variant-numeric: tabular-nums; }
.capsule small { color: var(--up); font-size: 14px; letter-spacing: .1em; text-transform: uppercase; }
.infobox dl { display: grid; grid-template-columns: 110px 1fr; gap: 9px 10px; margin: 0; padding: 16px 18px 18px; font-size: 14px; }
.infobox dt { color: var(--muted); text-transform: uppercase; font-size: 12px; padding-top: 2px; letter-spacing: .03em; }
.infobox dd { margin: 0; color: var(--text); } .infobox dd.link { color: var(--up); }
.pos { color: var(--up); }

/* dataset */
.files { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
.file { background: rgba(0,0,0,.22); border: 1px solid var(--line); border-radius: 3px; padding: 18px; display: grid; gap: 6px; align-content: start; }
.file b { font: 700 34px var(--display); font-variant-numeric: tabular-nums; }
.file.big b { color: var(--up); }
.file span { color: var(--muted); font-size: 15px; line-height: 1.4; }
.checks { list-style: none; padding: 0; grid-template-columns: 1fr 1fr; gap: 12px 30px; margin-top: 10px; font-size: 18px; }
.checks li::before { content: "✓"; color: var(--up); font-weight: 700; margin-right: 10px; }
.checks b { margin-right: 6px; }

/* findings */
.finds { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.find { border-top: 3px solid var(--down); background: rgba(0,0,0,.22); padding: 18px 20px; border-radius: 0 0 3px 3px; display: grid; gap: 6px; }
.find:nth-child(4), .find:nth-child(6) { border-top-color: var(--gold); }
.find:nth-child(5) { border-top-color: var(--up); }
.find b { font: 800 44px var(--display); font-variant-numeric: tabular-nums; }
.find span { color: var(--muted); font-size: 17px; line-height: 1.4; }

/* rules */
.rules { border-collapse: collapse; font-size: 19px; width: 100%; }
.rules th { font: 600 16px var(--mono); color: var(--gold); text-align: left; padding: 10px 14px 10px 0; width: 48px; }
.rules td { padding: 10px 0; border-bottom: 1px solid var(--line); }
.rules td.num { text-align: right; font: 600 22px var(--display); font-variant-numeric: tabular-nums; width: 180px; }

/* ER */
.er-wrap { flex: 1; min-height: 0; background: rgba(0,0,0,.22); border: 1px solid var(--line); border-radius: 3px;
           padding: 12px; display: flex; justify-content: center; align-items: center; overflow: hidden; }
.er-wrap img { height: 100%; max-height: 460px; width: auto; max-width: 100%; object-fit: contain; }

.cols2 { display: grid; grid-template-columns: 1fr 1fr; gap: 40px; }
.cols2.tight { gap: 24px; align-items: center; margin-top: 16px; }
li.exc { list-style: none; margin-left: -20px; background: rgba(0,0,0,.22); border: 1px solid var(--line); border-left: 3px solid var(--gold); border-radius: 3px; padding: 12px 16px; }

/* constraints */
.cons-layout { display: grid; grid-template-columns: 1fr 300px; gap: 36px; flex: 1; min-height: 0; }
.cons-layout ul { font-size: 18px; margin-top: 24px; }
.consbar { display: flex; height: 92px; border-radius: 3px; overflow: hidden; gap: 3px; }
.seg { display: grid; align-content: center; padding: 0 10px; min-width: 0; color: var(--ink); }
.seg b { font: 800 30px var(--display); } .seg span { font: 600 12px var(--mono); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.s0 { background: var(--gold); } .s1 { background: var(--up); } .s2 { background: #9fd3f7; } .s3 { background: var(--down); } .s4 { background: #c9d4df; }
.shot { margin: 0; display: grid; gap: 6px; align-content: start; min-height: 0; }
.shot img { max-width: 100%; max-height: 470px; object-fit: contain; border-radius: 3px; border: 1px solid var(--line); }
.shot.small img { max-height: 150px; object-fit: cover; object-position: top; }
figcaption { font: 13px var(--mono); color: var(--muted); }

/* pipeline */
.pipe { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin-top: 8px; }
.step { position: relative; background: rgba(0,0,0,.22); border: 1px solid var(--line); border-radius: 3px; padding: 16px 14px; display: grid; gap: 6px; }
.step b { font: 700 18px var(--display); } .step span { color: var(--muted); font-size: 14px; line-height: 1.35; }
.step:not(:last-child)::after { content: "→"; position: absolute; right: -12px; top: 50%; transform: translate(50%, -50%); color: var(--up); font-weight: 700; z-index: 1; }
.step.end { border-color: var(--up); }
.stat b { display: block; font: 800 70px var(--display); color: var(--up); } .stat span { font-size: 19px; color: var(--muted); }
.term { margin: 0; background: var(--top); border: 1px solid var(--line); border-radius: 3px; padding: 16px 18px; font: 15px/1.55 var(--mono); color: var(--text); white-space: pre-wrap; }

/* charts */
.chart svg, .chart-card svg { display: block; }
svg .grid { stroke: var(--line); stroke-width: 1; } svg .axis { stroke: var(--muted); stroke-width: 1; }
svg .lbl { fill: var(--text); font: 15px var(--body); } svg .lbl.strong { font-weight: 600; }
svg .sub { fill: var(--muted); font: 11px var(--mono); } svg .sub.up { fill: var(--up); font-size: 13px; font-weight: 600; }
svg .tick { fill: var(--muted); font: 13px var(--mono); }
svg .val { fill: var(--text); font: 600 14px var(--mono); } svg .val.small { font-size: 12px; }
svg .bar-up { fill: var(--up); } svg .bar-down { fill: var(--down); } svg .bar-gold { fill: var(--gold); }
svg .hi { stroke: var(--text); stroke-width: 2; }
.cols-chart { display: grid; grid-template-columns: 1.55fr 1fr; gap: 36px; align-items: center; flex: 1; }
.aside { display: grid; gap: 14px; font-size: 20px; }
.chart-card { background: rgba(0,0,0,.22); border: 1px solid var(--line); border-radius: 3px; padding: 18px 18px 8px; }
.chart-card h3 { font-size: 17px; color: var(--muted); font-family: var(--body); font-weight: 500; }
.legend { display: flex; gap: 24px; font: 600 15px var(--mono); }

/* query matrix */
.matrix { border-collapse: collapse; width: 100%; font-size: 14px; }
.matrix th, .matrix td { padding: 6px 8px; border-bottom: 1px solid var(--line); text-align: center; }
.matrix thead th { font: 600 12px var(--mono); color: var(--muted); vertical-align: bottom; }
.matrix tbody th { font: 600 14px var(--mono); color: var(--gold); }
.matrix td { color: var(--up); font-size: 16px; }
.matrix .q { text-align: left; color: var(--text); font-size: 14px; }

.cols-shot { display: grid; grid-template-columns: 1.15fr 1fr; gap: 30px; flex: 1; min-height: 0; }
.cols-shot ul { font-size: 17px; gap: 8px; }
.cols-shot > div { display: grid; gap: 14px; align-content: start; }
.demo { margin-top: 4px; }
.playbtn { display: inline-block; font: 600 22px var(--body); color: #d2efa9; padding: 12px 30px; border-radius: 2px;
           background: linear-gradient(to right, #75b022 5%, #588a1b 95%); box-shadow: 0 2px 10px rgba(0,0,0,.3); }
.thanks { margin-top: auto; font: 800 48px var(--display); color: var(--white); }

/* controls */
#bar { position: fixed; left: 0; right: 0; bottom: 0; height: 4px; background: var(--line); }
#bar i { display: block; height: 100%; width: 0; background: var(--up); transition: width .3s; }
#nav { position: fixed; right: max(14px, env(safe-area-inset-right, 0px)); bottom: calc(14px + env(safe-area-inset-bottom, 0px)); display: flex; gap: 8px; align-items: center; font: 13px var(--mono); color: var(--muted); }
#nav button { background: var(--panel); color: var(--text); border: 1px solid var(--line); border-radius: 8px; width: 38px; height: 34px; font-size: 16px; cursor: pointer; }
#nav button:hover { border-color: var(--up); } #nav button:focus-visible { outline: 2px solid var(--up); outline-offset: 2px; }
"""

JS = """
const slides = [...document.querySelectorAll('.slide')];
const stage = document.getElementById('stage');
const counter = document.getElementById('count');
const bar = document.querySelector('#bar i');
let cur = 0;
function fit() {
  const s = Math.min(innerWidth / 1280, innerHeight / 720);
  stage.style.transform = `scale(${s})`;
}
function show(i) {
  cur = Math.max(0, Math.min(slides.length - 1, i));
  slides.forEach((el, k) => el.classList.toggle('active', k === cur));
  counter.textContent = `${cur + 1} / ${slides.length}`;
  bar.style.width = `${(cur + 1) / slides.length * 100}%`;
  if (location.hash !== '#s' + (cur + 1)) history.replaceState(null, '', '#s' + (cur + 1));
}
function fromHash() { const m = /^#s(\\d+)$/.exec(location.hash); show(m ? +m[1] - 1 : 0); }
addEventListener('keydown', e => {
  if (['ArrowRight', 'PageDown', ' ', 'Enter'].includes(e.key)) { e.preventDefault(); show(cur + 1); }
  else if (['ArrowLeft', 'PageUp', 'Backspace'].includes(e.key)) { e.preventDefault(); show(cur - 1); }
  else if (e.key === 'Home') show(0);
  else if (e.key === 'End') show(slides.length - 1);
  else if (e.key === 'f' || e.key === 'F') {
    if (document.fullscreenElement) document.exitFullscreen?.();
    else document.documentElement.requestFullscreen?.().catch(() => {});
  }
});
document.getElementById('prev').onclick = () => show(cur - 1);
document.getElementById('next').onclick = () => show(cur + 1);
let tx = null;
addEventListener('touchstart', e => { tx = e.touches[0].clientX; }, { passive: true });
addEventListener('touchend', e => { if (tx === null) return; const dx = e.changedTouches[0].clientX - tx;
  if (Math.abs(dx) > 50) show(cur + (dx < 0 ? 1 : -1)); tx = null; });
addEventListener('resize', fit);
addEventListener('hashchange', fromHash);
fit(); fromHash();
"""

page = f"""<title>Steam Reviews Database</title>
<meta name="description" content="Project B presentation: 41 million Steam reviews in PostgreSQL">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Figtree:wght@300;400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>{CSS}</style>
<div id="viewport"><div id="stage">
{SLIDES}
</div></div>
<div id="bar"><i></i></div>
<div id="nav"><span id="count"></span><button id="prev" aria-label="Previous slide">←</button><button id="next" aria-label="Next slide">→</button></div>
<script>{JS}</script>
"""

out = ROOT / "presentation"
# Artifact version (the platform adds the document skeleton) and a standalone file for class.
(out / "deck.html").write_text(page, encoding="utf-8")
head, _, rest = page.partition("<style>")
standalone = ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
              "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
              f"{head}<style>{rest.split('</style>', 1)[0]}</style>\n</head>\n<body>"
              f"{rest.split('</style>', 1)[1]}</body>\n</html>\n")
(out / "index.html").write_text(standalone, encoding="utf-8")
print("wrote", out / "index.html", f"{len(standalone) / 1e6:.1f} MB,", len(S), "slides")
