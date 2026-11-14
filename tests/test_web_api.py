"""
Vercel 教授展示版 API 與 11/11 AC+Rules 引擎驗收測試 (tests/test_web_api.py)。

涵蓋 Phase 6 與 Requirement Change (4 工作表 Excel .xlsx) 全部驗收項目：
- Health Check（含詞庫缺失誠實回報與就緒狀態）
- 正常職缺與中英混合 JD 技能擷取
- 福利／ESG／行銷修飾詞誤抓排除
- GCP 多義縮寫領域消歧
- 無技能職缺保留
- G1-G10 分類與「待分類」處理
- 100 筆批次匯出 4 工作表 Excel (.xlsx) 驗證
- 與 104_single_city_merged_20261111.py 核心規則一致性比對
"""

from __future__ import annotations

import asyncio
import gzip
import importlib.util
import io
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import openpyxl
import pytest

from api.index import app
from src.web_adapter import WebSkillEngine, get_web_engine


def _build_test_bundle(path: Path) -> Path:
    """建立涵蓋 11/11 規則測試情境之測試用唯讀詞庫 (.json.gz)。"""
    bundle = {
        "schema_version": "1111_web_bundle_v1",
        "metadata": {
            "base_lexicon_filename": "test_fixture_20261111g.xlsx",
            "base_lexicon_sha256": "fixture_sha256_base",
            "grouped_lexicon_filename": "test_fixture_11_2026c.xlsx",
            "grouped_lexicon_sha256": "fixture_sha256_grouped",
            "skill_count": 10,
            "ai_skill_count": 2,
        },
        "skills": [
            {
                "SKILL_ID": "SK_PY_001",
                "SKILL_NAME": "Python (Programming Language)",
                "SKILL_NAME_ZH": "Python",
                "SKILL_TYPE": "Specialized Skill",
                "Category_Name": "Information Technology",
                "Subcategory_Name": "Programming Languages",
                "Category_Code": 17,
                "Subcategory_Code": 101,
                "Keywords": "Python",
                "Allow_Bare_2Char_Keywords": "",
                "Case_Sensitive_Keywords": "",
                "Structured_Field_Exact_Tags": "",
                "Is_AI_Skill": True,
                "Skill_group10_code": 8,
                "Skill_group10": "資訊科技、軟體、資料與AI技能",
                "Grouping_rule": "exact",
                "Grouping_status": "已對應",
                "Allowed_group_codes": "",
                "Ambiguity_note": "",
            },
            {
                "SKILL_ID": "SK_ML_001",
                "SKILL_NAME": "Machine Learning",
                "SKILL_NAME_ZH": "機器學習",
                "SKILL_TYPE": "Specialized Skill",
                "Category_Name": "Information Technology",
                "Subcategory_Name": "Artificial Intelligence",
                "Category_Code": 17,
                "Subcategory_Code": 102,
                "Keywords": "Machine Learning｜機器學習",
                "Allow_Bare_2Char_Keywords": "",
                "Case_Sensitive_Keywords": "",
                "Structured_Field_Exact_Tags": "",
                "Is_AI_Skill": True,
                "Skill_group10_code": 8,
                "Skill_group10": "資訊科技、軟體、資料與AI技能",
                "Grouping_rule": "exact",
                "Grouping_status": "已對應",
                "Allowed_group_codes": "",
                "Ambiguity_note": "",
            },
            {
                "SKILL_ID": "ESC7869CF7378283E0AA",
                "SKILL_NAME": "Google Cloud Platform",
                "SKILL_NAME_ZH": "Google Cloud Platform (GCP)",
                "SKILL_TYPE": "Specialized Skill",
                "Category_Name": "Information Technology",
                "Subcategory_Name": "Cloud Computing",
                "Category_Code": 17,
                "Subcategory_Code": 103,
                "Keywords": "Google Cloud Platform｜GCP",
                "Allow_Bare_2Char_Keywords": "",
                "Case_Sensitive_Keywords": "GCP",
                "Structured_Field_Exact_Tags": "",
                "Is_AI_Skill": False,
                "Skill_group10_code": 8,
                "Skill_group10": "資訊科技、軟體、資料與AI技能",
                "Grouping_rule": "exact",
                "Grouping_status": "已對應",
                "Allowed_group_codes": "",
                "Ambiguity_note": "",
            },
            {
                "SKILL_ID": "KS124ZQ6RS1V188JSCTX",
                "SKILL_NAME": "Good Clinical Practices",
                "SKILL_NAME_ZH": "優良臨床試驗規範 (GCP)",
                "SKILL_TYPE": "Specialized Skill",
                "Category_Name": "Healthcare",
                "Subcategory_Name": "Clinical Research",
                "Category_Code": 12,
                "Subcategory_Code": 201,
                "Keywords": "Good Clinical Practices｜GCP",
                "Allow_Bare_2Char_Keywords": "",
                "Case_Sensitive_Keywords": "GCP",
                "Structured_Field_Exact_Tags": "",
                "Is_AI_Skill": False,
                "Skill_group10_code": 9,
                "Skill_group10": "醫療、健康與照護技能",
                "Grouping_rule": "exact",
                "Grouping_status": "已對應",
                "Allowed_group_codes": "",
                "Ambiguity_note": "",
            },
            {
                "SKILL_ID": "KS1281Y6QHJ8PQLHTZ6R",
                "SKILL_NAME": "Process Control Engineering",
                "SKILL_NAME_ZH": "工程製程控制",
                "SKILL_TYPE": "Specialized Skill",
                "Category_Name": "Engineering",
                "Subcategory_Name": "Manufacturing",
                "Category_Code": 10,
                "Subcategory_Code": 301,
                "Keywords": "工程製程控制｜製程控制",
                "Allow_Bare_2Char_Keywords": "",
                "Case_Sensitive_Keywords": "",
                "Structured_Field_Exact_Tags": "",
                "Is_AI_Skill": False,
                "Skill_group10_code": 10,
                "Skill_group10": "工程、自然科學、設計、環境與能源技能",
                "Grouping_rule": "1103_meeting",
                "Grouping_status": "已對應",
                "Allowed_group_codes": "G7|G10",
                "Ambiguity_note": "依 2026/11/03 Meeting 決議允許 G7 或 G10，需依職缺脈絡人工確認",
            },
            {
                "SKILL_ID": "ES92A402F893456D877B",
                "SKILL_NAME": "Health Screenings",
                "SKILL_NAME_ZH": "健康檢查",
                "SKILL_TYPE": "Specialized Skill",
                "Category_Name": "Healthcare",
                "Subcategory_Name": "Preventive Care",
                "Category_Code": 12,
                "Subcategory_Code": 202,
                "Keywords": "健康檢查",
                "Allow_Bare_2Char_Keywords": "",
                "Case_Sensitive_Keywords": "",
                "Structured_Field_Exact_Tags": "",
                "Is_AI_Skill": False,
                "Skill_group10_code": 9,
                "Skill_group10": "醫療、健康與照護技能",
                "Grouping_rule": "exact",
                "Grouping_status": "已對應",
                "Allowed_group_codes": "",
                "Ambiguity_note": "",
            },
            {
                "SKILL_ID": "BGS423420828D2785973",
                "SKILL_NAME": "Group Insurance",
                "SKILL_NAME_ZH": "團體保險",
                "SKILL_TYPE": "Specialized Skill",
                "Category_Name": "Finance",
                "Subcategory_Name": "Insurance",
                "Category_Code": 8,
                "Subcategory_Code": 401,
                "Keywords": "團體保險｜勞健保",
                "Allow_Bare_2Char_Keywords": "",
                "Case_Sensitive_Keywords": "",
                "Structured_Field_Exact_Tags": "",
                "Is_AI_Skill": False,
                "Skill_group10_code": 4,
                "Skill_group10": "財務、會計與經濟技能",
                "Grouping_rule": "exact",
                "Grouping_status": "已對應",
                "Allowed_group_codes": "",
                "Ambiguity_note": "",
            },
            {
                "SKILL_ID": "KS1239Z71LLXDMTGRJ5S",
                "SKILL_NAME": "Economic Development",
                "SKILL_NAME_ZH": "經濟發展",
                "SKILL_TYPE": "Specialized Skill",
                "Category_Name": "Economics",
                "Subcategory_Name": "Macroeconomics",
                "Category_Code": 8,
                "Subcategory_Code": 402,
                "Keywords": "經濟發展",
                "Allow_Bare_2Char_Keywords": "",
                "Case_Sensitive_Keywords": "",
                "Structured_Field_Exact_Tags": "",
                "Is_AI_Skill": False,
                "Skill_group10_code": 4,
                "Skill_group10": "財務、會計與經濟技能",
                "Grouping_rule": "exact",
                "Grouping_status": "已對應",
                "Allowed_group_codes": "",
                "Ambiguity_note": "",
            },
            {
                "SKILL_ID": "SK_LINE_001",
                "SKILL_NAME": "LINE",
                "SKILL_NAME_ZH": "LINE 通訊軟體",
                "SKILL_TYPE": "Software",
                "Category_Name": "Administration",
                "Subcategory_Name": "Office Tools",
                "Category_Code": 370,
                "Subcategory_Code": 601,
                "Keywords": "LINE",
                "Allow_Bare_2Char_Keywords": "",
                "Case_Sensitive_Keywords": "LINE",
                "Structured_Field_Exact_Tags": "LINE",
                "Is_AI_Skill": False,
                "Skill_group10_code": 6,
                "Skill_group10": "行政與一般數位技能",
                "Grouping_rule": "exact",
                "Grouping_status": "已對應",
                "Allowed_group_codes": "",
                "Ambiguity_note": "",
            },
            {
                "SKILL_ID": "SK_UNGROUPED_001",
                "SKILL_NAME": "Data Pipeline",
                "SKILL_NAME_ZH": "資料管線",
                "SKILL_TYPE": "Specialized Skill",
                "Category_Name": "Information Technology",
                "Subcategory_Name": "Data Engineering",
                "Category_Code": 17,
                "Subcategory_Code": 105,
                "Keywords": "資料管線｜Data Pipeline｜Data Pipelines",
                "Allow_Bare_2Char_Keywords": "",
                "Case_Sensitive_Keywords": "",
                "Structured_Field_Exact_Tags": "",
                "Is_AI_Skill": False,
                "Skill_group10_code": None,
                "Skill_group10": "",
                "Grouping_rule": "",
                "Grouping_status": "待分類",
                "Allowed_group_codes": "",
                "Ambiguity_note": "",
            },
        ],
    }
    raw = json.dumps(bundle, ensure_ascii=False).encode("utf-8")
    with gzip.open(path, "wb") as f:
        f.write(raw)
    return path


