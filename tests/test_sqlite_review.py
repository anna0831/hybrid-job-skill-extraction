import csv
import sqlite3

from scripts.export_skill_review import export_review
from src.outputs.sqlite_store import initialize, put_job, write_long_rows


def test_review_sampling_is_reproducible_and_keeps_empty_names_and_raw_metadata(tmp_path):
    db = tmp_path / "test.db"
    with sqlite3.connect(db) as conn:
        initialize(conn)
        for i in range(10):
            row = {"ID": str(i), "資料月份": "202609", "104職位名稱": "餐廳工作人員", "職位描述": "人工製作測試原文"}
            write_long_rows(conn, [dict(row, SKILL_ID="SAMPLE_SKILL", SKILL_NAME_ZH="")])
        put_job(conn, {"ID": "NO_DETAIL", "資料月份": "202609", "104職位名稱": "餐廳工作人員"})
        conn.execute("""INSERT INTO raw_job_sources(ID,資料月份,source_file,source_row,source_payload)
                      VALUES ('NO_DETAIL','202609','synthetic',1,'{"coIndustry":"人工測試產業"}')""")
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    assert export_review(db, a, "餐飲", limit=5)["exported_job_snapshots"] == 5
    export_review(db, b, "餐飲", limit=5)
    assert a.read_bytes() == b.read_bytes()
    out = tmp_path / "no_detail.csv"
    assert export_review(db, out, "餐飲", no_detail=True)["exported_job_snapshots"] == 1
    with out.open(encoding="utf-8-sig", newline="") as f:
        row = next(csv.DictReader(f))
    assert row["industry_confirmed"] == "" and row["sampling_basis"] == "job_title_proxy"
    assert row["extracted_skills_json"] == "[]"
    assert "coIndustry" in row["original_job_metadata_json"]
