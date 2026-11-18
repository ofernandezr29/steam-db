"""Steam reviews explorer: Streamlit front end for the Project B database.

    streamlit run app/app.py

Every number shown comes from one of the queries in sql/queries.sql. Python
only sends the query with its parameters (bound by psycopg2, never pasted into
the SQL text) and hands the returned rows to the chart. It does not filter,
join, group or reshape them.

Author: Odei Fernández Rodríguez
"""
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import plotly.express as px
import psycopg2
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from steamdb.db import ROOT, connect, load_blocks  # noqa: E402

st.set_page_config(page_title="Steam reviews explorer", page_icon="🎮", layout="wide")

QUERIES = load_blocks(ROOT / "sql" / "queries.sql")
TIMEOUT_MS = 120_000
COLORS = ["#4C78A8", "#F58518", "#54A24B", "#B279A2", "#E45756", "#72B7B2"]


@st.cache_resource
def get_conn():
    conn = connect(options=f"-c statement_timeout={TIMEOUT_MS} -c work_mem=256MB")
    conn.set_session(readonly=False, autocommit=False)
    return conn


def run(name_or_sql, params=None, rollback_only=False):
    """Run a query and return a list of dicts. Never raises: shows the error."""
    sql = QUERIES.get(name_or_sql, name_or_sql)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d.name for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        conn.rollback()      # read-only queries and the Q11 simulation are never committed
        return rows
    except psycopg2.Error as exc:
        conn.rollback()
        msg = (exc.pgerror or str(exc)).strip().splitlines()[0]
        st.error(f"The database could not answer this query: {msg}")
        return []
    except Exception as exc:  # e.g. lost connection
        st.cache_resource.clear()
        st.error(f"Unexpected error: {exc}")
        return []


@st.cache_data(show_spinner="Querying PostgreSQL…", ttl=3600)
def cached(name, params_items):
    return run(name, dict(params_items))


def q(name, **params):
    return cached(name, tuple(sorted(params.items())))


def cols(rows, *names):
    """Column-wise view of the rows for plotly. Only converts NUMERIC (Decimal)
    to float so plotly treats it as a number; no value is computed here."""
    return {n: [float(r[n]) if isinstance(r[n], Decimal) else r[n] for r in rows] for n in names}


def show_sql(name):
    with st.expander("SQL of this chart"):
        st.code(QUERIES[name], language="sql")


@st.cache_data(ttl=3600)
def tag_names():
    return [r["name"] for r in run("SELECT name FROM tags ORDER BY name")]


@st.cache_data(ttl=3600)
def platform_names():
    return [r["name"] for r in run("SELECT name FROM platforms ORDER BY platform_id")]


@st.cache_data(ttl=3600)
def rating_labels():
    return [r["label"] for r in run("SELECT label FROM ratings ORDER BY rank_order DESC")]


@st.cache_data(ttl=3600)
def overview():
    rows = run("""SELECT (SELECT count(*) FROM games) AS games,
                         (SELECT count(*) FROM users) AS users,
                         (SELECT count(*) FROM recommendations) AS reviews,
                         (SELECT count(*) FROM tags) AS tags,
                         (SELECT min(review_date) FROM recommendations) AS first_review,
                         (SELECT max(review_date) FROM recommendations) AS last_review""")
    return rows[0] if rows else None


# ---------------------------------------------------------------- layout
st.title("🎮 Steam reviews explorer")
st.caption("Project B · Relational database on real data · Odei Fernández Rodríguez · "
           "Data: *Game Recommendations on Steam* (Kaggle, CC0)")

ov = overview()
if ov:
    c = st.columns(5)
    c[0].metric("Games", f"{ov['games']:,}")
    c[1].metric("Users", f"{ov['users']:,}")
    c[2].metric("Reviews", f"{ov['reviews']:,}")
    c[3].metric("Tags", f"{ov['tags']:,}")
    c[4].metric("Reviews from – to", f"{ov['first_review']:%Y} – {ov['last_review']:%Y}")

