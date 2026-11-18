"""ETL: load the four raw Steam files into the schema created by sql/schema.sql.

    python etl/load.py                      # full load, one transaction
    python etl/load.py --inject-error       # rollback demo: fails on purpose

Rules
  * The tables must already exist (sql/schema.sql). This script only INSERTs.
  * Everything runs inside ONE transaction: if any step fails, PostgreSQL rolls
    back and no table keeps a single row.
  * Missing values stay NULL. No value is invented.
  * Python only reads the files and cleans their *format* (types, NULLs,
    pivoting the platform flags and the tag lists). It does not analyse data.
  * Every cleaning rule is counted and written to etl/cleaning_log.json.

Author: Odei Fernández Rodríguez
"""
import argparse
import csv
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("STEAM_DATA", ROOT / "data"))

# Steam review score labels, worst to best (domain knowledge, not data).
RATINGS = ["Overwhelmingly Negative", "Very Negative", "Negative", "Mostly Negative",
           "Mixed", "Mostly Positive", "Positive", "Very Positive",
           "Overwhelmingly Positive"]
# csv column -> platform name
PLATFORMS = {"win": "Windows", "mac": "Mac", "linux": "Linux", "steam_deck": "Steam Deck"}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HOURS_RE = re.compile(r"^\d+(\.\d)?$")

rules = Counter()          # cleaning rule -> rows affected


def connect():
    return psycopg2.connect(dbname=os.environ.get("PGDATABASE", "steam"),
                            host=os.environ.get("PGHOST", "localhost"),
                            port=os.environ.get("PGPORT", "5432"),
                            user=os.environ.get("PGUSER", "postgres"),
                            password=os.environ.get("PGPASSWORD"))


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# --------------------------------------------------------------- format helpers
def to_bool(v):
    if v == "true":
        return True
    if v == "false":
        return False
    raise ValueError(f"not a boolean: {v!r}")


def to_date(v):
    if not DATE_RE.match(v):
        raise ValueError(f"not an ISO date: {v!r}")
    return v  # PostgreSQL parses it; date.fromisoformat would only slow us down


def to_nonneg_int(v):
    n = int(v)
    if n < 0:
        raise ValueError(f"negative integer: {v!r}")
    return n


class LineStream:
    """File-like object over an iterator of text lines, for cursor.copy_expert."""

    def __init__(self, lines):
        self.lines = lines
        self.buf = ""

    def read(self, size=-1):
        while size < 0 or len(self.buf) < size:
            try:
                self.buf += next(self.lines)
            except StopIteration:
                break
        if size < 0:
            out, self.buf = self.buf, ""
        else:
            out, self.buf = self.buf[:size], self.buf[size:]
        return out

    readline = read


# ------------------------------------------------------------------- loaders
def load_lookups(cur):
    execute_values(cur, "INSERT INTO ratings (rating_id, label, rank_order) VALUES %s",
                   [(i, label, i) for i, label in enumerate(RATINGS, 1)])
    execute_values(cur, "INSERT INTO platforms (platform_id, name) VALUES %s",
                   list(enumerate(PLATFORMS.values(), 1)))
    log(f"ratings: {len(RATINGS)} rows, platforms: {len(PLATFORMS)} rows")


def read_metadata():
    meta = {}
    with open(DATA / "games_metadata.json", encoding="utf-8") as f:
        for line in f:
            doc = json.loads(line)
            meta[int(doc["app_id"])] = doc
    return meta