async def _asgi_call(
    method: str,
    path: str,
    json_body: Any = None,
    extra_headers: Optional[List[tuple[bytes, bytes]]] = None,
) -> tuple[int, Dict[str, str], bytes]:
    """直接透過 ASGI 介面呼叫 FastAPI/Starlette App，不依賴 httpx 或外部網路。"""
    body_bytes = json.dumps(json_body, ensure_ascii=False).encode("utf-8") if json_body is not None else b""
    headers = [(b"host", b"testserver")]
    if extra_headers:
        headers.extend(extra_headers)
    if json_body is not None:
        headers.append((b"content-type", b"application/json"))
        headers.append((b"content-length", str(len(body_bytes)).encode("ascii")))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }

    sent_request = False
    status_code = 500
    resp_headers: Dict[str, str] = {}
    resp_chunks: List[bytes] = []

    async def receive():
        nonlocal sent_request
        if not sent_request:
            sent_request = True
            return {"type": "http.request", "body": body_bytes, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        nonlocal status_code, resp_headers
        if message["type"] == "http.response.start":
            status_code = message["status"]
            resp_headers = {k.decode("latin1").lower(): v.decode("latin1") for k, v in message.get("headers", [])}
        elif message["type"] == "http.response.body":
            resp_chunks.append(message.get("body", b""))

    await app(scope, receive, send)
    return status_code, resp_headers, b"".join(resp_chunks)


@pytest.fixture
def loaded_engine(tmp_path: Path):
    bundle_path = _build_test_bundle(tmp_path / "lexicon_bundle.json.gz")
    eng = get_web_engine(bundle_path=str(bundle_path), force_reload=True)
    assert eng.ready is True
    return eng


def test_health_missing_lexicon(tmp_path: Path):
    missing_path = str(tmp_path / "does_not_exist.json.gz")
    get_web_engine(bundle_path=missing_path, force_reload=True)
    status, _, body = asyncio.run(_asgi_call("GET", "/api/health"))
    assert status == 200
    data = json.loads(body.decode("utf-8"))
    assert data["ready"] is False
    assert data["llm_enabled"] is False
    assert data["status"] == "lexicon_missing"


def test_root_html_served(loaded_engine):
    status, headers, body = asyncio.run(_asgi_call("GET", "/"))
    assert status == 200
    assert "text/html" in headers.get("content-type", "")
    html = body.decode("utf-8")
    assert "104 職缺技能擷取研究展示系統" in html
    assert "下載完整分析報告 (.xlsx)" in html


def test_health_ready(loaded_engine):
    status, _, body = asyncio.run(_asgi_call("GET", "/api/health"))
    assert status == 200
    data = json.loads(body.decode("utf-8"))
    assert data["ready"] is True
    assert data["llm_enabled"] is False
    assert data["skill_count"] == 10
    assert data["ai_skill_count"] == 2


def test_extract_bilingual_and_ungrouped(loaded_engine):
    payload = {
        "job_title": "資深資料工程師",
        "job_description": "負責建置 Data Pipelines、Python 自動化與 Machine Learning 模型部署。",
        "job_skills": "資料管線",
        "computer_tools": "Python, LINE",
    }
    status, _, body = asyncio.run(_asgi_call("POST", "/api/extract", payload))
    assert status == 200
    data = json.loads(body.decode("utf-8"))
    ids = {s["SKILL_ID"]: s for s in data["skills"]}
    assert "SK_PY_001" in ids
    assert "SK_ML_001" in ids
    assert "SK_UNGROUPED_001" in ids
    assert "SK_LINE_001" in ids  # 工具欄精確標籤命中
    assert ids["SK_UNGROUPED_001"]["Skill_group10"] == "待分類"
    assert data["stats"]["ai_skill_count"] == 2


def test_welfare_and_esg_exclusion(loaded_engine):
    payload = {
        "job_title": "品牌專員",
        "job_description": (
            "【公司簡介】本公司致力於氣候變遷、生態永續與經濟發展。\n"
            "【員工福利】提供團體保險、勞健保與年度健康檢查。\n"
            "【工作內容】負責產品資料管線整理，且需依 production line 排程回報。"
        ),
        "job_skills": "",
        "computer_tools": "",
    }
    status, _, body = asyncio.run(_asgi_call("POST", "/api/extract", payload))
    assert status == 200
    data = json.loads(body.decode("utf-8"))
    kept_ids = {s["SKILL_ID"] for s in data["skills"]}
    assert "SK_UNGROUPED_001" in kept_ids
    assert "ES92A402F893456D877B" not in kept_ids  # 福利健康檢查排除
    assert "BGS423420828D2785973" not in kept_ids   # 福利團體保險排除
    assert "KS1239Z71LLXDMTGRJ5S" not in kept_ids  # ESG 經濟發展排除
    assert "SK_LINE_001" not in kept_ids           # Case_Sensitive_Keywords 小寫 line 排除
    assert len(data["excluded_candidates"]) >= 3


def test_gcp_disambiguation(loaded_engine):
    cloud_payload = {
        "job_title": "Cloud Engineer",
        "job_description": "負責 GCP、AWS 與 Docker 微服務部署。",
    }
    _, _, b1 = asyncio.run(_asgi_call("POST", "/api/extract", cloud_payload))
    d1 = json.loads(b1.decode("utf-8"))
    ids1 = {s["SKILL_ID"] for s in d1["skills"]}
    assert "ESC7869CF7378283E0AA" in ids1
    assert "KS124ZQ6RS1V188JSCTX" not in ids1

    clinical_payload = {
        "job_title": "臨床試驗專員 CRA",
        "job_description": "熟悉臨床試驗法規、ICH-GCP 與 IRB 送審流程。",
    }
    _, _, b2 = asyncio.run(_asgi_call("POST", "/api/extract", clinical_payload))
    d2 = json.loads(b2.decode("utf-8"))
    ids2 = {s["SKILL_ID"] for s in d2["skills"]}
    assert "KS124ZQ6RS1V188JSCTX" in ids2
    assert "ESC7869CF7378283E0AA" not in ids2


def test_zero_skill_job(loaded_engine):
    payload = {
        "job_title": "總機接待",
        "job_description": "負責接待來賓與環境整理。",
    }
    status, _, body = asyncio.run(_asgi_call("POST", "/api/extract", payload))
    assert status == 200
    data = json.loads(body.decode("utf-8"))
    assert data["stats"]["total_skills"] == 0
    assert data["job"]["是否命中技能"] is False


def test_100_jobs_excel_export_4_sheets(loaded_engine):
    jobs_payload: List[Dict[str, Any]] = []
    for i in range(1, 101):
        if i % 5 == 0:
            # 20 筆零技能職缺
            jobs_payload.append({
                "job_id": f"00{i:04d}",
                "data_month": "202611",
                "job_title": f"一般行政人員_{i}",
                "job_description": "負責收發信件與茶水準備。",
            })
        else:
            jobs_payload.append({
                "job_id": f"00{i:04d}",
                "data_month": "202611",
                "job_title": f"製程與AI資料工程師_{i}",
                "job_description": (
                    "【員工福利】享健康檢查與勞健保。\n"
                    "【工作內容】負責 Python、Machine Learning 與工程製程控制改善。"
                ),
                "computer_tools": "Python",
            })

    # 先取得 API 批次 JSON 結果
    st_ext, _, body_ext = asyncio.run(_asgi_call("POST", "/api/extract", {"jobs": jobs_payload}))
    assert st_ext == 200
    ext_data = json.loads(body_ext.decode("utf-8"))
    assert ext_data["stats"]["job_count"] == 100
    assert ext_data["stats"]["zero_skill_jobs"] == 20

    # 下載 .xlsx
    st_xls, hdrs, xlsx_bytes = asyncio.run(_asgi_call("POST", "/api/export/xlsx", {"jobs": jobs_payload}))
    assert st_xls == 200
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in hdrs["content-type"]
    assert "104_skill_extraction_" in hdrs["content-disposition"]
    assert hdrs["content-disposition"].endswith('.xlsx"')

    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=True)
    assert wb.sheetnames == ["Skills_Long", "Group10_Summary", "Jobs", "Audit"]

    ws_long = wb["Skills_Long"]
    ws_g10 = wb["Group10_Summary"]
    ws_jobs = wb["Jobs"]
    ws_audit = wb["Audit"]

    # 1. Skills_Long 筆數一致
    assert ws_long.max_row - 1 == ext_data["stats"]["total_skill_records"]
    # 2. Jobs 保留全部 100 筆（含零技能）
    assert ws_jobs.max_row - 1 == 100
    # 3. 前導零文字格式保留、不轉科學記號
    first_job_id_cell = ws_jobs.cell(row=2, column=1)
    assert first_job_id_cell.value == "000001"
    assert first_job_id_cell.number_format == "@"
    # 4. Group10_Summary 筆數一致
    assert ws_g10.max_row - 1 == len(ext_data["group10_summary"])
    # 5. Audit 筆數一致（包含福利排除與 G7|G10 歧義紀錄）
    assert ws_audit.max_row - 1 == len(ext_data["audit_records"])