tabs = st.tabs(["📈 Trend", "🏷️ Tags", "🏆 Top games", "💶 Price", "🧪 Early access",
                "🖥️ Platforms", "⚖️ Store vs dataset", "⏱️ Playtime", "👥 Reviewers",
                "🔎 Search", "🛒 Sale simulation"])

# Q03 — monthly trend --------------------------------------------------------
with tabs[0]:
    st.subheader("How many reviews were written each month, and how positive were they?")
    c1, c2 = st.columns([1, 2])
    tag = c1.selectbox("Tag", ["(all games)"] + tag_names(), key="q03_tag")
    rng = c2.date_input("Review dates", (date(2017, 1, 1), date(2022, 12, 31)),
                        min_value=date(2010, 1, 1), max_value=date(2022, 12, 31), key="q03_d")
    if not (isinstance(rng, tuple) and len(rng) == 2):
        st.info("Choose a start and an end date.")
    else:
        rows = q("Q03", date_from=rng[0], date_to=rng[1],
                 tag=None if tag == "(all games)" else tag)
        if not rows:
            st.warning("No reviews for this selection.")
        else:
            d = cols(rows, "month", "reviews", "pct_recommended", "growth_vs_year_before_pct")
            a, b = st.columns(2)
            a.plotly_chart(px.bar(d, x="month", y="reviews", title="Reviews per month",
                                  color_discrete_sequence=COLORS[:1]), width="stretch")
            b.plotly_chart(px.line(d, x="month", y="pct_recommended", markers=True,
                                   title="% of reviews that recommend the game",
                                   color_discrete_sequence=COLORS[1:2]).update_yaxes(range=[0, 100]),
                           width="stretch")
            st.plotly_chart(px.bar(d, x="month", y="growth_vs_year_before_pct",
                                   title="Growth vs the same month a year before (%) — LAG(…, 12)",
                                   color_discrete_sequence=COLORS[2:3]), width="stretch")
    show_sql("Q03")

# Q01 + Q08 — tags -----------------------------------------------------------
with tabs[1]:
    st.subheader("Which tags have the best-rated games?")
    c1, c2 = st.columns(2)
    min_games = c1.slider("Minimum games per tag", 10, 5000, 500, step=10, key="q01_min")
    top = c2.slider("Tags to show", 5, 40, 15, key="q01_top")
    rows = q("Q01", min_games=min_games, limit=top)
    if rows:
        d = cols(rows, "tag", "avg_positive_ratio", "games")
        st.plotly_chart(px.bar(d, x="avg_positive_ratio", y="tag", orientation="h",
                               hover_data=["games"], color_discrete_sequence=COLORS[:1],
                               title="Average Steam positive ratio of the games with each tag")
                        .update_yaxes(autorange="reversed"), width="stretch")
    else:
        st.warning("No tag has that many games.")
    show_sql("Q01")

    st.subheader("Which tags are over-represented among the best-rated games?")
    c1, c2 = st.columns(2)
    rating = c1.selectbox("Rating", rating_labels(), key="q08_r")
    min_top = c2.slider("Minimum games with that rating", 1, 200, 20, key="q08_min")
    rows = q("Q08", rating=rating, min_games=min_top, limit=15)
    if rows:
        d = cols(rows, "tag", "lift", "pct_of_top_games", "pct_of_all_games")
        st.plotly_chart(px.bar(d, x="lift", y="tag", orientation="h",
                               hover_data=["pct_of_top_games", "pct_of_all_games"],
                               color_discrete_sequence=COLORS[3:4],
                               title=f"Lift: share among '{rating}' games ÷ share among all games")
                        .update_yaxes(autorange="reversed"), width="stretch")
    else:
        st.warning("No tag reaches that minimum for this rating.")
    show_sql("Q08")

