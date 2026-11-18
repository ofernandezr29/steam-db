"""Measure three queries without and with the secondary indexes of sql/indexes.sql.

Runs each query 3 times with EXPLAIN (ANALYZE) and keeps the best execution time.
Writes queries/index_benchmark.json. Leaves the indexes created.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from steamdb.db import ROOT, connect, load_blocks  # noqa: E402

BENCH = {
    "All reviews of one game (Counter-Strike: Global Offensive), newest first": (
        "SELECT review_date, is_recommended, hours FROM recommendations "
        "WHERE app_id = 730 ORDER BY review_date DESC LIMIT 100", {}),
    "Monthly trend for one tag (Q03, tag 'Roguelike')": (
        load_blocks(ROOT / "sql" / "queries.sql")["Q03"],
        {"date_from": "2019-01-01", "date_to": "2022-12-31", "tag": "Roguelike"}),
    "Title search with review count per game (Q10, 'portal')": (
        load_blocks(ROOT / "sql" / "queries.sql")["Q10"], {"search": "portal", "limit": 10}),
}


def best_ms(cur, sql, params):
    best, plan_top = None, None
    for _ in range(3):
        cur.execute("EXPLAIN (ANALYZE, FORMAT JSON) " + sql, params)
        plan = cur.fetchone()[0][0]
        ms = plan["Execution Time"]
        if best is None or ms < best:
            best, plan_top = ms, plan["Plan"]
    def scans(node, acc):
        if "Scan" in node["Node Type"]:
            acc.append(f'{node["Node Type"]} on {node.get("Relation Name", "?")}'
                       + (f' using {node["Index Name"]}' if "Index Name" in node else ""))
        for child in node.get("Plans", []):
            scans(child, acc)
        return acc
    return round(best, 3), sorted(set(scans(plan_top, [])))


def main():
    idx = load_blocks(ROOT / "sql" / "indexes.sql")
    conn = connect()
    conn.autocommit = True
    cur = conn.cursor()
    out = {}
    for phase in ("drop", "create"):
        cur.execute(idx[phase])
        cur.execute("ANALYZE recommendations")
        for name, (sql, params) in BENCH.items():
            ms, scans = best_ms(cur, sql, params)
            out.setdefault(name, {})["without" if phase == "drop" else "with"] = {
                "ms": ms, "scans": scans}
            print(f"{phase:6} {ms:>10.3f} ms  {name}", flush=True)
    (ROOT / "queries" / "index_benchmark.json").write_text(json.dumps(out, indent=2))
    conn.close()


if __name__ == "__main__":
    main()
