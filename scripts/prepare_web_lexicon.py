#!/usr/bin/env python3
"""
將 11/11 正式研究版基底詞庫與十大分類詞庫轉換為 Vercel Web API 使用的唯讀壓縮 JSON (.json.gz)。

預設尋找：
- 基底詞庫：詞庫skill_lexicon_v13_20261111g.xlsx
- 十大分類：詞庫skill_lexicon_v13_Chen_grouped_11_2026c.xlsx

不會靜默以舊版或迷你詞庫代替 11/11 正式檔案；若找不到正式檔案將明確報錯退出。
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import openpyxl

DEFAULT_BASE_FILENAME = "詞庫skill_lexicon_v13_20261111g.xlsx"
DEFAULT_GROUPED_FILENAME = "詞庫skill_lexicon_v13_Chen_grouped_11_2026c.xlsx"
DEFAULT_ONEDRIVE_LEXICON_DIR = "/Users/anna/Library/CloudStorage/OneDrive-個人/ChenRA/AI_Job_project/詞庫"
DEFAULT_OUTPUT_PATH = Path("web_data/lexicon_bundle.json.gz")

EXPECTED_GROUP10 = {
    1: "認知、分析與創新技能",
    2: "溝通、語言與人際技能",
    3: "個人特質、自我管理與身體能力",
    4: "財務、會計與經濟技能",
    5: "管理、商業、法遵與治理技能",
    6: "行政與一般數位技能",
    7: "營運、技職與第一線服務技能",
    8: "資訊科技、軟體、資料與AI技能",
    9: "醫療、健康與照護技能",
    10: "工程、自然科學、設計、環境與能源技能",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _clean_str(val: Any) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    return "" if s.lower() == "nan" else s


def _clean_int(val: Any) -> Optional[int]:
    s = _clean_str(val)
    if not s:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def _parse_group10_code(val: Any) -> Optional[int]:
    s = _clean_str(val).upper()
    if not s:
        return None
    if s.startswith("G") and s[1:].isdigit():
        return int(s[1:])
    return _clean_int(s)


def _read_excel_rows(path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        headers_raw = next(rows_iter)
    except StopIteration:
        wb.close()
        return [], []
    headers = [_clean_str(h) for h in headers_raw]
    records: list[dict[str, Any]] = []
    for row in rows_iter:
        if row is None or all(v is None or str(v).strip() == "" for v in row):
            continue
        rec = {headers[i]: (row[i] if i < len(row) else None) for i in range(len(headers)) if headers[i]}
        records.append(rec)
    wb.close()
    return headers, records


def resolve_input_file(explicit: Optional[str], filename: str, search_dirs: list[Path]) -> Path:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.is_file():
            raise FileNotFoundError(f"找不到指定的詞庫檔案：{p}")
        return p
    for d in search_dirs:
        cand = d / filename
        if cand.is_file():
            return cand.resolve()
    searched = ", ".join(str(d / filename) for d in search_dirs)
    raise FileNotFoundError(
        f"找不到 11/11 正式詞庫檔案「{filename}」。已搜尋路徑：{searched}\n"
        "請使用 --base-lexicon / --grouped-lexicon 明確指定檔案路徑。"
    )


def build_bundle(base_path: Path, grouped_path: Path) -> Dict[str, Any]:
    base_headers, base_rows = _read_excel_rows(base_path)
    required_base = {"Category_Name", "Subcategory_Name", "Skill_Name", "Skill_Name_ZH", "Skill_Type", "Keywords"}
    missing_base = sorted(required_base - set(base_headers))
    if missing_base:
        raise ValueError(f"基底詞庫缺少必要欄位：{missing_base}")

    grouped_headers, grouped_rows = _read_excel_rows(grouped_path)
    required_grouped = {"Skill_ID", "Skill_Name", "Skill_group10_code", "Skill_group10", "Grouping_rule"}
    missing_grouped = sorted(required_grouped - set(grouped_headers))
    if missing_grouped:
        raise ValueError(f"十大分類詞庫缺少必要欄位：{missing_grouped}")

    id_lookup: Dict[str, Dict[str, Any]] = {}
    name_lookup: Dict[str, Dict[str, Any]] = {}
    for r in grouped_rows:
        sid = _clean_str(r.get("Skill_ID"))
        sname = _clean_str(r.get("Skill_Name"))
        g_code = _parse_group10_code(r.get("Skill_group10_code"))
        g_name = _clean_str(r.get("Skill_group10"))
        if g_code in EXPECTED_GROUP10 and not g_name:
            g_name = EXPECTED_GROUP10[g_code]
        meta = {
            "Skill_group10_code": g_code,
            "Skill_group10": g_name,
            "Grouping_rule": _clean_str(r.get("Grouping_rule")),
            "Grouping_status": _clean_str(r.get("Grouping_status")) or ("已對應" if g_code is not None else "待分類"),
            "Allowed_group_codes": _clean_str(r.get("Allowed_group_codes")),
            "Ambiguity_note": _clean_str(r.get("Ambiguity_note")),
        }
        if sid:
            id_lookup[sid] = meta
        if sname:
            name_lookup[sname] = meta

    skills: list[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    ai_count = 0

    for row in base_rows:
        sid = _clean_str(row.get("Skill_ID"))
        sname = _clean_str(row.get("Skill_Name"))
        sname_zh = _clean_str(row.get("Skill_Name_ZH"))
        keywords = _clean_str(row.get("Keywords"))
        if not keywords and not sname and not sname_zh:
            continue

        if sid:
            if sid in seen_ids:
                raise ValueError(f"基底詞庫發現重複 Skill_ID：{sid}")
            seen_ids.add(sid)

        meta = id_lookup.get(sid) if sid else name_lookup.get(sname)
        if not meta and sname:
            meta = name_lookup.get(sname)

        g_code = meta["Skill_group10_code"] if meta else None
        g_name = meta["Skill_group10"] if meta else ""
        g_rule = meta["Grouping_rule"] if meta else ""
        g_status = meta["Grouping_status"] if meta else "待分類"
        allowed_codes = meta["Allowed_group_codes"] if meta else ""
        ambiguity_note = meta["Ambiguity_note"] if meta else ""

        is_ai = _clean_str(row.get("Is_AI_Skill")).upper() in {"Y", "YES", "1", "TRUE"}
        if is_ai:
            ai_count += 1

        skills.append({
            "SKILL_ID": sid,
            "SKILL_NAME": sname,
            "SKILL_NAME_ZH": sname_zh,
            "SKILL_TYPE": _clean_str(row.get("Skill_Type")),
            "Category_Name": _clean_str(row.get("Category_Name")),
            "Subcategory_Name": _clean_str(row.get("Subcategory_Name")),
            "Category_Code": _clean_int(row.get("Category_Code")),
            "Subcategory_Code": _clean_int(row.get("Subcategory_Code")),
            "Keywords": keywords,
            "Allow_Bare_2Char_Keywords": _clean_str(row.get("Allow_Bare_2Char_Keywords")),
            "Case_Sensitive_Keywords": _clean_str(row.get("Case_Sensitive_Keywords")),
            "Structured_Field_Exact_Tags": _clean_str(row.get("Structured_Field_Exact_Tags")),
            "Is_AI_Skill": is_ai,
            "Skill_group10_code": g_code,
            "Skill_group10": g_name or "待分類",
            "Grouping_rule": g_rule,
            "Grouping_status": g_status,
            "Allowed_group_codes": allowed_codes,
            "Ambiguity_note": ambiguity_note,
        })

    return {
        "schema_version": "1111_web_bundle_v1",
        "metadata": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "base_lexicon_filename": base_path.name,
            "base_lexicon_sha256": sha256_file(base_path),
            "grouped_lexicon_filename": grouped_path.name,
            "grouped_lexicon_sha256": sha256_file(grouped_path),
            "skill_count": len(skills),
            "ai_skill_count": ai_count,
            "group10_definitions": {str(k): v for k, v in EXPECTED_GROUP10.items()},
        },
        "skills": skills,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="轉換 11/11 正式 Excel 詞庫為 Web 專用壓縮 JSON")
    parser.add_argument("--base-lexicon", default=None, help=f"基底詞庫路徑（預設尋找 {DEFAULT_BASE_FILENAME}）")
    parser.add_argument("--grouped-lexicon", default=None, help=f"十大分類詞庫路徑（預設尋找 {DEFAULT_GROUPED_FILENAME}）")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="輸出 .json.gz 路徑")
    args = parser.parse_args()

    search_dirs = [Path.cwd(), Path.cwd() / "lexicon", Path(DEFAULT_ONEDRIVE_LEXICON_DIR)]
    try:
        base_path = resolve_input_file(args.base_lexicon, DEFAULT_BASE_FILENAME, search_dirs)
        grouped_path = resolve_input_file(args.grouped_lexicon, DEFAULT_GROUPED_FILENAME, search_dirs)
    except FileNotFoundError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1

    bundle = build_bundle(base_path, grouped_path)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    raw_bytes = json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    if out_path.suffix == ".gz":
        with gzip.open(out_path, "wb", compresslevel=6) as f:
            f.write(raw_bytes)
    else:
        out_path.write_bytes(raw_bytes)

    meta = bundle["metadata"]
    print(f"✅ 已產生 Web 詞庫：{out_path} ({out_path.stat().st_size / 1024:.1f} KB)")
    print(f"   基底詞庫：{meta['base_lexicon_filename']} (SHA256: {meta['base_lexicon_sha256'][:12]}...)")
    print(f"   十大分類：{meta['grouped_lexicon_filename']} (SHA256: {meta['grouped_lexicon_sha256'][:12]}...)")
    print(f"   技能總數：{meta['skill_count']:,}（AI 技能：{meta['ai_skill_count']:,}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