def test_consistency_with_1111_cli_rules():
    """驗證 Web Adapter 與 104_single_city_merged_20261111.py 的核心規則一致。"""
    from src import web_adapter

    cli_path = Path("104_single_city_merged_20261111.py")
    assert cli_path.is_file()
    cli_src = cli_path.read_text(encoding="utf-8")

    # 檢查關鍵 11/11 規則常數與函式皆同步存在於兩邊
    for symbol in [
        "KS124ZQ6RS1V188JSCTX",
        "ESC7869CF7378283E0AA",
        "ES63C92B9AE0C7FC326A",
        "KS127MD73WL7RSVDW53X",
        "KS1239Z71LLXDMTGRJ5S",
        "ES92A402F893456D877B",
        "BGS423420828D2785973",
    ]:
        assert symbol in cli_src

    sample_desc = "【公司簡介】ESG 永續發展與經濟發展。【員工福利】勞健保與健康檢查。【工作內容】負責 GCP 與 Kubernetes 部署。"
    web_sections = web_adapter.parse_text_sections(sample_desc)
    types = [s["type"] for s in web_sections]
    assert "COMPANY_INTRO" in types
    assert "WELFARE" in types
    assert "JOB_DUTIES" in types

    assert web_adapter.is_context_excluded("ES92A402F893456D877B", "年度員工健康檢查與福利") is True
    assert web_adapter.lacks_required_context("ESC7869CF7378283E0AA", "GCP", sample_desc, sample_desc.find("GCP"), sample_desc.find("GCP") + 2) is False
    assert web_adapter.lacks_required_context("KS124ZQ6RS1V188JSCTX", "GCP", sample_desc, sample_desc.find("GCP"), sample_desc.find("GCP") + 2) is True


