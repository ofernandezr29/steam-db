# Project B · Steam game recommendations in PostgreSQL

Relational database application on real data. Odei Fernández Rodríguez (single-member group).

Dataset: [Game Recommendations on Steam](https://www.kaggle.com/datasets/antonkozyriev/game-recommendations-on-steam)
by Anton Kozyriev, Kaggle, license CC0 1.0. It has four files: 50,872 games, 14.3 M users and 41.2 M reviews.
The raw data is **not** committed. `scripts/download_data.sh` downloads it into `data/`.

Report: [`report/Project_B_Report.pdf`](report/Project_B_Report.pdf) · Slides: **[ofernandezr29.github.io/steam-db](https://ofernandezr29.github.io/steam-db/)** (use ← → and F for full screen; source in [`presentation/index.html`](presentation/index.html))

## Layout

| Path | What it is |
|---|---|
| `scripts/download_data.sh` | Downloads the raw files from Kaggle into `data/` |
| `scripts/setup.sh` | Runs the whole pipeline from zero |
| `profiling/load_raw.py`, `profiling/profile.sql`, `profiling/run_profile.py` | Data profile: raw files go into text-only staging tables, every number comes from SQL. Output in `profile_results.md` |
| `sql/schema.sql` | Physical schema: 8 tables, PK / FK / NOT NULL / UNIQUE / CHECK |
| `etl/load.py` | ETL: one transaction, COPY streaming, cleaning rules counted in `etl/cleaning_log.json`. `--inject-error` shows the rollback |
| `sql/indexes.sql`, `queries/index_benchmark.py` | Secondary indexes and before/after timings |
| `sql/verify_constraints.sql` | Shows every constraint after the load and tries 7 invalid rows |
| `sql/queries.sql`, `queries/run_queries.py` | The 12 SQL queries. Results in `queries/query_results.md` |
| `app/app.py` | Streamlit dashboard: 11 tabs, 13 charts, filters passed as SQL parameters |
| `report/` | ER diagram (`er_diagram.py`), report generator (`build_report.py`), screenshots, PDF |
| `presentation/` | Slide deck (`index.html`, built by `build_presentation.py`) |
| `scripts/rollback_demo.sh` | Live rollback demo on an empty `steam_demo` database (about 12 s) |
| `EFFORT_LOG.md` | Who did what |

## Run

Requires PostgreSQL. The connection is set through `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD` and `PGDATABASE`.
The defaults are `localhost`, `5432`, `postgres`, no password and `steam`.

```bash
scripts/setup.sh                       # venv, download, CREATE DATABASE, schema, load (~9 min), indexes, checks
.venv/bin/streamlit run app/app.py     # dashboard at http://localhost:8501
```

Individual steps:

```bash
psql -h localhost -U postgres -d steam -f sql/schema.sql      # 1. schema first (also empties the tables)
.venv/bin/python etl/load.py --inject-error                   #    rollback demo: fails on purpose, tables stay empty
.venv/bin/python etl/load.py                                  # 2. full load in one transaction
.venv/bin/python queries/index_benchmark.py                   # 3. indexes + timings
psql -h localhost -U postgres -d steam -f sql/verify_constraints.sql   # 4. constraints after loading
.venv/bin/python queries/run_queries.py                       # 5. the 12 queries

# data profile (needs ~4.5 GB more disk for the staging copy; drop it afterwards)
.venv/bin/python profiling/load_raw.py && .venv/bin/python profiling/run_profile.py
psql -h localhost -U postgres -d steam -c "DROP SCHEMA raw CASCADE"

# report (needs: pip install weasyprint)
python report/er_diagram.py && python report/build_report.py
```

The first time the dashboard opens, the heavy queries over all 41 M reviews (Q04, Q09, Q12) take 10–25 s each.
After that their results are cached for one hour.

## Rules followed

- All analysis is done in SQL. Python only reads the raw files and cleans their *format*, sends queries with bound
  parameters and passes the rows to the charts. No pandas, Polars or NumPy.
- The schema is created first and the load only inserts. The whole load is one transaction.
- Missing values stay NULL. Every cleaning rule and the number of rows it affects is documented.
