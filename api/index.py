"""
Vercel / FastAPI 後端入口 (api/index.py)

提供：
- GET  /api/health       系統與詞庫健康狀態（不啟用 LLM）
- POST /api/extract      單篇或最多 100 筆職缺之 11/11 AC + Rules 技能擷取
- POST /api/export/xlsx  單篇或最多 100 筆職缺之 4 工作表 Excel (.xlsx) 記憶體下載

本機開發時亦同時掛載 web/ 靜態檔案至根路徑 /。
"""

from __future__ import annotations

import base64
import hmac
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, ValidationError

try:
    from fastapi import FastAPI, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, Response
    from fastapi.staticfiles import StaticFiles
    _HAS_FASTAPI = True
except ImportError:  # 本機環境若僅有 Starlette 時仍可執行與測試
    from starlette.applications import Starlette as FastAPI
    from starlette.middleware.cors import CORSMiddleware
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response
    from starlette.routing import Mount, Route
    from starlette.staticfiles import StaticFiles
    _HAS_FASTAPI = False

from src.web_adapter import (
    MAX_BATCH_JOBS,
    MAX_FIELD_CHARS,
    generate_excel_workbook,
    get_dataset_store,
    get_web_engine,
    parse_uploaded_xlsx,
)

# 僅紀錄摘要資訊，禁止紀錄職缺原文
logger = logging.getLogger("web_api")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class JobInput(BaseModel):
    job_id: Optional[str] = Field(default=None, max_length=64)
    data_month: Optional[str] = Field(default=None, max_length=16)
    job_title: str = Field(default="", max_length=300)
    job_description: str = Field(default="", max_length=MAX_FIELD_CHARS)
    job_skills: str = Field(default="", max_length=5000)
    computer_tools: str = Field(default="", max_length=5000)


class BatchExtractRequest(BaseModel):
    jobs: List[JobInput] = Field(..., min_length=1, max_length=MAX_BATCH_JOBS)


class DatasetSampleRequest(BaseModel):
    dataset_id: str = Field(..., min_length=1, max_length=128)
    mode: str = Field(default="fixed", max_length=32)
    count: int = Field(default=MAX_BATCH_JOBS, ge=1, le=MAX_BATCH_JOBS)


class XlsxUploadRequest(BaseModel):
    filename: str = Field(default="uploaded.xlsx", max_length=255)
    content_base64: str = Field(..., min_length=1, max_length=8_000_000)