def test_ui_removed_forbidden_text_and_json_input():
    for rel in ("web/index.html", "web/app.html", "web/app.js"):
        txt = Path(rel).read_text(encoding="utf-8")
        assert "純本地比對，無需 API Key、不呼叫生成式 AI" not in txt
        assert "無需 API Key" not in txt
        assert "不呼叫生成式 AI" not in txt
        assert "batchJsonInput" not in txt
        assert "JSONL" not in txt
        assert "JSON 陣列" not in txt


def test_dataset_manifest_and_sampling_api(tmp_path: Path, loaded_engine):
    import base64
    from scripts.prepare_web_datasets import process_sanitized_demo_jsonl
    from src.web_adapter import get_dataset_store

    ds_dir = tmp_path / "datasets"
    ds_dir.mkdir()
    entries = process_sanitized_demo_jsonl(Path("data/sample/sample_jobs.jsonl"), ds_dir, limit=100, seed=42)
    manifest = {"manifest_version": "1.0.0", "generated_at": "2026-11-14T15:20:00+08:00", "datasets": entries}
    manifest_path = ds_dir / "dataset_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    # 確認 Manifest 不含本機絕對路徑或 Token
    raw_manifest = manifest_path.read_text(encoding="utf-8")
    assert "/Users/" not in raw_manifest
    assert "OneDrive" not in raw_manifest

    get_dataset_store(manifest_path=str(manifest_path), force_reload=True)

    st_list, _, body_list = asyncio.run(_asgi_call("GET", "/api/datasets"))
    assert st_list == 200
    ds_payload = json.loads(body_list.decode("utf-8"))
    assert ds_payload["ready"] is True
    assert len(ds_payload["cities"]) >= 1

    first_ds_id = ds_payload["datasets"][0]["dataset_id"]
    st_s1, _, b_s1 = asyncio.run(_asgi_call("POST", "/api/datasets/sample", {"dataset_id": first_ds_id, "mode": "fixed", "count": 100}))
    st_s2, _, b_s2 = asyncio.run(_asgi_call("POST", "/api/datasets/sample", {"dataset_id": first_ds_id, "mode": "fixed", "count": 100}))
    assert st_s1 == 200 and st_s2 == 200
    s1 = json.loads(b_s1.decode("utf-8"))
    s2 = json.loads(b_s2.decode("utf-8"))
    assert s1["jobs"] == s2["jobs"]  # 固定抽樣可重現
    assert s1["notice"] is not None  # 示範集少於 100 筆應明確提示

    # Option A 禁止偽裝隨機抽樣
    st_rand, _, _ = asyncio.run(_asgi_call("POST", "/api/datasets/sample", {"dataset_id": first_ds_id, "mode": "random", "count": 100}))
    assert st_rand == 400

    # 測試上傳 XLSX（含 工作編號 -> ID 映射與 兼職 排除）
    wb_up = openpyxl.Workbook()
    ws_up = wb_up.active
    ws_up.append(["工作編號", "資料月份", "工作角色", "104職位名稱", "職位描述", "工作技能", "電腦工具"])
    ws_up.append(["009988", "202611", "全職", "資料工程師", "負責 Python 與 SQL 資料管線。", "資料管線", "Python"])
    ws_up.append(["009988", "202611", "全職", "資料工程師", "重複列應被略過", "資料管線", "Python"])
    ws_up.append(["009989", "202611", "兼職", "兼職工讀生", "Python", "", ""])
    up_buf = io.BytesIO()
    wb_up.save(up_buf)
    b64 = base64.b64encode(up_buf.getvalue()).decode("ascii")

    st_up, _, b_up = asyncio.run(_asgi_call("POST", "/api/extract/xlsx-upload", {"filename": "test_up.xlsx", "content_base64": b64}))
    assert st_up == 200
    up_res = json.loads(b_up.decode("utf-8"))
    assert up_res["upload_stats"]["accepted_unique_jobs"] == 1
    assert up_res["upload_stats"]["excluded_part_time"] == 1
    assert up_res["jobs"][0]["ID"] == "009988"