# Q02 — top games per year ---------------------------------------------------
with tabs[2]:
    st.subheader("Most reviewed games of each release year")
    c1, c2 = st.columns([2, 1])
    y = c1.slider("Release years", 2000, 2023, (2016, 2022), key="q02_y")
    top = c2.slider("Top N per year", 1, 10, 3, key="q02_top")
    rows = q("Q02", year_from=y[0], year_to=y[1], top=top)
    if rows:
        d = cols(rows, "release_year", "title", "reviews", "pct_recommended", "rnk")
        st.plotly_chart(px.bar(d, x="release_year", y="reviews", color="title", text="title",
                               barmode="group", hover_data=["rnk", "pct_recommended"],
                               title="Reviews in the dataset, top games by release year")
                        .update_layout(showlegend=False), width="stretch")
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        st.warning("No games for these years.")
    show_sql("Q02")

# Q04 — price bands ----------------------------------------------------------
with tabs[3]:
    st.subheader("Do players like expensive games more than cheap or free ones?")
    plat = st.selectbox("Platform", ["(any)"] + platform_names(), key="q04_p")
    rows = q("Q04", platform=None if plat == "(any)" else plat)
    if rows:
        d = cols(rows, "price_band", "pct_recommended", "median_hours", "reviews", "games")
        a, b = st.columns(2)
        a.plotly_chart(px.bar(d, x="price_band", y="pct_recommended", hover_data=["games", "reviews"],
                              title="% of reviews that recommend the game",
                              color_discrete_sequence=COLORS[:1]), width="stretch")
        b.plotly_chart(px.bar(d, x="price_band", y="median_hours",
                              title="Median hours played when reviewing",
                              color_discrete_sequence=COLORS[1:2]), width="stretch")
    show_sql("Q04")

# Q06 — early access ---------------------------------------------------------
with tabs[4]:
    st.subheader("Early access reviews (before the release date) vs reviews after release")
    min_r = st.slider("Minimum early-access reviews per tag", 1000, 200000, 50000, step=1000,
                      key="q06_min")
    rows = q("Q06", min_reviews=min_r, limit=15)
    if rows:
        d = cols(rows, "tag", "pct_recommended_early", "pct_recommended_after", "early_access_reviews")
        fig = px.bar(d, x="tag", y=["pct_recommended_early", "pct_recommended_after"],
                     barmode="group", hover_data=["early_access_reviews"],
                     color_discrete_sequence=COLORS[2:4],
                     title="% recommended, by one of the game's 5 main tags")
        st.plotly_chart(fig.update_yaxes(range=[50, 100]), width="stretch")
    else:
        st.warning("No tag has that many early-access reviews.")
    show_sql("Q06")

# Q07 — platforms ------------------------------------------------------------
with tabs[5]:
    st.subheader("Platform support among the games released each year")
    y0 = st.slider("From release year", 2000, 2022, 2010, key="q07_y")
    rows = q("Q07", year_from=y0)
    if rows:
        d = cols(rows, "release_year", "platform", "pct_of_year", "games")
        st.plotly_chart(px.line(d, x="release_year", y="pct_of_year", color="platform", markers=True,
                                hover_data=["games"], color_discrete_sequence=COLORS,
                                title="% of the games released that year available on each platform"),
                        width="stretch")
    show_sql("Q07")

# Q05 — store vs dataset -----------------------------------------------------
with tabs[6]:
    st.subheader("Games the dataset's reviewers like much more (or less) than the store score")
    min_r = st.slider("Minimum reviews in the dataset", 500, 50000, 5000, step=500, key="q05_min")
    rows = q("Q05", min_reviews=min_r, limit=20)
    if rows:
        d = cols(rows, "title", "steam_positive_ratio", "dataset_pct_recommended", "gap",
                 "dataset_reviews")
        st.plotly_chart(px.scatter(d, x="steam_positive_ratio", y="dataset_pct_recommended",
                                   size="dataset_reviews", color="gap", hover_name="title",
                                   color_continuous_scale="RdBu",
                                   title="Store positive ratio vs % recommended in the dataset")
                        .add_shape(type="line", x0=0, y0=0, x1=100, y1=100,
                                   line=dict(dash="dot", color="grey")),
                        width="stretch")
        st.dataframe(rows, width="stretch", hide_index=True)
    show_sql("Q05")

