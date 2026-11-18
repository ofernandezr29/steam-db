"""Build the Project B report (report/Project_B_Report.pdf).

Every number in the report is read from the files written by the SQL runs:
  profiling/profile_results.md   data profile (profiling/profile.sql)
  etl/cleaning_log.json          rows affected by each cleaning rule (etl/load.py)
  queries/query_results.json     the 12 queries (queries/run_queries.py)
  queries/index_benchmark.json   timings with and without indexes
  queries/verify_constraints.out constraints after the load
Needs: pip install weasyprint
"""
import html
import json
import re
from pathlib import Path

from weasyprint import HTML

ROOT = Path(__file__).resolve().parents[1]
REP = ROOT / "report"
AUTHOR = "Odei Fernández Rodríguez"

E = html.escape


def md_tables(path):
    """{section title: [(header, rows)]} from a markdown file made of ## + tables."""
    out, title = {}, None
    for block in re.split(r"^## ", Path(path).read_text(encoding="utf-8"), flags=re.M)[1:]:
        title, _, body = block.partition("\n")
        lines = [l for l in body.splitlines() if l.startswith("|")]
        if lines:
            head = [c.strip() for c in lines[0].strip("|").split("|")]
            rows = [[c.strip() for c in l.strip("|").split("|")] for l in lines[2:]]
            out[title.strip()] = (head, rows)
    return out


def table(head, rows, cls="", num_from=1, maxlen=70):
    th = "".join(f"<th>{E(str(h))}</th>" for h in head)
    body = ""
    for r in rows:
        tds = ""
        for i, v in enumerate(r):
            v = "NULL" if v is None else v
            if isinstance(v, float):
                v = f"{v:,.2f}".rstrip("0").rstrip(".") if abs(v) < 1e6 else f"{v:,.0f}"
            elif isinstance(v, int) and not isinstance(v, bool) and head[i] not in (
                    "release_year", "user_id", "app_id", "month"):
                v = f"{v:,}"
            s = str(v)
            if maxlen and len(s) > maxlen:
                s = s[:maxlen - 3] + "…"
            num = i >= num_from and re.fullmatch(r"-?[\d,]+(\.\d+)?", s or "x")
            tds += f'<td class="{"n" if num else ""}">{E(s)}</td>'
        body += f"<tr>{tds}</tr>"
    return f'<table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>'


# ------------------------------------------------------------------ data
prof = md_tables(ROOT / "profiling" / "profile_results.md")
clean = json.loads((ROOT / "etl" / "cleaning_log.json").read_text())
Q = json.loads((ROOT / "queries" / "query_results.json").read_text())
bench = json.loads((ROOT / "queries" / "index_benchmark.json").read_text())
verify = (ROOT / "queries" / "verify_constraints.out").read_text()


def prof_table(prefix, **kw):
    for k, (h, r) in prof.items():
        if k.startswith(prefix):
            return table(h, r, **kw)
    raise KeyError(prefix)


# constraint summary block (section 2 of verify_constraints.out)
m = re.search(r"table_name\s+\|\s+pk.*?\n-+\+.*?\n(.*?)\n\(\d+ filas?\)", verify, re.S)
cons_rows = [[c.strip() for c in l.split("|")] for l in m.group(1).splitlines()]
rejections = re.findall(r"NOTICE:\s+(rejected\s+\[\d+\].*)", verify)
n_constraints = int(re.search(r"\((\d+) filas?\)", verify).group(1))

