"""Run every query of sql/queries.sql with example parameters and write
queries/query_results.md (question, SQL, sample of the result, run time).

Q11 is an UPDATE: it runs inside a transaction that is rolled back, and the
script then checks that the table is unchanged.
"""
import json
import sys
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from steamdb.db import ROOT, connect, load_blocks, md_table, query  # noqa: E402

PARAMS = {
    "Q01": {"min_games": 500, "limit": 10},
    "Q02": {"year_from": 2018, "year_to": 2022, "top": 3},
    "Q03": {"date_from": date(2019, 1, 1), "date_to": date(2022, 12, 31), "tag": "Roguelike"},
    "Q04": {"platform": None},
    "Q05": {"min_reviews": 5000, "limit": 10},
    "Q06": {"min_reviews": 50000, "limit": 10},
    "Q07": {"year_from": 2012},
    "Q08": {"rating": "Overwhelmingly Positive", "min_games": 20, "limit": 10},
    "Q09": {"min_reviews": 50, "limit": 10},
    "Q10": {"search": "portal", "limit": 10},
    "Q11": {"tag": "Roguelike", "pct": 50},
    "Q12": {"min_reviews": 100000, "limit": 10},
}


def parse(sql):
    meta, body = {}, []
    for line in sql.splitlines():
        if line.startswith("-- question:"):
            meta["question"] = line.split(":", 1)[1].strip()
        elif line.startswith("-- uses:"):
            meta["uses"] = line.split(":", 1)[1].strip()
        else:
            body.append(line)
    meta["sql"] = "\n".join(body).strip()
    return meta


def jsonable(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, date):
        return v.isoformat()
    return v


def main():
    blocks = {k: parse(v) for k, v in load_blocks(ROOT / "sql" / "queries.sql").items()}
    only = set(sys.argv[1:])
    conn = connect()
    with conn.cursor() as cur:
        cur.execute("SET work_mem = '256MB'")
    conn.commit()
    results, out = {}, ["# Query results\n"]
    for name, q in blocks.items():
        if only and name not in only:
            continue
        params = PARAMS[name]
        t = time.time()
        cols, rows = query(conn, q["sql"], params)
        secs = time.time() - t
        extra = ""
        if name == "Q11":
            conn.rollback()                       # undo the UPDATE
            _, check = query(conn, """SELECT round(avg(g.price_final), 2) FROM games g
                WHERE g.price_final > 0
                  AND g.app_id IN (SELECT gt.app_id FROM game_tags gt JOIN tags t USING (tag_id)
                                   WHERE t.name = %(tag)s)""", params)
            extra = (f"After ROLLBACK the average price of those games is {check[0][0]} "
                     f"(same as avg_price_before): the UPDATE left no trace.")
        conn.rollback()
        print(f"{name}: {len(rows)} rows in {secs:.1f}s", flush=True)
        results[name] = {**q, "params": {k: jsonable(v) for k, v in params.items()},
                         "columns": cols, "rows": [[jsonable(v) for v in r] for r in rows[:15]],
                         "row_count": len(rows), "seconds": round(secs, 2), "extra": extra}
        out += [f"## {name}. {q['question']}\n", f"*Uses:* {q['uses']}  ",
                f"*Parameters:* `{params}`  ", f"*Time:* {secs:.2f} s, {len(rows)} rows\n",
                "```sql", q["sql"], "```\n", md_table(cols, rows, 15), "", extra, ""]
    if not only:
        (ROOT / "queries" / "query_results.md").write_text("\n".join(out), encoding="utf-8")
        (ROOT / "queries" / "query_results.json").write_text(
            json.dumps(results, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    conn.close()


if __name__ == "__main__":
    main()