def test_parse_text_sections_matches_cli_regression():
    """回歸測試：確保開頭前言接裸編號清單與福利段落內編號清單之分段邏輯與 11/11 CLI 一致。"""
    from src.web_adapter import get_section_for_offset, parse_text_sections

    # 1. 11082602 型態：開頭含公司介紹慣用語，後接 1. 2. 裸編號清單，再接【員工福利】
    desc_11082602 = (
        "我們是深耕全台的專業品牌，致力於通路服務。"
        "1.負責區域客戶服務與商品陳列。"
        "2.執行市場調查與數據分析。"
        "【員工福利】1.三節獎金 2.員工旅遊"
    )
    secs1 = parse_text_sections(desc_11082602)
    assert get_section_for_offset(secs1, desc_11082602.index("深耕全台"))["type"] == "COMPANY_INTRO"
    assert get_section_for_offset(secs1, desc_11082602.index("客戶服務"))["type"] == "JOB_DUTIES"
    assert get_section_for_offset(secs1, desc_11082602.index("員工旅遊"))["type"] == "WELFARE"

    # 2. 11501700 型態：【薪資待遇】福利段落內含 1. 2. 3. 加給條件，不可被誤切為 JOB_DUTIES
    desc_11501700 = (
        "【工作內容】1.物理治療評估與介入。"
        "【薪資待遇】1.底薪45000元 2.績效獎金 3.擁有物理治療師證書另加給。"
        "【福利制度】內部專業訓練制度"
    )
    secs2 = parse_text_sections(desc_11501700)
    assert get_section_for_offset(secs2, desc_11501700.index("擁有物理治療師證書"))["type"] == "WELFARE"

    # 3. 12897906 型態：【我們有全台最好的餐飲環境】福利段落內含 1. 2. 3.，不可被誤切為 JOB_DUTIES
    desc_12897906 = (
        "【關於我們】我們是餐飲品牌。"
        "【我們有全台最好的餐飲環境】★員工享有以下環境與工作的內容★1. 餐廳酒水庫存管理。2. 協助外場人員現場服務。"
        "【其他福利】勞健保"
    )
    secs3 = parse_text_sections(desc_12897906)
    assert get_section_for_offset(secs3, desc_12897906.index("庫存管理"))["type"] == "WELFARE"