def load_games(cur):
    meta = read_metadata()
    rating_id = {label: i for i, label in enumerate(RATINGS, 1)}
    platform_id = {col: i for i, col in enumerate(PLATFORMS, 1)}

    games, game_platforms, game_tags_raw = [], [], []
    with open(DATA / "games.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            app_id = int(row["app_id"])
            title = row["title"].strip()
            if title != row["title"]:
                rules["games: title trimmed"] += 1

            price_final = float(row["price_final"])
            price_original = float(row["price_original"])
            discount = float(row["discount"])
            if price_original == 0 and price_final > 0:
                # 0.00 is a placeholder: a paid game cannot have a free original
                # price. The real value is unknown -> NULL (never invented).
                price_original = discount = None
                rules["games: price_original 0 with price_final > 0 -> NULL (and discount)"] += 1

            doc = meta.get(app_id)
            if doc is None:
                rules["games: no metadata line"] += 1
                doc = {"description": None, "tags": []}
            description = (doc.get("description") or "").strip() or None
            if description is None:
                rules["games: empty description -> NULL"] += 1

            if row["rating"] not in rating_id:
                raise ValueError(f"unknown rating {row['rating']!r} for app {app_id}")

            games.append((app_id, title, to_date(row["date_release"]), rating_id[row["rating"]],
                          int(row["positive_ratio"]), to_nonneg_int(row["user_reviews"]),
                          price_final, price_original, discount, description))

            flags = [col for col in PLATFORMS if to_bool(row[col])]
            if not flags:
                rules["games: no platform flag set -> no game_platforms rows"] += 1
            game_platforms += [(app_id, platform_id[col]) for col in flags]

            tags = doc.get("tags") or []
            if not tags:
                rules["games: empty tag list -> no game_tags rows"] += 1
            seen = set()
            for tag in tags:
                tag = tag.strip()
                if tag in seen:
                    rules["game_tags: repeated tag in one game dropped"] += 1
                    continue
                seen.add(tag)
                game_tags_raw.append((app_id, tag, len(seen)))

    extra = set(meta) - {g[0] for g in games}
    if extra:
        rules["games_metadata: line without a game in games.csv (ignored)"] += len(extra)

    execute_values(cur, """INSERT INTO games (app_id, title, date_release, rating_id,
                       positive_ratio, user_reviews, price_final, price_original,
                       discount, description) VALUES %s""", games, page_size=2000)
    log(f"games: {len(games):,} rows")

    execute_values(cur, "INSERT INTO game_platforms (app_id, platform_id) VALUES %s",
                   game_platforms, page_size=5000)
    log(f"game_platforms: {len(game_platforms):,} rows")

    tag_id = {name: i for i, name in enumerate(sorted({t for _, t, _ in game_tags_raw}), 1)}
    execute_values(cur, "INSERT INTO tags (tag_id, name) VALUES %s",
                   [(i, name) for name, i in tag_id.items()])
    execute_values(cur, "INSERT INTO game_tags (app_id, tag_id, tag_rank) VALUES %s",
                   [(a, tag_id[t], r) for a, t, r in game_tags_raw], page_size=5000)
    log(f"tags: {len(tag_id):,} rows, game_tags: {len(game_tags_raw):,} rows")


def user_lines():
    with open(DATA / "users.csv", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        assert header == ["user_id", "products", "reviews"], header
        for user_id, products, _reviews in reader:
            # reviews is not loaded: it is derived data (= COUNT of the user's
            # rows in recommendations, checked in profiling/profile.sql).
            rules["users: derived column reviews not loaded"] += 1
            yield f"{to_nonneg_int(user_id)},{to_nonneg_int(products)}\n"


def recommendation_lines():
    with open(DATA / "recommendations.csv", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        assert header == ["app_id", "helpful", "funny", "date", "is_recommended",
                          "hours", "user_id", "review_id"], header
        for app_id, helpful, funny, day, rec, hours, user_id, review_id in reader:
            if not HOURS_RE.match(hours):
                raise ValueError(f"bad hours {hours!r} in review {review_id}")
            yield (f"{int(review_id)},{int(app_id)},{int(user_id)},{to_date(day)},"
                   f"{'t' if to_bool(rec) else 'f'},{hours},"
                   f"{to_nonneg_int(helpful)},{to_nonneg_int(funny)}\n")


def load_users(cur):
    t = time.time()
    cur.copy_expert("COPY users (user_id, products) FROM STDIN WITH (FORMAT csv)",
                    LineStream(user_lines()))
    log(f"users: {cur.rowcount:,} rows ({time.time() - t:.0f}s)")


def load_recommendations(cur):
    t = time.time()
    # Temporary table that lives only inside this transaction.
    cur.execute("""CREATE TEMP TABLE stage_recommendations
                   (LIKE recommendations INCLUDING DEFAULTS) ON COMMIT DROP""")
    cur.copy_expert("""COPY stage_recommendations (review_id, app_id, user_id, review_date,
                       is_recommended, hours, helpful, funny) FROM STDIN WITH (FORMAT csv)""",
                    LineStream(recommendation_lines()))
    staged = cur.rowcount
    log(f"stage_recommendations: {staged:,} rows read ({time.time() - t:.0f}s)")

    # Steam allows one review per user and game. The source has a few pairs twice;
    # keep the most recent review (latest date, then highest review_id).
    t = time.time()
    cur.execute("SET LOCAL work_mem = '256MB'")
    cur.execute("""
        INSERT INTO recommendations
        SELECT DISTINCT ON (user_id, app_id) *
        FROM stage_recommendations
        ORDER BY user_id, app_id, review_date DESC, review_id DESC""")
    inserted = cur.rowcount
    rules["recommendations: duplicate (user_id, app_id) -> older review dropped"] = staged - inserted
    log(f"recommendations: {inserted:,} rows ({time.time() - t:.0f}s)")


def table_counts(cur):
    out = {}
    for t in ("ratings", "platforms", "games", "game_platforms", "tags", "game_tags",
              "users", "recommendations"):
        cur.execute(f"SELECT count(*) FROM {t}")
        out[t] = cur.fetchone()[0]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--inject-error", action="store_true",
                    help="insert an invalid row after the games are loaded, to show the rollback")
    args = ap.parse_args()

    start = time.time()
    conn = connect()
    cur = conn.cursor()                     # psycopg2 opens a transaction on first execute
    try:
        if any(table_counts(cur).values()):
            raise RuntimeError("tables are not empty: run sql/schema.sql first")

        load_lookups(cur)
        load_games(cur)

        if args.inject_error:
            log(f"inside the transaction: {table_counts(cur)}")
            log("injecting a game with positive_ratio = 150 (violates CHECK 0..100)")
            cur.execute("""INSERT INTO games (app_id, title, date_release, rating_id,
                           positive_ratio, user_reviews, price_final)
                           VALUES (999999999, 'Broken row', '2020-01-01', 5, 150, 10, 0)""")

        load_users(cur)
        load_recommendations(cur)
        counts = table_counts(cur)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        log(f"ERROR: {type(exc).__name__}: {str(exc).strip().splitlines()[0]}")
        log("ROLLBACK done")
        with conn.cursor() as c2:
            log(f"after rollback: {table_counts(c2)}")
        conn.close()
        return 1

    log(f"COMMIT done in {time.time() - start:.0f}s: {counts}")
    report = {"loaded_at": date.today().isoformat(), "seconds": round(time.time() - start),
              "row_counts": counts, "cleaning_rules": dict(rules)}
    (ROOT / "etl" / "cleaning_log.json").write_text(json.dumps(report, indent=2,
                                                               ensure_ascii=False))
    for rule, n in rules.items():
        print(f"  {n:>12,}  {rule}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
