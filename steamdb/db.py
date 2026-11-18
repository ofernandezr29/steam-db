"""Shared helpers: database connection and named SQL blocks.

SQL files are split into blocks that start with a line '-- name: <title>'.
Python only sends a block (with bound parameters) and returns the rows; it never
filters, joins or aggregates them.
"""
import os
import re
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parents[1]


def connect(**kw):
    return psycopg2.connect(dbname=os.environ.get("PGDATABASE", "steam"),
                            host=os.environ.get("PGHOST", "localhost"),
                            port=os.environ.get("PGPORT", "5432"),
                            user=os.environ.get("PGUSER", "postgres"),
                            password=os.environ.get("PGPASSWORD"),
                            application_name="steam-db", **kw)


def load_blocks(path):
    """Return {name: sql} for every '-- name:' block of a .sql file, in order."""
    text = Path(path).read_text(encoding="utf-8")
    blocks = {}
    for part in re.split(r"^-- name: ", text, flags=re.M)[1:]:
        name, _, sql = part.partition("\n")
        blocks[name.strip()] = sql.strip()
    return blocks


def query(conn, sql, params=None):
    """Run one statement and return (column names, rows)."""
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [d.name for d in cur.description], cur.fetchall()


def md_table(cols, rows, limit=None):
    def fmt(v):
        if isinstance(v, int) and not isinstance(v, bool):
            return f"{v:,}"
        return "NULL" if v is None else str(v).replace("|", "\\|").replace("\n", " ")
    rows = rows[:limit] if limit else rows
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join(fmt(v) for v in r) + " |" for r in rows]
    return "\n".join(out)