def _check_dataset_access(request: Request, dataset_meta: Dict[str, Any]) -> Optional[JSONResponse]:
    """對非脫敏示範資料集（access_level != 'sanitized_demo'）強制執行 fail-closed 驗證。"""
    if dataset_meta.get("access_level") == "sanitized_demo":
        return None
    expected = os.environ.get("RESEARCH_API_TOKEN", "").strip()
    if not expected:
        return JSONResponse(
            status_code=403,
            content={"detail": "此資料集為受保護研究資料，伺服器尚未啟用存取驗證，拒絕未授權存取。"},
        )
    auth_header = request.headers.get("authorization", "")
    prefix = "Bearer "
    provided = auth_header[len(prefix):].strip() if auth_header.startswith(prefix) else ""
    if not provided or not hmac.compare_digest(provided, expected):
        return JSONResponse(
            status_code=401,
            content={"detail": "存取正式研究資料需要有效的 Bearer Token 驗證。"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return None


def _allowed_origins() -> List[str]:
    raw = os.environ.get("ALLOWED_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return ["*"]


def _parse_extract_payload(body: Any) -> tuple[bool, List[Dict[str, Any]], Optional[Dict[str, Any]], Optional[str]]:
    if not isinstance(body, dict):
        raise ValueError("Request body 必須為 JSON 物件。")
    if "dataset_id" in body:
        req = DatasetSampleRequest.model_validate(body)
        store = get_dataset_store()
        sampled = store.load_sample(dataset_id=req.dataset_id, mode=req.mode, count=req.count)
        return True, sampled["jobs"], sampled["dataset"], sampled.get("notice")
    if "jobs" in body:
        req = BatchExtractRequest.model_validate(body)
        return True, [j.model_dump() for j in req.jobs], None, None
    job = JobInput.model_validate(body)
    if not any([job.job_title.strip(), job.job_description.strip(), job.job_skills.strip(), job.computer_tools.strip()]):
        raise ValueError("請至少輸入職缺名稱或工作內容其中一項。")
    return False, [job.model_dump()], None, None


async def handle_health(_: Request) -> JSONResponse:
    engine = get_web_engine()
    info = engine.health_info()
    return JSONResponse(content=info, status_code=200)


async def handle_datasets(_: Request) -> JSONResponse:
    store = get_dataset_store()
    return JSONResponse(content=store.list_datasets_payload(), status_code=200)


async def handle_datasets_sample(request: Request) -> JSONResponse:
    try:
        raw_body = await request.json()
        req = DatasetSampleRequest.model_validate(raw_body)
    except ValidationError as exc:
        return JSONResponse(status_code=422, content={"detail": "抽樣參數驗證失敗。", "errors": exc.errors()})
    except Exception:
        return JSONResponse(status_code=400, content={"detail": "無效的 JSON 格式。"})

    store = get_dataset_store()
    try:
        sampled = store.load_sample(dataset_id=req.dataset_id, mode=req.mode, count=req.count)
    except KeyError as exc:
        return JSONResponse(status_code=404, content={"detail": str(exc)})
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    except FileNotFoundError as exc:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    auth_err = _check_dataset_access(request, sampled["dataset"])
    if auth_err is not None:
        return auth_err

    logger.info("sample dataset=%s mode=%s count=%d", req.dataset_id, req.mode, len(sampled["jobs"]))
    return JSONResponse(content=sampled, status_code=200)


async def handle_extract(request: Request) -> JSONResponse:
    engine = get_web_engine()
    if not engine.ready:
        return JSONResponse(
            status_code=503,
            content={"detail": engine.load_error or "詞庫尚未就緒，請先產生 web_data/lexicon_bundle.json.gz。"},
        )

    try:
        raw_body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"detail": "無效的 JSON 格式。"})

    try:
        is_batch, jobs, dataset_meta, notice = _parse_extract_payload(raw_body)
    except ValidationError as exc:
        return JSONResponse(status_code=422, content={"detail": "輸入欄位驗證失敗或超過字數／筆數限制。", "errors": exc.errors()})
    except (KeyError, FileNotFoundError) as exc:
        return JSONResponse(status_code=404, content={"detail": str(exc)})
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    if dataset_meta is not None:
        auth_err = _check_dataset_access(request, dataset_meta)
        if auth_err is not None:
            return auth_err

    logger.info("extract request: batch=%s job_count=%d", is_batch, len(jobs))
    if is_batch:
        result = engine.extract_batch_jobs(jobs, dataset_meta=dataset_meta)
        return JSONResponse(content={"mode": "batch", "notice": notice, **result}, status_code=200)

    single = engine.extract_single_job(jobs[0], default_index=1)
    return JSONResponse(content={"mode": "single", **single}, status_code=200)


async def handle_extract_xlsx_upload(request: Request) -> JSONResponse:
    engine = get_web_engine()
    if not engine.ready:
        return JSONResponse(
            status_code=503,
            content={"detail": engine.load_error or "詞庫尚未就緒。"},
        )
    try:
        raw_body = await request.json()
        req = XlsxUploadRequest.model_validate(raw_body)
        xlsx_bytes = base64.b64decode(req.content_base64, validate=True)
        jobs, upload_stats = parse_uploaded_xlsx(xlsx_bytes, max_jobs=MAX_BATCH_JOBS)
    except ValidationError as exc:
        return JSONResponse(status_code=422, content={"detail": "上傳格式驗證失敗。", "errors": exc.errors()})
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    except Exception:
        return JSONResponse(status_code=400, content={"detail": "無法解析上傳的 Excel 檔案，請確認為有效 .xlsx。"})

    logger.info("extract xlsx upload: accepted_jobs=%d", len(jobs))
    result = engine.extract_batch_jobs(jobs, dataset_meta={"sample_version": f"xlsx_upload:{req.filename}"})
    return JSONResponse(content={"mode": "batch", "upload_stats": upload_stats, **result}, status_code=200)


async def handle_export_xlsx(request: Request) -> Response:
    engine = get_web_engine()
    if not engine.ready:
        return JSONResponse(
            status_code=503,
            content={"detail": engine.load_error or "詞庫尚未就緒，無法匯出 Excel。"},
        )

    try:
        raw_body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"detail": "無效的 JSON 格式。"})

    try:
        if isinstance(raw_body, dict) and "content_base64" in raw_body:
            req = XlsxUploadRequest.model_validate(raw_body)
            xlsx_in = base64.b64decode(req.content_base64, validate=True)
            jobs, _ = parse_uploaded_xlsx(xlsx_in, max_jobs=MAX_BATCH_JOBS)
            dataset_meta = {"sample_version": f"xlsx_upload:{req.filename}"}
        else:
            _, jobs, dataset_meta, _ = _parse_extract_payload(raw_body)
    except ValidationError as exc:
        return JSONResponse(status_code=422, content={"detail": "輸入欄位驗證失敗或超過字數／筆數限制。", "errors": exc.errors()})
    except (KeyError, FileNotFoundError) as exc:
        return JSONResponse(status_code=404, content={"detail": str(exc)})
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    if dataset_meta is not None and "access_level" in dataset_meta:
        auth_err = _check_dataset_access(request, dataset_meta)
        if auth_err is not None:
            return auth_err

    logger.info("export xlsx request: job_count=%d", len(jobs))
    batch_res = engine.extract_batch_jobs(jobs, dataset_meta=dataset_meta)
    xlsx_bytes = generate_excel_workbook(batch_res)

    ts = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y%m%d_%H%M%S")
    filename = f"104_skill_extraction_{ts}.xlsx"

    return Response(
        content=xlsx_bytes,
        media_type=XLSX_MIME,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Job-Count": str(batch_res["stats"]["job_count"]),
            "X-Skill-Records": str(batch_res["stats"]["total_skill_records"]),
        },
    )