def test_dynamic_dataset_button_and_demo_disclosure():
    """Task 2：確認前端按鈕與資訊欄依 sample_size 與 access_level 動態顯示，不誤導為 100 筆。"""
    index_html = Path("web/index.html").read_text(encoding="utf-8")
    app_js = Path("web/app.js").read_text(encoding="utf-8")
    assert 'id="analyzeBtn">抽取並分析 100 筆職缺</button>' not in index_html
    assert "getDatasetButtonLabel" in app_js
    assert "分析 ${count} 筆示範職缺" in app_js
    assert "脫敏示範資料（非完整 100 筆正式研究資料）" in app_js


def test_protected_dataset_access_control(tmp_path: Path, loaded_engine, monkeypatch):
    """Task 2：驗證非 sanitized_demo 正式研究資料在 /api/datasets/sample、/api/extract、/api/export/xlsx 受 fail-closed 保護。"""
    import gzip
    from src.web_adapter import get_dataset_store

    ds_dir = tmp_path / "protected_ds"
    ds_dir.mkdir()
    sample_file = "auth_taichung_202609.json.gz"
    with gzip.open(ds_dir / sample_file, "wt", encoding="utf-8") as f:
        json.dump(
            {
                "jobs": [
                    {
                        "job_id": "AUTH_001",
                        "data_month": "202609",
                        "job_title": "資料工程師",
                        "job_description": "負責 Python 與 SQL 資料管線。",
                        "job_skills": "Python",
                        "computer_tools": "SQL",
                    }
                ]
            },
            f,
            ensure_ascii=False,
        )
    manifest = {
        "manifest_version": "1.0.0",
        "generated_at": "2026-11-14T15:50:00+08:00",
        "datasets": [
            {
                "dataset_id": "auth_taichung_202609",
                "city": "臺中市",
                "year_month": "202609",
                "source_filename": "cleaned_臺中市_202609.xlsx",
                "source_sha256": "abc123",
                "raw_job_count": 100,
                "filtered_job_count": 90,
                "available_job_count": 90,
                "sample_size": 1,
                "sample_seed": 42,
                "sample_version": "v1_fixed_seed42",
                "role_filter_rule": "排除兼職",
                "access_level": "research_authorized",
                "sampling_modes_supported": ["fixed"],
                "sampled_job_ids": ["AUTH_001@202609"],
                "sample_file": sample_file,
            }
        ],
    }
    manifest_path = ds_dir / "dataset_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    get_dataset_store(manifest_path=str(manifest_path), force_reload=True)

    # 1. GET /api/datasets 只回傳 metadata，不含職缺原文
    st_list, _, body_list = asyncio.run(_asgi_call("GET", "/api/datasets"))
    assert st_list == 200
    assert "負責 Python 與 SQL 資料管線" not in body_list.decode("utf-8")

    # 2. 未設定 RESEARCH_API_TOKEN 時，三個端點皆應回 403 fail-closed
    monkeypatch.delenv("RESEARCH_API_TOKEN", raising=False)
    for ep in ("/api/datasets/sample", "/api/extract", "/api/export/xlsx"):
        st, _, _ = asyncio.run(_asgi_call("POST", ep, {"dataset_id": "auth_taichung_202609"}))
        assert st == 403

    # 3. 設定 RESEARCH_API_TOKEN 後，無 Token 回 401，正確 Bearer Token 回 200
    monkeypatch.setenv("RESEARCH_API_TOKEN", "secret-prof-token")
    for ep in ("/api/datasets/sample", "/api/extract", "/api/export/xlsx"):
        st_unauth, _, _ = asyncio.run(_asgi_call("POST", ep, {"dataset_id": "auth_taichung_202609"}))
        assert st_unauth == 401
        st_ok, _, _ = asyncio.run(
            _asgi_call(
                "POST",
                ep,
                {"dataset_id": "auth_taichung_202609"},
                extra_headers=[(b"authorization", b"Bearer secret-prof-token")],
            )
        )
        assert st_ok == 200