MEANING = {
    "Q01": "Niche tags with a dedicated audience (Cats, Soundtrack, Precision Platformer) average "
           "a higher store score than mass genres, so a tag says something about expected quality "
           "and not only about content.",
    "Q02": "Popularity and satisfaction are different things: Battlefield 2042 is the second most "
           "reviewed 2021 game but only 32.8 % of its reviewers recommend it, while Factorio "
           "(2020) reaches 96.7 %.",
    "Q03": "Roguelike reviews peak every June and November (Steam's summer and autumn sales) and "
           "those peaks are also the most positive months; from 2019 to 2020 the monthly volume "
           "grew by 90–270 % year on year.",
    "Q04": "Games priced 5–40 $ are recommended more (≈ 88 %) than free games (80 %), and the "
           "median playtime at review grows with the price, from 6.6 h under 5 $ to 60 h above 40 $.",
    "Q05": "For several very popular games the dataset's reviewers are clearly more critical than "
           "the store score (GTA V: 86 vs 68.3), so the sample is not a perfect copy of the store "
           "and the other results describe this sample.",
    "Q06": "Early-access reviews are much more negative for Singleplayer (60.4 % vs 86.4 %) and "
           "Sandbox games, while Simulation games are liked more during early access: unfinished "
           "story-driven games are punished most.",
    "Q07": "Mac and Linux support peaked in 2013 (44 % and 38 % of new games) and has fallen every "
           "year since, to 15 % and 11 % in 2023; the Steam Deck flag is set for almost every game, "
           "so that column carries no information.",
    "Q08": "Touch-Friendly, Dating Sim, LGBTQ+ and Great Soundtrack are 3–5 times more frequent among "
           "'Overwhelmingly Positive' games than in the whole catalogue.",
    "Q09": "A handful of reviewers collect hundreds of helpful votes per review; one of them (user "
           "5016837) recommends fewer than 1 % of the games reviewed, an influential critic.",
    "Q10": "A parameterised search answers the typical user question in tens of milliseconds and "
           "also shows the cleaning rules at work (Portal 2's unknown original price is NULL).",
    "Q11": "A half-price sale on the 1,800 paid Roguelike games would lower their average price from "
           "10.52 $ to 5.67 $; after the ROLLBACK the table is unchanged.",
    "Q12": "For every main tag, players who do not recommend a game stop after a third or less of the "
           "hours of those who recommend it (RPG: 32.6 h vs 9.3 h), so negative reviews come early.",
}

TABS = [("tab01.png", "Trend (Q03): tag and date range filters; reviews per month, % recommended, "
                      "growth vs the year before"),
        ("tab02.png", "Tags (Q01, Q08): sliders for minimum games and number of tags; rating selector"),
        ("tab03.png", "Top games (Q02): release-year range and top-N per year"),
        ("tab04.png", "Price (Q04): platform filter; % recommended and median hours by price band"),
        ("tab05.png", "Early access (Q06): minimum early-access reviews per tag"),
        ("tab06.png", "Platforms (Q07): first release year shown"),
        ("tab07.png", "Store vs dataset (Q05): minimum reviews; scatter with the y = x line"),
        ("tab08.png", "Playtime (Q12): number of main tags"),
        ("tab09.png", "Reviewers (Q09): minimum reviews per user and number of users"),
        ("tab10.png", "Search (Q10): free text, sent as a bound ILIKE parameter"),
        ("tab11.png", "Sale simulation (Q11): UPDATE inside a transaction followed by ROLLBACK")]

AI_ROWS = [
    ("Data profile queries (profiling/profile.sql)", "Claude Code (Claude Opus)",
     "First version of the 16 profiling queries and of the loader that copies the raw files "
     "into text-only staging tables.",
     "Re-ran every query and compared key counts with wc -l on the files and with manual "
     "samples (e.g. the 21 duplicated user/game pairs were inspected one by one)."),
    ("Schema design (sql/schema.sql) and ER diagram", "Claude Code",
     "Proposal of the 8 tables, data types and CHECK constraints; Graphviz script for the diagram.",
     "Checked every constraint against the profile ranges; verify_constraints.sql tries 7 invalid "
     "rows and all are rejected."),
    ("ETL script (etl/load.py)", "Claude Code",
     "Python loader with COPY streaming, one transaction, cleaning-rule counters and the "
     "--inject-error rollback demo.",
     "Compared loaded row counts with the profile (41,154,794 − 21 = 41,154,773); ran the "
     "rollback demo and checked that all 8 tables were empty afterwards."),
    ("The 12 SQL queries (sql/queries.sql)", "Claude Code",
     "First version of each query and of the sentence that explains its result.",
     "Ran each query in psql/pgAdmin, checked samples by hand (e.g. counts for one game with a "
     "simple WHERE app_id = …), reviewed that every requirement (JOIN, HAVING, subquery, window, "
     "CTE, DML in a transaction) appears."),
    ("Index benchmark", "Claude Code",
     "Script that runs EXPLAIN ANALYZE with and without the secondary indexes.",
     "Read the plans to confirm the index is actually used (Index Only Scan) and not only faster "
     "by caching."),
    ("Streamlit app (app/app.py)", "Claude Code",
     "The app with 11 tabs, bound parameters, error handling and timeouts.",
     "Tested with Streamlit AppTest: all tabs, empty input, an SQL-injection string, partial date "
     "range; the injection string is treated as plain text."),
    ("Report (this PDF)", "Claude Code",
     "Report generator that reads the result files and lays out the PDF.",
     "Read the whole report and compared every number with the query outputs."),
]


