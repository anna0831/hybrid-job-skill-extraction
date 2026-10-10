import json
from pathlib import Path
import sqlite3

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.outputs.sqlite_store import import_source, initialize, write_long_rows, report
from src.outputs.sqlite_preview import connect_readonly, fetch_job, fetch_page


def job(jid="00123", month="202609", **extras):
    return {"ID": jid, "資料月份": month, "104職位名稱": "人工測試職缺",
            "104職位名稱碼": "009988", "職位描述": '引號"與換行\n原文', **extras}


def source(tmp_path, rows, name="source.parquet"):
    path = tmp_path / name
    pq.write_table(pa.Table.from_pylist(rows), path, row_group_size=2)
    return path


def test_empty_skill_source_rows_and_duplicates_are_not_dropped(tmp_path):
    rows = [job(SKILL_ID=None, SKILL_NAME_ZH=None, Category_Name=None, IS_SOFTWARE=None),
            job(SKILL_ID="", SKILL_NAME_ZH="", Category_Name="", IS_SOFTWARE=False)]
    rows.append(dict(rows[1]))
    db = tmp_path / "test.db"
    result = import_source(source(tmp_path, rows), db, batch_size=1)
    assert result["source_rows"] == result["skill_detail_rows"] == 3
    assert result["null_skill_names"] == 1 and result["empty_skill_names"] == 2
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT SKILL_ID,Skill_Name_ZH,category,IS_SOFTWARE FROM skill_records ORDER BY record_id").fetchall() == [
            (None, None, None, None), ("", "", "", 0), ("", "", "", 0)]
        saved = [json.loads(r[0]) for r in conn.execute("SELECT source_payload FROM skill_records ORDER BY record_id")]
        assert saved == rows
        assert conn.execute("SELECT source_row FROM skill_records").fetchall() == [(1,), (2,), (3,)]
    assert fetch_job(db, "00123", "202609")["104職位名稱碼"] == "009988"


def test_blank_name_with_valid_id_is_a_detail_row(tmp_path):
    rows = [job(SKILL_ID="SAMPLE_SKILL_01", SKILL_NAME_ZH="", Category_Name="Sample category")]
    result = import_source(source(tmp_path, rows), tmp_path / "test.db")
    assert result["skill_detail_rows"] == 1
    assert result["distinct_nonempty_skill_ids"] == 1
    assert result["distinct_nonempty_skill_names"] == 0


def test_raw_job_backfill_is_snapshot_aware_and_does_not_make_skills(tmp_path):
    db = tmp_path / "test.db"
    import_source(source(tmp_path, [job(SKILL_ID="A", SKILL_NAME_ZH="技能")]), db)
    raw = [job(), job(month="202610"), job(jid="ZERO")]
    result = import_source(source(tmp_path, raw, "raw.parquet"), db, mode="raw-jobs")
    assert result["job_snapshots"] == 3
    assert result["skill_detail_rows"] == 1
    assert result["jobs_without_detail_rows"] == 2
    assert result["view_rows"] == 3
    assert result["raw_source_job_snapshots"] == 3 and result["jobs_not_in_raw_sources"] == 0
    rows, _ = fetch_page(db, filters={"no_detail": True})
    assert {(r["ID"], r["資料月份"]) for r in rows} == {("00123", "202610"), ("ZERO", "202609")}
    assert all(r["record_id"] is None for r in rows)
    assert "not proven extraction failures" in result["scope"]


def test_conflicts_do_not_modify_existing_target(tmp_path):
    db = tmp_path / "test.db"
    import_source(source(tmp_path, [job(SKILL_ID="A")]), db)
    before = db.read_bytes()
    bad = source(tmp_path, [job(職位描述="不同原文")], "raw.parquet")
    with pytest.raises(ValueError, match="Conflicting job snapshot"):
        import_source(bad, db, mode="raw-jobs")
    assert db.read_bytes() == before
    with pytest.raises(FileExistsError):
        import_source(bad, db)


def test_parquet_uses_batches_without_read_table(tmp_path, monkeypatch):
    path = source(tmp_path, [job(str(i), SKILL_ID="A") for i in range(7)])
    def forbidden(*args, **kwargs):
        raise AssertionError("Whole-file read is forbidden")
    monkeypatch.setattr(pq, "read_table", forbidden)
    assert import_source(path, tmp_path / "test.db", batch_size=2)["source_rows"] == 7


def test_100_row_keyset_pages_preserve_repeated_rows_and_null_records(tmp_path):
    db = tmp_path / "test.db"
    rows = [job("ONE", SKILL_ID=str(i), SKILL_NAME_ZH="技能") for i in range(205)]
    import_source(source(tmp_path, rows), db)
    import_source(source(tmp_path, [job("ZERO")], "raw.parquet"), db, mode="raw-jobs")
    pages, cursor = [], None
    while True:
        page, cursor = fetch_page(db, cursor=cursor)
        assert len(page) <= 100
        assert all("職位描述" not in r and "工作技能" not in r for r in page)
        pages.append(page)
        if cursor is None:
            break
    assert [len(p) for p in pages] == [100, 100, 6]
    all_rows = sum(pages, [])
    assert len({(r["ID"], r["資料月份"], r["record_id"]) for r in all_rows}) == 206
    assert all_rows[-1]["record_id"] is None
    assert fetch_job(db, "ONE", "202609")["職位描述"] == rows[0]["職位描述"]


