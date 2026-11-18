"""Copy the raw files, untouched, into text-only staging tables (schema raw).

This is only used for the data profile: every column is TEXT so nothing is
rejected or converted, and every profiling number is then computed in SQL
(profiling/profile.sql). Python does not analyse anything here.
"""
import csv
import io
import os
import sys
import time
from pathlib import Path

import psycopg2

DATA = Path(os.environ.get("STEAM_DATA", Path(__file__).resolve().parents[1] / "data"))

DDL = """
DROP SCHEMA IF EXISTS raw CASCADE;
CREATE SCHEMA raw;
CREATE TABLE raw.games (
    line_no bigint GENERATED ALWAYS AS IDENTITY,
    app_id text, title text, date_release text, win text, mac text, linux text,
    rating text, positive_ratio text, user_reviews text, price_final text,
    price_original text, discount text, steam_deck text);
CREATE TABLE raw.users (
    line_no bigint GENERATED ALWAYS AS IDENTITY,
    user_id text, products text, reviews text);
CREATE TABLE raw.recommendations (
    line_no bigint GENERATED ALWAYS AS IDENTITY,
    app_id text, helpful text, funny text, date text, is_recommended text,
    hours text, user_id text, review_id text);
CREATE TABLE raw.games_metadata (
    line_no bigint GENERATED ALWAYS AS IDENTITY,
    doc jsonb);
"""


def copy_csv(cur, table, path):
    with open(path, newline="", encoding="utf-8") as f:
        header = f.readline().strip()
        cur.copy_expert(f"COPY raw.{table} ({header}) FROM STDIN WITH (FORMAT csv)", f)


class JsonLines(io.RawIOBase):
    """File-like object that turns each JSON line into one CSV row for COPY."""

    def __init__(self, path):
        self.src = open(path, encoding="utf-8")
        self.buf = b""

    def readable(self):
        return True

    def readinto(self, b):
        while len(self.buf) < len(b):
            line = self.src.readline()
            if not line:
                break
            out = io.StringIO()
            csv.writer(out).writerow([line.rstrip("\n")])
            self.buf += out.getvalue().encode()
        n = min(len(b), len(self.buf))
        b[:n] = self.buf[:n]
        self.buf = self.buf[n:]
        return n


def main():
    conn = psycopg2.connect(dbname=os.environ.get("PGDATABASE", "steam"),
                            host=os.environ.get("PGHOST", "localhost"),
                            user=os.environ.get("PGUSER", "postgres"))
    with conn, conn.cursor() as cur:
        cur.execute(DDL)
        for table in ("games", "users", "recommendations"):
            t = time.time()
            copy_csv(cur, table, DATA / f"{table}.csv")
            print(f"raw.{table}: {cur.rowcount:,} rows in {time.time() - t:.0f}s", flush=True)
        t = time.time()
        cur.copy_expert("COPY raw.games_metadata (doc) FROM STDIN WITH (FORMAT csv)",
                        io.BufferedReader(JsonLines(DATA / "games_metadata.json")))
        print(f"raw.games_metadata: {cur.rowcount:,} rows in {time.time() - t:.0f}s")
    conn.close()


if __name__ == "__main__":
    sys.exit(main())