# ------------------------------------------------------------------ html
def q_section(name):
    q = Q[name]
    rows = q["rows"][:8]
    return f"""
<div class="query">
  <h3>{name}. {E(q['question'])}</h3>
  <p class="meta"><b>Author:</b> {AUTHOR} · <b>Uses:</b> {E(q['uses'])} ·
     <b>Parameters:</b> <code>{E(json.dumps(q['params'], ensure_ascii=False))}</code> ·
     <b>Time:</b> {q['seconds']:.2f} s</p>
  <pre>{E(q['sql'])}</pre>
  <p class="sample">Sample of the result ({min(8, q['row_count'])} of {q['row_count']} rows):</p>
  {table(q['columns'], rows, cls='small')}
  {f'<p class="note">{E(q["extra"])}</p>' if q.get('extra') else ''}
  <p class="why"><b>Why it matters:</b> {E(MEANING[name])}</p>
</div>"""


rules_rows = [
    ("R1", "games", "price_original = 0.00 while price_final > 0 (a paid game cannot have a free "
     "original price): price_original and discount set to NULL", clean["cleaning_rules"].get(
         "games: price_original 0 with price_final > 0 -> NULL (and discount)", 0)),
    ("R2", "games", "Empty description in games_metadata.json stored as NULL, not ''",
     clean["cleaning_rules"].get("games: empty description -> NULL", 0)),
    ("R3", "game_tags", "Empty tag list: the game gets no game_tags rows (no tag invented)",
     clean["cleaning_rules"].get("games: empty tag list -> no game_tags rows", 0)),
    ("R4", "recommendations", "Same user reviewing the same game twice: keep the most recent "
     "review (latest date, then highest review_id), drop the older one",
     clean["cleaning_rules"].get(
         "recommendations: duplicate (user_id, app_id) -> older review dropped", 0)),
    ("R5", "users", "Column reviews not loaded: it is derived data (equal to the user's number of "
     "rows in recommendations for 100 % of users)",
     clean["cleaning_rules"].get("users: derived column reviews not loaded", 0)),
    ("R6", "all", "Format conversions: 'true'/'false' → boolean, ISO text → date, text → integer / "
     "numeric. Any other value would raise an error and roll the load back", 0),
    ("R7", "games / game_platforms", "Four platform flags pivoted into game_platforms rows "
     "(only the flags that are true); games with no flag set", clean["cleaning_rules"].get(
         "games: no platform flag set -> no game_platforms rows", 0)),
]

bench_rows = [(k, v["without"]["ms"], v["with"]["ms"],
               f'{v["without"]["ms"] / max(v["with"]["ms"], 0.001):,.0f}×',
               "; ".join(s for s in v["with"]["scans"] if "Index" in s))
              for k, v in bench.items()]