def test_ui_skill_details_and_batch_explorer():
    """UI 回歸修正：確認單篇與批次模式皆直接呈現技能明細、G1–G10 分布與逐筆職缺檢視，且零技能顯示明確提示。"""
    index_html = Path("web/index.html").read_text(encoding="utf-8")
    app_js = Path("web/app.js").read_text(encoding="utf-8")

    # 6 KPI、G1–G10 分布與完整技能明細表欄位
    for elem_id in (
        "kpiVal1",
        "kpiVal6",
        "batchJobsTableBody",
        "jobSearchInput",
        "jobSortSelect",
        "prevJobBtn",
        "nextJobBtn",
        "showAllSkillsBtn",
        "skillDetailsSection",
        "groupChart",
        "skillChips",
        "skillsTableBody",
    ):
        assert elem_id in index_html

    for col in ("SKILL_ID", "Category / Subcategory", "G1–G10 分類", "Is_AI_Skill", "MATCHED_FROM", "匹配證據"):
        assert col in index_html

    # app.js 不可再於 batch 模式隱藏技能明細，且必須渲染 skills_long、零技能提示與逐筆點擊切換
    assert 'singleResultDetails.classList.add("hidden")' not in app_js
    assert "lastBatchData.skills_long" in app_js
    assert "selectBatchJob" in app_js
    assert "stepBatchJob" in app_js
    assert "未擷取到技能" in app_js
