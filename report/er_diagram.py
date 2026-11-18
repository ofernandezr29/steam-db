"""Draw the ER diagram (course notation: one box per table, PK/FK marked,
1 / N on each relationship, row count under the box) with Graphviz.

Row counts are read from the database with SQL.  Output: report/build/er.svg
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from steamdb.db import connect  # noqa: E402

OUT = Path(__file__).resolve().parent / "build"

TABLES = {
    "ratings": ["rating_id (PK)", "label (UQ)", "rank_order (UQ)"],
    "games": ["app_id (PK)", "title", "date_release", "rating_id (FK)", "positive_ratio",
              "user_reviews", "price_final", "price_original", "discount", "description"],
    "platforms": ["platform_id (PK)", "name (UQ)"],
    "game_platforms": ["app_id (PK, FK)", "platform_id (PK, FK)"],
    "tags": ["tag_id (PK)", "name (UQ)"],
    "game_tags": ["app_id (PK, FK)", "tag_id (PK, FK)", "tag_rank"],
    "users": ["user_id (PK)", "products"],
    "recommendations": ["review_id (PK)", "app_id (FK)", "user_id (FK)", "review_date",
                        "is_recommended", "hours", "helpful", "funny"],
}
# (one side, many side)
RELS = [("ratings", "games"), ("games", "game_platforms"), ("platforms", "game_platforms"),
        ("games", "game_tags"), ("tags", "game_tags"), ("games", "recommendations"),
        ("users", "recommendations")]


LIGHT = dict(bg="white", edge="#4a5568", label="#1a202c", border="#a0aec0", head="#4a5568",
             head_fg="white", body="#edf2f7", body_fg="#2d3748", foot_bg="white", foot_fg="#2d3748")
# Dark palette used by the presentation
DARK = dict(bg="transparent", edge="#66c0f4", label="#66c0f4", border="#3d6a8a", head="#2a475e",
            head_fg="white", body="#16202d", body_fg="#c7d5e0", foot_bg="#1b2838", foot_fg="#66c0f4")


def row_counts():
    conn = connect()
    counts = {}
    with conn.cursor() as cur:
        for t in TABLES:
            cur.execute(f"SELECT count(*) FROM {t}")
            counts[t] = cur.fetchone()[0]
    conn.close()
    return counts


def make_dot(counts, p=LIGHT):
    lines = ['graph ER {', f'graph [rankdir=LR, nodesep=0.5, ranksep=0.9, fontname="Helvetica", bgcolor="{p["bg"]}"];',
             'node [shape=plain, fontname="Helvetica"];',
             f'edge [fontname="Helvetica-Bold", fontsize=11, color="{p["edge"]}", fontcolor="{p["label"]}", penwidth=1.3];']
    for t, cols in TABLES.items():
        rows = "".join(f'<TR><TD ALIGN="LEFT" BALIGN="LEFT"><FONT FACE="Courier" POINT-SIZE="11" '
                       f'COLOR="{p["body_fg"]}">{c}</FONT></TD></TR>' for c in cols)
        lines.append(
            f'{t} [label=<<TABLE BORDER="1" COLOR="{p["border"]}" CELLBORDER="0" CELLSPACING="0" CELLPADDING="5">'
            f'<TR><TD BGCOLOR="{p["head"]}"><FONT COLOR="{p["head_fg"]}" POINT-SIZE="13"><B>{t}</B></FONT></TD></TR>'
            f'<TR><TD BGCOLOR="{p["body"]}"><TABLE BORDER="0" CELLSPACING="0" CELLPADDING="1">{rows}</TABLE></TD></TR>'
            f'<TR><TD BGCOLOR="{p["foot_bg"]}"><FONT POINT-SIZE="11" COLOR="{p["foot_fg"]}"><B>{counts[t]:,} rows</B></FONT></TD></TR>'
            f'</TABLE>>];')
    for one, many in RELS:
        lines.append(f'{one} -- {many} [taillabel=" 1 ", headlabel=" N ", labeldistance=1.6];')
    lines.append('}')
    return "\n".join(lines)


def render(dot, out_dir, name, fmts=("svg", "png")):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{name}.dot").write_text(dot)
    for fmt in fmts:
        subprocess.run(["dot", f"-T{fmt}", "-Gdpi=160", "-o", out_dir / f"{name}.{fmt}",
                        out_dir / f"{name}.dot"], check=True)
    (out_dir / f"{name}.dot").unlink()


def main():
    render(make_dot(row_counts()), OUT, "er")
    print("wrote", OUT / "er.svg")


if __name__ == "__main__":
    main()