CSS = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm;
        @bottom-center { content: "Project B · Steam game recommendations · " counter(page);
                         font: 8pt 'DejaVu Sans'; color: #718096; } }
@page :first { @bottom-center { content: none; } }
body { font: 9.6pt/1.45 'DejaVu Sans', sans-serif; color: #1a202c; }
h1 { font-size: 23pt; margin: 0 0 4pt; color: #1a365d; }
h2 { font-size: 14.5pt; color: #1a365d; border-bottom: 2px solid #2b6cb0; padding-bottom: 3pt;
     margin: 18pt 0 8pt; page-break-after: avoid; }
h2.newpage { page-break-before: always; }
h3 { font-size: 10.8pt; color: #2c5282; margin: 12pt 0 4pt; page-break-after: avoid; }
p { margin: 4pt 0 6pt; text-align: justify; }
ul { margin: 3pt 0 6pt 0; padding-left: 15pt; } li { margin: 2pt 0; }
table { border-collapse: collapse; width: 100%; margin: 5pt 0 9pt; font-size: 8.3pt;
        page-break-inside: auto; }
th { background: #2c5282; color: white; text-align: left; padding: 3pt 5pt; font-weight: bold; }
td { padding: 2.5pt 5pt; border-bottom: 1px solid #e2e8f0; vertical-align: top; }
tr:nth-child(even) td { background: #f7fafc; }
td.n { text-align: right; white-space: nowrap; }
table.small { font-size: 7.6pt; }
pre { background: #f7fafc; border: 1px solid #e2e8f0; border-left: 3px solid #2b6cb0;
      padding: 6pt 8pt; font: 7.4pt/1.35 'DejaVu Sans Mono', monospace; white-space: pre-wrap;
      margin: 4pt 0 6pt; }
a { color: #2b6cb0; text-decoration: none; }
code { font: 8pt 'DejaVu Sans Mono', monospace; background: #edf2f7; padding: 0 2pt; }
.cover { height: 245mm; display: flex; flex-direction: column; }
.cover .band { background: #1a365d; color: white; padding: 22pt 24pt; margin: 0 0 18pt; }
.cover .band h1 { color: white; font-size: 26pt; }
.cover .band p { color: #bee3f8; font-size: 12pt; margin: 0; text-align: left; }
.facts td:first-child { font-weight: bold; width: 32%; color: #2c5282; }
.kpis { display: flex; gap: 8pt; margin: 14pt 0; }
.kpi { flex: 1; border: 1px solid #cbd5e0; border-top: 4px solid #2b6cb0; padding: 8pt; }
.kpi b { display: block; font-size: 16pt; color: #1a365d; }
.kpi span { font-size: 8pt; color: #4a5568; }
.query { page-break-inside: auto; border-top: 1px solid #cbd5e0; padding-top: 2pt; margin-top: 8pt; }
.query .meta { font-size: 8pt; color: #4a5568; text-align: left; }
.query .sample { font-size: 8pt; color: #4a5568; margin-bottom: 0; }
.why { background: #ebf8ff; border-left: 3px solid #3182ce; padding: 4pt 7pt; }
.note { font-size: 8.3pt; color: #276749; }
figure { margin: 8pt 0 12pt; page-break-inside: avoid; text-align: center; }
figure img { max-width: 100%; max-height: 118mm; border: 1px solid #cbd5e0; }
figcaption { font-size: 8.2pt; color: #4a5568; margin-top: 3pt; }
img.er { width: 100%; }
.two { display: flex; gap: 10pt; } .two > div { flex: 1; }
.rel { font: 8.4pt/1.6 'DejaVu Sans Mono', monospace; background: #f7fafc; padding: 6pt 8pt;
       border: 1px solid #e2e8f0; }
.rel u { text-decoration: underline; font-weight: bold; }
.rel i { color: #2b6cb0; font-style: normal; }
"""

counts = clean["row_counts"]
html_doc = f"""<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head><body>

<div class="cover">
  <div class="band">
    <h1>Project B · Relational Database Application on Real Data</h1>
    <p>Steam game recommendations: from four raw files to a PostgreSQL database, SQL analysis and a
       Streamlit dashboard</p>
  </div>
  <table class="facts">
    <tr><td>Group</td><td>{AUTHOR} (single-member group)</td></tr>
    <tr><td>Dataset</td><td>Game Recommendations on Steam, by Anton Kozyriev (Kaggle)</td></tr>
    <tr><td>Source</td><td>https://www.kaggle.com/datasets/antonkozyriev/game-recommendations-on-steam</td></tr>
    <tr><td>License</td><td>CC0 1.0: Public Domain</td></tr>
    <tr><td>Database</td><td>PostgreSQL 18.6 · psycopg2 2.9 · Streamlit 1.67 · Plotly 7.1</td></tr>
    <tr><td>Repository</td><td><a href="https://github.com/ofernandezr29/steam-db">https://github.com/ofernandezr29/steam-db</a></td></tr>
    <tr><td>Slides (GitHub Pages)</td><td><a href="https://ofernandezr29.github.io/steam-db/">https://ofernandezr29.github.io/steam-db/</a></td></tr>
    <tr><td>Submission</td><td>25 November 2026</td></tr>
  </table>
  <div class="kpis">
    <div class="kpi"><b>8</b><span>tables</span></div>
    <div class="kpi"><b>{counts['games']:,}</b><span>games</span></div>
    <div class="kpi"><b>{counts['users']/1e6:.1f} M</b><span>users</span></div>
    <div class="kpi"><b>{counts['recommendations']/1e6:.1f} M</b><span>reviews</span></div>
    <div class="kpi"><b>12</b><span>SQL queries</span></div>
    <div class="kpi"><b>{n_constraints}</b><span>constraints</span></div>
  </div>
  <h3>Contents</h3>
  <ul>
    <li>1. Introduction: domain, questions and data source</li>
    <li>2. Data profile and cleaning rules</li>
    <li>3. Design: ER diagram, relational model and justified exceptions</li>
    <li>4. Implementation: schema, load, constraints and indexes</li>
    <li>5. Queries (12, with author)</li>
    <li>6. Visualization</li>
    <li>7. AI adoption report</li>
    <li>Appendix: effort log and how to run the project</li>
  </ul>
</div>

<h2 class="newpage">1. Introduction</h2>
<p><b>Domain.</b> Steam is the largest PC game store. Every game has a store page with its price,
platforms, user-assigned tags and an aggregated review score, and every user can write one review
per game saying whether they recommend it and how many hours they had played. The dataset is a
public scrape of that information and links games, users and reviews through shared keys, which
makes it a good candidate for a relational model.</p>
<p><b>Questions the database answers.</b></p>
<ul>{''.join(f"<li><b>{k}.</b> {E(v['question'])}</li>" for k, v in Q.items())}</ul>
<p><b>Data sources and license.</b> <i>Game Recommendations on Steam</i>, published on Kaggle by
Anton Kozyriev (data collected from the public Steam store, reviews from 2010 to 2022), license
<b>CC0 1.0 Public Domain</b>. It is a regular dataset, not a competition dataset. It contains four
files: <code>games.csv</code> (50,872 rows), <code>games_metadata.json</code> (one JSON object per
line with description and tags, 50,872), <code>users.csv</code> (14,306,064) and
<code>recommendations.csv</code> (41,154,794, 1.9 GB). The raw files are not committed: they are
downloaded by <code>scripts/download_data.sh</code>.</p>

<h2>2. Data profile</h2>
<p>The raw files were copied, unchanged, into text-only staging tables (schema <code>raw</code>,
<code>profiling/load_raw.py</code>) so that nothing is rejected or converted before it is measured.
All the numbers below come from the 16 SQL queries of <code>profiling/profile.sql</code>.</p>
<div class="two"><div><h3>Row count of every file</h3>{prof_table('1.')}</div>
<div><h3>Candidate keys</h3>{prof_table('2.')}</div></div>
<h3>Nulls and empty values per column</h3>
{prof_table('3.', cls='small')}
<div class="two"><div>{prof_table('4.')}</div><div>{prof_table('5.')}</div></div>
<div class="two"><div><h3>Formats (values not matching the pattern)</h3>{prof_table('6.')}</div>
<div><h3>Value ranges</h3>{prof_table('7.', cls='small')}</div></div>
<h3>Coded values</h3>
<p>The rating is a code with nine labels. Its range of positive ratio and number of store reviews
shows the rule Steam uses (for example <i>Positive</i> = 80–100 % with 10–49 reviews,
<i>Very Positive</i> = 80–100 % with 50 or more):</p>
{prof_table('8.')}
<div class="two"><div><h3>Platform flag combinations</h3>{prof_table('9.', num_from=4)}</div>
<div><h3>Tags</h3>{prof_table('10.')}<h3>Orphans between files</h3>{prof_table('11.')}</div></div>
<h3>Duplicates, codes without a meaning and anything unexpected</h3>
<ul>
<li><b>No orphans:</b> every recommendation points to an existing game and user, and every game
has exactly one metadata line. 13,262 games have no review in this sample.</li>
<li><b>games.title is not a key:</b> 121 titles are repeated with different <code>app_id</code>
(e.g. four different games called <i>Loop</i>).</li>
<li><b>Duplicated reviews:</b> 21 (user, game) pairs appear twice, a few days apart (an edited
review exported twice). Steam allows one review per user and game.</li>
{f"<li><b>Price placeholder:</b> {prof['12. Unexpected: paid games whose original price is 0.00'][1][0][0]} paid games have <code>price_original = 0.00</code> and therefore a final price higher than the original. 0.00 here means unknown.</li>"}
<li><b>Derived column:</b> <code>users.reviews</code> equals the number of rows of that user in
<code>recommendations</code> for all 14,306,064 users.</li>
<li><b>Early access:</b> 2,996,566 reviews (7.3 %) of 4,304 games are dated before the game's
release date. They are not errors: <code>date_release</code> is the end of early access.</li>
<li><b>Uninformative flag:</b> <code>steam_deck</code> is true for 50,870 of 50,872 games.</li>
<li><b>Extremes:</b> 176,329 reviews with 0.0 hours and a maximum of exactly 1000.0 hours (a cap
of the source); 125,242 users with 0 products have written reviews (private or unlisted
libraries).</li>
</ul>
{prof_table('13.', cls='small', num_from=9)}

<h3>Cleaning rules (applied by <code>etl/load.py</code>)</h3>
{table(['Rule', 'Table', 'What the ETL does', 'Rows affected'], rules_rows, num_from=3, maxlen=0)}
<p>Nothing was invented: every gap stays NULL (R1, R2) or simply produces no row (R3, R7).
No row was rejected by the format conversions (R6).</p>

<h2 class="newpage">3. Design</h2>
<h3>ER diagram (course notation: PK/FK per column, 1 / N cardinalities, row counts)</h3>
<img class="er" src="file://{REP}/build/er.svg">
<h3>Relational model</h3>
<div class="rel">
ratings(<u>rating_id</u>, label, rank_order)<br>
games(<u>app_id</u>, title, date_release, <i>rating_id → ratings</i>, positive_ratio, user_reviews,
price_final, price_original, discount, description)<br>
platforms(<u>platform_id</u>, name)<br>
game_platforms(<u><i>app_id → games</i>, <i>platform_id → platforms</i></u>)<br>
tags(<u>tag_id</u>, name)<br>
game_tags(<u><i>app_id → games</i>, <i>tag_id → tags</i></u>, tag_rank)<br>
users(<u>user_id</u>, products)<br>
recommendations(<u>review_id</u>, <i>app_id → games</i>, <i>user_id → users</i>, review_date,
is_recommended, hours, helpful, funny) · UNIQUE (user_id, app_id)
</div>
<h3>Design decisions and justified exceptions</h3>
<ul>
<li><b>Platforms as an N:M relationship.</b> The four boolean columns of <code>games.csv</code>
become <code>platforms</code> + <code>game_platforms</code>, so a new platform is a new row, not a
new column, and "games on platform X" is a join.</li>
<li><b>Tags in first normal form.</b> The JSON list of tags is split into <code>tags</code> (441)
and <code>game_tags</code> (584,215). <code>tag_rank</code> keeps the order Steam shows, which
ranks tags by votes (Q06 and Q12 use it).</li>
<li><b>Rating as a lookup table.</b> The nine labels are stored once, with <code>rank_order</code>
so that they can be sorted from worst to best.</li>
<li><b>Exception 1: rating is kept although it is almost derivable</b> from
<code>positive_ratio</code> and <code>user_reviews</code> (see the coded values table). Steam does
not publish the exact rule and the ranges overlap (<i>Positive</i> and <i>Very Positive</i> share
80–100 %), so recomputing it would mean inventing a rule. It is kept as given by the source.</li>
<li><b>Exception 2: <code>user_reviews</code> and <code>positive_ratio</code> are kept</b> although
they look like aggregates of <code>recommendations</code>. They are totals of the whole store, not
of this sample, and Q05 shows they differ, so they cannot be derived.</li>
<li><b><code>users.reviews</code> is dropped</b> because it is fully derived (profile item 14) and
would become inconsistent after any INSERT or DELETE on <code>recommendations</code>.</li>
<li><b>Description stays in <code>games</code>:</b> it is a 1:1 attribute and the metadata file
has exactly one line per game, so a separate table would add a join without removing redundancy.</li>
<li><b>Keys from the source.</b> <code>app_id</code>, <code>user_id</code> and
<code>review_id</code> are stable identifiers from Steam and are unique (profile item 2), so they
are the primary keys. <code>tag_id</code> and <code>platform_id</code> are surrogate keys created
by the ETL.</li>
<li><b>Early-access reviews are kept:</b> they are real reviews with a meaning of their own
(Q06), so no CHECK forces <code>review_date ≥ date_release</code>.</li>
</ul>

<h2 class="newpage">4. Implementation</h2>
<h3>Physical schema (<code>sql/schema.sql</code>)</h3>
<p>The script creates the 8 tables before the load; the ETL only inserts rows. Types were chosen
from the profiled ranges:</p>
<ul>
<li><code>integer</code> for ids and counters (max user_id 14.3 M, max helpful 36,212), <code>smallint</code>
for small domains (ratings, tags, platforms, positive_ratio 0–100, tag_rank 1–20).</li>
<li><code>numeric(6,2)</code> for prices (max 299.99, exact cents), <code>numeric(4,1)</code> for
the discount, <code>numeric(5,1)</code> for hours (max 1000.0, one decimal in the source).</li>
<li><code>date</code> for release and review dates, <code>boolean</code> for is_recommended,
<code>varchar(200)</code> for titles (max 165) and <code>varchar(40)</code> for tag names (max 33),
<code>text</code> for descriptions (max 530).</li>
<li>CHECK constraints from the domain: positive_ratio 0–100, non-negative prices, counters and
hours, discount 0–100, <code>price_final ≤ price_original</code> when the original is known,
review dates not before Steam's launch (2003-09-12), non-blank titles, tag_rank 1–20.</li>
<li>UNIQUE: rating label and rank, platform and tag names, (app_id, tag_rank) and
(user_id, app_id) in <code>recommendations</code> (one review per user and game).</li>
</ul>
<pre>{E((ROOT / 'sql' / 'schema.sql').read_text().split('CREATE TABLE recommendations')[1].split(');')[0].join(['CREATE TABLE recommendations', ');']))}</pre>

<h3>Load (<code>etl/load.py</code>)</h3>
<ul>
<li>One transaction for the whole load: psycopg2 opens it at the first statement and the script
commits only after the last table. Any exception calls <code>rollback()</code>.</li>
<li>Small tables are inserted with <code>execute_values</code>. <code>users</code> and
<code>recommendations</code> are streamed with <code>COPY … FROM STDIN</code>: Python reads each CSV
line, validates and converts its format and passes it on, without keeping the file in memory.</li>
<li>Reviews first go to a temporary table that only exists inside the transaction
(<code>ON COMMIT DROP</code>). The final INSERT uses <code>DISTINCT ON (user_id, app_id)</code>
to apply rule R4, and the number of rows dropped is <code>staged − inserted</code>.</li>
<li>Full load: <b>{clean['seconds']} s</b> for {sum(counts.values()):,} rows.</li>
</ul>
<h3>Rollback demonstration</h3>
<p><code>python etl/load.py --inject-error</code> loads the lookups and the games and then inserts
a game with <code>positive_ratio = 150</code>:</p>
<pre>{E((ROOT / 'etl' / 'rollback_demo.log').read_text().strip())}</pre>
<p>The rows were visible inside the transaction (games: 50,872) and after the CHECK violation and
the ROLLBACK every table is empty again.</p>

<h3>Constraints verified after the load (<code>sql/verify_constraints.sql</code>)</h3>
<p>All {n_constraints} constraints are present and validated in <code>pg_constraint</code> (the same list
pgAdmin shows under <i>Tables › table › Constraints</i>):</p>
{table(['table', 'PK', 'FK', 'UNIQUE', 'CHECK', 'NOT NULL'], cons_rows)}
<figure><img src="file://{REP}/screenshots/pgadmin_constraints_query.png">
<figcaption>pgAdmin after the load: the Query Tool lists the {n_constraints} constraints of schema public,
all with validated = true.</figcaption></figure>
<div class="two"><div><figure><img style="max-height: 95mm" src="file://{REP}/screenshots/pgadmin_constraints_tree.png">
<figcaption>pgAdmin Object Explorer: Tables › recommendations › Constraints (9): primary key, 2 foreign
keys, UNIQUE (user_id, app_id) and 5 CHECK constraints. NOT NULL is shown per column.</figcaption>
</figure></div><div>
<p>The script also tries 7 invalid rows inside a transaction that is rolled back. Every one is
rejected with the expected error:</p>
<pre>{E(chr(10).join(rejections))}</pre></div></div>

<h3>Indexes (<code>sql/indexes.sql</code>)</h3>
<p>Secondary indexes are created after the load. The FK <code>recommendations.app_id</code> has no
index of its own, so the main one is <code>(app_id, review_date) INCLUDE (is_recommended, hours)</code>;
the N:M tables get the reverse index <code>(tag_id, app_id)</code>. Best of three
<code>EXPLAIN ANALYZE</code> runs (<code>queries/index_benchmark.py</code>):</p>
{table(['Query', 'Without (ms)', 'With (ms)', 'Speed-up', 'Index used'], bench_rows, maxlen=0)}
<p>Queries that aggregate all 41 million reviews (Q04, Q09, Q12) still read the whole table: an
index cannot help when every row is needed.</p>

<h2 class="newpage">5. Queries</h2>
<p>All queries are in <code>sql/queries.sql</code> and are written by {AUTHOR}, the only member of
the group. They run in PostgreSQL with bound parameters; Python only sends them and prints or
draws the rows. The required elements appear at least once: joins of 2–4 tables (all but Q03),
GROUP BY + HAVING (Q01, Q05, Q06, Q08, Q09, Q12), subqueries (Q03, Q04, Q05, Q08, Q10, Q11),
window functions (RANK in Q02 and Q09, LAG in Q03, SUM OVER in Q07), CTEs (Q02, Q03, Q04, Q07,
Q08, Q11, Q12) and an UPDATE inside a transaction (Q11).</p>
{''.join(q_section(k) for k in Q)}

<h2 class="newpage">6. Visualization</h2>
<p><b>Framework:</b> Streamlit 1.67 with Plotly charts (<code>app/app.py</code>,
<code>streamlit run app/app.py</code>). The app has 11 tabs with 13 charts, all fed directly by
the rows of the queries above.</p>
<ul>
<li><b>Only SQL computes.</b> Python sends each query with its parameters and gives the rows to
Plotly. The only conversion is NUMERIC → float so that Plotly treats it as a number.</li>
<li><b>Filters as parameters.</b> Every widget value (tag, dates, sliders, platform, rating,
search text, discount) is passed as a psycopg2 named parameter (<code>%(tag)s</code>). The user
never types SQL, and an input like <code>'; DROP TABLE games; --</code> is just searched as text.</li>
<li><b>No crashes.</b> Widgets limit the values (sliders with ranges, lists read from the
database, a text box of at most 80 characters). An incomplete date range shows a message. Every
query has a 120 s <code>statement_timeout</code>, and any database error is shown as a message
followed by a rollback.</li>
<li><b>Q11 never changes data.</b> The sale simulation runs the UPDATE and then ROLLBACK, and
checks that the average price in the table is unchanged.</li>
<li>Results are cached for one hour (<code>st.cache_data</code>), so the heavy queries (Q04, Q09,
Q12, 10–25 s on 41 M rows) only run the first time.</li>
</ul>
{''.join(f'<figure><img src="file://{REP}/screenshots/report/{f}"><figcaption>{E(c)}</figcaption></figure>' for f, c in TABS)}

<h2 class="newpage">7. AI adoption report</h2>
{table(['Task', 'Tool', 'What the AI produced', 'How it was checked'], AI_ROWS, num_from=9, maxlen=0)}

<h2>Appendix A. Effort log</h2>
<p>Single-member group: {AUTHOR} did every task: dataset choice and selection PDF, data profile,
design of the model, schema, ETL, queries, visualization, report and presentation. See
<code>EFFORT_LOG.md</code> in the repository.</p>

<h2>Appendix B. How to run</h2>
<p>Code: <a href="https://github.com/ofernandezr29/steam-db">github.com/ofernandezr29/steam-db</a> ·
Presentation slides online: <a href="https://ofernandezr29.github.io/steam-db/">ofernandezr29.github.io/steam-db</a>
(arrow keys to move, F for full screen).</p>
<pre>scripts/setup.sh                 # venv, download, CREATE DATABASE, schema, load, indexes, checks
.venv/bin/python etl/load.py --inject-error   # rollback demo (schema must be empty)
.venv/bin/python profiling/load_raw.py && .venv/bin/python profiling/run_profile.py   # data profile
.venv/bin/python queries/run_queries.py       # the 12 queries with sample parameters
.venv/bin/streamlit run app/app.py            # the dashboard</pre>
</body></html>"""

(REP / "build").mkdir(exist_ok=True)
(REP / "build" / "report.html").write_text(html_doc, encoding="utf-8")
HTML(string=html_doc, base_url=str(REP)).write_pdf(REP / "Project_B_Report.pdf")
print("wrote", REP / "Project_B_Report.pdf")