_WEB_DIR = Path(__file__).resolve().parent.parent / "web"

if _HAS_FASTAPI:
    app = FastAPI(
        title="104 職缺技能擷取研究展示 API (AC + Rules)",
        version="20261111_web_ac_v1",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.add_api_route("/api/health", handle_health, methods=["GET"])
    app.add_api_route("/api/datasets", handle_datasets, methods=["GET"])
    app.add_api_route("/api/datasets/sample", handle_datasets_sample, methods=["POST"])
    app.add_api_route("/api/extract", handle_extract, methods=["POST"])
    app.add_api_route("/api/extract/xlsx-upload", handle_extract_xlsx_upload, methods=["POST"])
    app.add_api_route("/api/export/xlsx", handle_export_xlsx, methods=["POST"])
    if _WEB_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(_WEB_DIR), html=True), name="web")
else:
    routes = [
        Route("/api/health", handle_health, methods=["GET"]),
        Route("/api/datasets", handle_datasets, methods=["GET"]),
        Route("/api/datasets/sample", handle_datasets_sample, methods=["POST"]),
        Route("/api/extract", handle_extract, methods=["POST"]),
        Route("/api/extract/xlsx-upload", handle_extract_xlsx_upload, methods=["POST"]),
        Route("/api/export/xlsx", handle_export_xlsx, methods=["POST"]),
    ]
    if _WEB_DIR.is_dir():
        routes.append(Mount("/", StaticFiles(directory=str(_WEB_DIR), html=True), name="web"))
    app = FastAPI(routes=routes)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)
