#!/usr/bin/env bash
# Full pipeline from zero: venv, raw data, database, schema, load, indexes.
# Connection settings come from PGHOST / PGPORT / PGUSER / PGPASSWORD (default localhost / postgres).
set -euo pipefail
cd "$(dirname "$0")/.."
export PGHOST=${PGHOST:-localhost} PGUSER=${PGUSER:-postgres} PGDATABASE=${PGDATABASE:-steam}
[[ -d .venv ]] || { python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt; }
scripts/download_data.sh
psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$PGDATABASE'" | grep -q 1 \
    || psql -d postgres -c "CREATE DATABASE $PGDATABASE"
psql -v ON_ERROR_STOP=1 -q -f sql/schema.sql          # 1. schema first
.venv/bin/python etl/load.py                         # 2. load (one transaction)
.venv/bin/python queries/index_benchmark.py          # 3. indexes + before/after timings
psql -v ON_ERROR_STOP=1 -f sql/verify_constraints.sql   # 4. constraints still there
echo "Done. Start the app with: .venv/bin/streamlit run app/app.py"
