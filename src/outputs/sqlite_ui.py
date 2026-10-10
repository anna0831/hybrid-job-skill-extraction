"""Streamlit long preview. All bulk work stays in the offline CLI."""
import os
from pathlib import Path
import sqlite3

import pandas as pd
import streamlit as st

from src.outputs.sqlite_preview import database_version, fetch_job, fetch_page


@st.cache_data(ttl=60, max_entries=32)
def cached_page(version, cursor, filters):
    return fetch_page(version[0], cursor=cursor, filters=filters)


@st.cache_data(ttl=60, max_entries=16)
def cached_job(version, job_id, month):
    return fetch_job(version[0], job_id, month)


def render_sqlite_preview():
    st.subheader("SQLite 技能明細查核（Long format）")
    st.caption("每頁 100 筆；選擇職缺後再載入原文。技能名稱空白的紀錄仍會顯示。")
    path = Path(os.environ.get("SKILL_DB_PATH", "skills_taichung_202609.db")).expanduser()
    if not path.is_file():
        st.info("尚未設定可讀取的資料庫。請在本機啟動時設定 SKILL_DB_PATH，指向你的 .db 檔案。")
        st.code('SKILL_DB_PATH="/完整路徑/skills_taichung_202609.db" .venv/bin/python -m streamlit run sqlite_app.py', language="bash")
        return
    try:
        version = database_version(path)
        with st.form("sqlite_filters"):
            a, b, c = st.columns(3)
            job_id = a.text_input("職缺 ID")
            month = b.text_input("資料月份，例如 202609")
            skill_id = c.text_input("技能 ID")
            a, b, c = st.columns(3)
            skill_text = a.text_input("技能中文名稱包含")
            title_text = b.text_input("職稱包含（僅供找案例）")
            category = c.text_input("原始分類（完整名稱）")
            a, b = st.columns(2)
            source = a.text_input("擷取來源（完整名稱）")
            group10 = b.text_input("十大分類（完整名稱）")
            empty_name = st.checkbox("只看中文名稱為空字串的技能明細")
            no_detail = st.checkbox("只看沒有技能明細的職缺快照")
            submitted = st.form_submit_button("套用篩選")
        if submitted:
            st.session_state["sqlite_applied_filters"] = {
                "ID": job_id, "資料月份": month, "SKILL_ID": skill_id, "skill_text": skill_text,
                "title_text": title_text, "category": category, "MATCHED_FROM": source,
                "Skill_group10": group10, "empty_name": empty_name, "no_detail": no_detail,
            }
        filters = st.session_state.get("sqlite_applied_filters", {})
        signature = (version, tuple(sorted(filters.items())))
        position = st.session_state.get("sqlite_position")
        if position is None or position["signature"] != signature or submitted:
            position = {"signature": signature, "history": [None], "index": 0}
            st.session_state["sqlite_position"] = position
        cursor = position["history"][position["index"]]
        rows, next_cursor = cached_page(version, cursor, filters)
        st.caption(f"第 {position['index'] + 1} 頁 · 本頁 {len(rows)} 筆。沒有明細不等於已確認漏抓；請核對原文與擷取執行範圍。")
        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df, hide_index=True, use_container_width=True)
            st.download_button("下載本頁 CSV", df.to_csv(index=False).encode("utf-8-sig"),
                               "skill_long_page.csv", "text/csv")
        a, b = st.columns(2)
        if a.button("上一頁", disabled=position["index"] == 0):
            position["index"] -= 1
            st.rerun()
        if b.button("下一頁", disabled=next_cursor is None):
            position["history"] = position["history"][:position["index"] + 1] + [next_cursor]
            position["index"] += 1
            st.rerun()
        if rows:
            snapshots = list(dict.fromkeys((r["ID"], r["資料月份"]) for r in rows))
            selection = st.selectbox("選擇本頁職缺以檢視原文", snapshots,
                                     format_func=lambda key: f"{key[0]} / {key[1]}")
            if st.button("載入職缺原文"):
                job = cached_job(version, *selection)
                if job:
                    st.write(f"**{job.get('104職位名稱', '')}** · {selection[0]} / {selection[1]}")
                    for field in ("職位描述", "工作技能", "電腦工具"):
                        st.markdown(f"**{field}**")
                        st.text(job.get(field) if job.get(field) is not None else "（NULL：來源未提供）")
                else:
                    st.warning("找不到此職缺快照，請重新套用篩選。")
    except (OSError, ValueError, sqlite3.Error) as exc:
        st.error(f"資料庫查詢失敗：{exc}")