def test_filters_are_parameterized_and_connections_are_readonly(tmp_path):
    db = tmp_path / "test.db"
    import_source(source(tmp_path, [job(SKILL_ID="S", SKILL_NAME_ZH="", Category_Name="Sample")]), db)
    assert fetch_page(db, filters={"ID": "' OR 1=1 --"})[0] == []
    assert len(fetch_page(db, filters={"empty_name": True, "SKILL_ID": "S"})[0]) == 1
    conn = connect_readonly(db)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM jobs")
    finally:
        conn.close()


def test_report_distinguishes_rows_ids_names_and_does_not_infer_categories():
    conn = sqlite3.connect(":memory:")
    initialize(conn)
    write_long_rows(conn, [job(SKILL_ID="A", SKILL_NAME_ZH="同名", Category_Name="同分類"),
                          job(SKILL_ID="B", SKILL_NAME_ZH="同名", Category_Name="同分類"),
                          job(SKILL_ID="B", SKILL_NAME_ZH="同名", Category_Name="同分類")])
    result = report(conn)
    assert (result["skill_detail_rows"], result["distinct_nonempty_skill_ids"], result["distinct_nonempty_skill_names"]) == (3, 2, 1)
    assert "original jobs absent" in result["scope"]
    conn.close()


def test_existing_db_without_new_optional_skill_columns_can_be_backfilled(tmp_path):
    db = tmp_path / "legacy.db"
    import_source(source(tmp_path, [job(SKILL_ID="S", SKILL_NAME_ZH="技能")]), db)
    with sqlite3.connect(db) as conn:
        conn.execute("DROP VIEW v_skill_long")
        for c in ("MATCHED_KEYWORD", "START_POS", "END_POS", "source_payload", "source_row"):
            conn.execute(f'ALTER TABLE skill_records DROP COLUMN "{c}"')
    result = import_source(source(tmp_path, [job("ZERO")], "raw.parquet"), db, mode="raw-jobs")
    assert result["skill_detail_rows"] == 1 and result["jobs_without_detail_rows"] == 1
    assert len(fetch_page(db)[0]) == 2


def test_missing_id_or_month_is_rejected_and_fallback_does_not_override(tmp_path):
    with pytest.raises(ValueError, match="ID and 資料月份"):
        import_source(source(tmp_path, [{"ID": "J"}]), tmp_path / "test.db")
    db = tmp_path / "test.db"
    import_source(source(tmp_path, [{"ID": "J"}]), db, month="202609")
    assert fetch_job(db, "J", "202609") is not None
    other = tmp_path / "other.db"
    import_source(source(tmp_path, [job(month="202610")]), other, month="202609")
    assert fetch_job(other, "00123", "202610") is not None


def test_streamlit_only_fetches_original_text_after_button_click(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    import src.outputs.sqlite_ui as ui
    db = tmp_path / "test.db"
    import_source(source(tmp_path, [job(SKILL_ID="A")]), db)
    monkeypatch.setenv("SKILL_DB_PATH", str(db))
    ui.cached_page.clear()
    ui.cached_job.clear()
    calls = []
    original = ui.fetch_job
    def counted(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)
    monkeypatch.setattr(ui, "fetch_job", counted)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "sqlite_app.py").run(timeout=15)
    assert not app.exception and not app.error
    assert len(app.dataframe[0].value) == 1
    assert calls == []
    [b for b in app.button if b.label == "載入職缺原文"][0].click().run()
    assert not app.exception and not app.error
    assert len(calls) == 1
    assert any('引號"與換行' in t.value for t in app.text)


def test_streamlit_next_previous_and_filter_reset(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    import src.outputs.sqlite_ui as ui
    db = tmp_path / "paging.db"
    import_source(source(tmp_path, [job(str(i).zfill(3), SKILL_ID="A") for i in range(105)]), db)
    monkeypatch.setenv("SKILL_DB_PATH", str(db))
    ui.cached_page.clear()
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "sqlite_app.py").run(timeout=15)
    assert len(app.dataframe[0].value) == 100 and not app.error
    [b for b in app.button if b.label == "下一頁"][0].click().run()
    assert len(app.dataframe[0].value) == 5 and not app.error
    [b for b in app.button if b.label == "上一頁"][0].click().run()
    assert len(app.dataframe[0].value) == 100
    [t for t in app.text_input if t.label == "職缺 ID"][0].set_value("104")
    [b for b in app.button if b.label == "套用篩選"][0].click().run()
    assert len(app.dataframe[0].value) == 1
    assert app.dataframe[0].value.iloc[0]["ID"] == "104"
    assert app.session_state["sqlite_position"]["index"] == 0