# Q12 — playtime -------------------------------------------------------------
with tabs[7]:
    st.subheader("Do players who don't recommend a game stop playing earlier?")
    n = st.slider("Main tags to show", 3, 20, 10, key="q12_n")
    rows = q("Q12", min_reviews=100000, limit=n)
    if rows:
        d = cols(rows, "tag", "median_hours_recommended", "median_hours_not_recommended", "reviews")
        st.plotly_chart(px.bar(d, x="tag", y=["median_hours_recommended",
                                              "median_hours_not_recommended"],
                               barmode="group", hover_data=["reviews"],
                               color_discrete_sequence=[COLORS[2], COLORS[4]],
                               title="Median hours at review time, by the game's main tag"),
                        width="stretch")
    show_sql("Q12")

# Q09 — reviewers ------------------------------------------------------------
with tabs[8]:
    st.subheader("Reviewers whose reviews other players find most helpful")
    c1, c2 = st.columns(2)
    min_r = c1.slider("Minimum reviews per user", 10, 300, 50, key="q09_min")
    lim = c2.slider("Users to show", 5, 50, 15, key="q09_lim")
    rows = q("Q09", min_reviews=min_r, limit=lim)
    if rows:
        d = cols(rows, "user_id", "helpful_per_review", "reviews", "pct_recommended")
        d["user_id"] = [f"user {u}" for u in d["user_id"]]   # label only
        st.plotly_chart(px.bar(d, x="helpful_per_review", y="user_id", orientation="h",
                               hover_data=["reviews", "pct_recommended"],
                               color_discrete_sequence=COLORS[5:6],
                               title="Average helpful votes per review")
                        .update_yaxes(autorange="reversed", type="category"),
                        width="stretch")
        st.dataframe(rows, width="stretch", hide_index=True)
    show_sql("Q09")

# Q10 — search ---------------------------------------------------------------
with tabs[9]:
    st.subheader("Search a game by title")
    text = st.text_input("Part of the title", "portal", max_chars=80, key="q10_s").strip()
    if not text:
        st.info("Type part of a title.")
    else:
        rows = q("Q10", search=text, limit=25)
        if rows:
            st.dataframe(rows, width="stretch", hide_index=True)
        else:
            st.warning(f"No game title contains “{text}”.")
    show_sql("Q10")

# Q11 — UPDATE inside a transaction, rolled back ------------------------------
with tabs[10]:
    st.subheader("What if every paid game with a tag went on sale?")
    st.caption("Runs an UPDATE inside a transaction and then a ROLLBACK, so the database "
               "never changes. The result shows what the UPDATE did before it was undone.")
    c1, c2 = st.columns(2)
    tag = c1.selectbox("Tag", tag_names(), index=None, placeholder="Choose a tag", key="q11_t")
    pct = c2.slider("Discount %", 5, 95, 50, step=5, key="q11_p")
    if st.button("Simulate sale (UPDATE + ROLLBACK)", key="q11_go", disabled=not tag):
        rows = run("Q11", {"tag": tag, "pct": pct})          # not cached: it is DML
        if rows and rows[0]["games_updated"]:
            r = rows[0]
            c = st.columns(3)
            c[0].metric("Games updated", f"{r['games_updated']:,}")
            c[1].metric("Average price before", f"{r['avg_price_before']} $")
            c[2].metric("Average price after", f"{r['avg_price_after']} $")
            check = run("""SELECT round(avg(price_final), 2) AS avg_now FROM games
                           WHERE price_final > 0 AND app_id IN (SELECT gt.app_id FROM game_tags gt
                           JOIN tags t USING (tag_id) WHERE t.name = %(tag)s)""", {"tag": tag})
            if check:
                st.success(f"ROLLBACK done: the average price in the table is still "
                           f"{check[0]['avg_now']} $.")
        elif rows:
            st.warning("No paid game has that tag.")
    show_sql("Q11")
