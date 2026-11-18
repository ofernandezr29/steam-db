#!/usr/bin/env bash
# Live rollback demo (~12 s) on an empty copy of the schema, so the real database is not touched.
set -euo pipefail
cd "$(dirname "$0")/.."
export PGHOST=${PGHOST:-localhost} PGUSER=${PGUSER:-postgres}
psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = 'steam_demo'" | grep -q 1 \
    || psql -d postgres -qc "CREATE DATABASE steam_demo"
PGDATABASE=steam_demo psql -q -f sql/schema.sql
PGDATABASE=steam_demo .venv/bin/python etl/load.py --inject-error || true
