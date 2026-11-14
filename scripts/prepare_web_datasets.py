#!/usr/bin/env python3
"""
掃描清洗後 104 職缺 Excel (.xlsx) 或脫敏示範 JSONL，產生：
- dataset_manifest.json（不含本機絕對路徑或任何憑證）
- 每個縣市×月份對應之固定 100 筆（seed=42）不重複職缺樣本 (.json.gz)

篩選與識別規則與 104_single_city_merged_20261111.py 完全一致：
- 工作編號 -> ID（保留前導零）
- 唯一職缺鍵：(ID, 資料月份)
- 工作角色篩選：僅排除「工作角色 == '兼職'」，保留全職、高階及其他所有角色
- 抽樣順序：先依 (ID, 資料月份) 排序後，再以 random.Random(42).sample(...) 抽取最多 100 筆
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import random
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import openpyxl

EXCLUDED_ROLE = "兼職"
ROLE_FILTER_RULE = "排除 工作角色 == '兼職'（保留全職、高階及其他所有角色）"
DEFAULT_SEED = 42
DEFAULT_SAMPLE_LIMIT = 100
SAMPLE_VERSION = "v1_fixed_seed42"

CITY_SLUG_MAP = {
    "臺北市": "taipei",
    "台北市": "taipei",
    "新北市": "new_taipei",
    "桃園市": "taoyuan",
    "臺中市": "taichung",
    "台中市": "taichung",
    "臺南市": "tainan",
    "台南市": "tainan",
    "高雄市": "kaohsiung",
    "新竹市": "hsinchu_city",
    "新竹縣": "hsinchu_county",
    "基隆市": "keelung",
    "苗栗縣": "miaoli",
    "彰化縣": "changhua",
    "南投縣": "nantou",
    "雲林縣": "yunlin",
    "嘉義市": "chiayi_city",
    "嘉義縣": "chiayi_county",
    "屏東縣": "pingtung",
    "宜蘭縣": "yilan",
    "花蓮縣": "hualien",
    "臺東縣": "taitung",
    "台東縣": "taitung",
    "澎湖縣": "penghu",
    "金門縣": "kinmen",
    "連江縣": "lienchiang",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _clean_str_preserve_leading_zero(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, bool):
        return str(val)
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        if val.is_integer():
            return str(int(val))
        return str(val).strip()
    s = str(val).strip()
    return "" if s.lower() == "nan" else s


def _clean_str(val: Any) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    return "" if s.lower() == "nan" else s


def extract_city_and_month(filename: str) -> Tuple[str, str]:
    m_month = re.search(r"(20\d{4})", filename)
    year_month = m_month.group(1) if m_month else "unknown"
    city = "未知縣市"
    for c_name in CITY_SLUG_MAP:
        if c_name in filename:
            city = c_name
            break
    if city == "未知縣市":
        m_city = re.search(r"cleaned_([^_]+)_20\d{4}", filename)
        if m_city:
            city = m_city.group(1)
    return city, year_month


def _make_dataset_id(city: str, year_month: str, prefix: str = "") -> str:
    slug = CITY_SLUG_MAP.get(city, re.sub(r"[^a-zA-Z0-9]+", "_", city).strip("_") or "dataset")
    base = f"{slug}_{year_month}"
    return f"{prefix}_{base}" if prefix else base


def _sample_jobs(
    records: List[Dict[str, Any]],
    limit: int = DEFAULT_SAMPLE_LIMIT,
    seed: int = DEFAULT_SEED,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    raw_job_count = len(records)
    filtered: List[Dict[str, Any]] = []
    excluded_part_time = 0

    for rec in records:
        role = _clean_str(rec.get("工作角色"))
        if role == EXCLUDED_ROLE:
            excluded_part_time += 1
            continue
        job_id = _clean_str_preserve_leading_zero(rec.get("ID") or rec.get("工作編號"))
        if not job_id:
            raise ValueError("職缺資料缺少識別欄位（ID / 工作編號），禁止自行編造。")
        data_month = _clean_str_preserve_leading_zero(rec.get("資料月份")) or "unknown"
        norm = {
            "ID": job_id,
            "資料月份": data_month,
            "工作角色": role,
            "104職位名稱": _clean_str(rec.get("104職位名稱") or rec.get("職位名稱") or rec.get("職稱")),
            "職位描述": _clean_str(rec.get("職位描述")),
            "工作技能": _clean_str(rec.get("工作技能")),
            "電腦工具": _clean_str(rec.get("電腦工具")),
        }
        filtered.append(norm)

    filtered_job_count = len(filtered)

    # 依 (ID, 資料月份) 去重並檢核內容衝突
    by_key: Dict[Tuple[str, str], Dict[str, Any]] = {}
    duplicate_warnings: List[str] = []
    for item in filtered:
        key = (item["ID"], item["資料月份"])
        if key not in by_key:
            by_key[key] = item
        else:
            prev = by_key[key]
            diffs = [
                f for f in ("104職位名稱", "職位描述", "工作技能", "電腦工具")
                if prev[f] != item[f]
            ]
            if diffs:
                duplicate_warnings.append(
                    f"重複鍵 {key} 內容不一致（差異欄位：{', '.join(diffs)}），保留首次出現紀錄。"
                )

    sorted_keys = sorted(by_key.keys())
    available_job_count = len(sorted_keys)

    if available_job_count <= limit:
        chosen_keys = sorted_keys
    else:
        rng = random.Random(seed)
        chosen_keys = sorted(rng.sample(sorted_keys, limit))

    sampled = [by_key[k] for k in chosen_keys]
    stats = {
        "raw_job_count": raw_job_count,
        "excluded_part_time_count": excluded_part_time,
        "filtered_job_count": filtered_job_count,
        "available_job_count": available_job_count,
        "sample_size": len(sampled),
        "sampled_job_ids": [f"{k[0]}@{k[1]}" for k in chosen_keys],
        "duplicate_conflict_warnings": duplicate_warnings,
    }
    return sampled, stats


def process_cleaned_excel(
    xlsx_path: Path,
    out_dir: Path,
    access_level: str = "authorized_research",
    limit: int = DEFAULT_SAMPLE_LIMIT,
    seed: int = DEFAULT_SEED,
) -> Dict[str, Any]:
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        headers_raw = next(rows_iter)
    except StopIteration:
        wb.close()
        raise ValueError(f"Excel 檔案為空：{xlsx_path.name}")

    headers = [_clean_str(h) for h in headers_raw]
    records: List[Dict[str, Any]] = []
    for row in rows_iter:
        if row is None or all(v is None or str(v).strip() == "" for v in row):
            continue
        rec = {headers[i]: (row[i] if i < len(row) else None) for i in range(len(headers)) if headers[i]}
        records.append(rec)
    wb.close()

    city, year_month = extract_city_and_month(xlsx_path.name)
    sampled, stats = _sample_jobs(records, limit=limit, seed=seed)
    dataset_id = _make_dataset_id(city, year_month)
    sample_filename = f"{dataset_id}.json.gz"
    sample_out = out_dir / sample_filename

    payload = {
        "dataset_id": dataset_id,
        "city": city,
        "year_month": year_month,
        "sample_version": SAMPLE_VERSION,
        "access_level": access_level,
        "jobs": sampled,
    }
    raw_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with gzip.open(sample_out, "wb", compresslevel=6) as f:
        f.write(raw_bytes)

    return {
        "dataset_id": dataset_id,
        "city": city,
        "year_month": year_month,
        "source_filename": xlsx_path.name,
        "source_sha256": sha256_file(xlsx_path),
        "raw_job_count": stats["raw_job_count"],
        "filtered_job_count": stats["filtered_job_count"],
        "available_job_count": stats["available_job_count"],
        "sample_size": stats["sample_size"],
        "sample_seed": seed,
        "generated_at": datetime.now(ZoneInfo("Asia/Taipei")).isoformat(),
        "sample_version": SAMPLE_VERSION,
        "role_filter_rule": ROLE_FILTER_RULE,
        "access_level": access_level,
        "sampling_modes_supported": ["fixed"],
        "sampled_job_ids": stats["sampled_job_ids"],
        "duplicate_conflict_count": len(stats["duplicate_conflict_warnings"]),
        "sample_file": sample_filename,
    }


def process_sanitized_demo_jsonl(
    jsonl_path: Path,
    out_dir: Path,
    limit: int = DEFAULT_SAMPLE_LIMIT,
    seed: int = DEFAULT_SEED,
) -> List[Dict[str, Any]]:
    """將開源脫敏示範集轉成安全的預設展示 Manifest（明確標示 sanitized_demo，不宣稱為正式 104 原文）。"""
    records_by_bucket: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    with jsonl_path.open("r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            city = _clean_str(obj.get("縣市") or obj.get("county")) or "示範資料集"
            ym = _clean_str(obj.get("資料月份") or obj.get("month")) or "202609"
            rec = {
                "ID": _clean_str_preserve_leading_zero(obj.get("ID") or obj.get("工作編號") or f"DEMO_{idx:03d}"),
                "資料月份": ym,
                "工作角色": _clean_str(obj.get("工作角色")) or "全職",
                "104職位名稱": _clean_str(obj.get("職位名稱") or obj.get("104職位名稱") or obj.get("job_title")),
                "職位描述": _clean_str(obj.get("職位描述") or obj.get("job_desc")),
                "工作技能": _clean_str(obj.get("工作技能") or obj.get("job_skills")),
                "電腦工具": _clean_str(obj.get("電腦工具") or obj.get("tools")),
            }
            records_by_bucket.setdefault((city, ym), []).append(rec)

    src_sha = sha256_file(jsonl_path)
    entries: List[Dict[str, Any]] = []
    for (city, ym), recs in sorted(records_by_bucket.items()):
        sampled, stats = _sample_jobs(recs, limit=limit, seed=seed)
        dataset_id = _make_dataset_id(city, ym, prefix="demo")
        sample_filename = f"{dataset_id}.json.gz"
        payload = {
            "dataset_id": dataset_id,
            "city": city,
            "year_month": ym,
            "sample_version": SAMPLE_VERSION,
            "access_level": "sanitized_demo",
            "jobs": sampled,
        }
        with gzip.open(out_dir / sample_filename, "wb", compresslevel=6) as f:
            f.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

        entries.append({
            "dataset_id": dataset_id,
            "city": f"{city}（脫敏示範）",
            "year_month": ym,
            "source_filename": jsonl_path.name,
            "source_sha256": src_sha,
            "raw_job_count": stats["raw_job_count"],
            "filtered_job_count": stats["filtered_job_count"],
            "available_job_count": stats["available_job_count"],
            "sample_size": stats["sample_size"],
            "sample_seed": seed,
            "generated_at": datetime.now(ZoneInfo("Asia/Taipei")).isoformat(),
            "sample_version": SAMPLE_VERSION,
            "role_filter_rule": ROLE_FILTER_RULE,
            "access_level": "sanitized_demo",
            "sampling_modes_supported": ["fixed"],
            "sampled_job_ids": stats["sampled_job_ids"],
            "duplicate_conflict_count": len(stats["duplicate_conflict_warnings"]),
            "sample_file": sample_filename,
        })
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description="建置 Web 版縣市／月份固定抽樣資料集與 dataset_manifest.json")
    parser.add_argument("--input-dir", default=None, help="掃描清洗後 cleaned_*.xlsx 的資料夾路徑")
    parser.add_argument("--input-files", nargs="*", default=None, help="明確指定一或多個 cleaned_*.xlsx 路徑")
    parser.add_argument("--demo-jsonl", default=None, help="使用開源脫敏示範 JSONL 建立示範 Manifest")
    parser.add_argument("--output-dir", default="web_data/datasets", help="輸出資料夾（預設 web_data/datasets）")
    parser.add_argument("--access-level", default="authorized_research", help="資料集授權層級標記")
    parser.add_argument("--limit", type=int, default=DEFAULT_SAMPLE_LIMIT, help="每個資料集最大抽樣筆數（預設 100）")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="固定抽樣隨機種子（預設 42）")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    datasets: List[Dict[str, Any]] = []
    if args.demo_jsonl:
        datasets.extend(process_sanitized_demo_jsonl(Path(args.demo_jsonl), out_dir, limit=args.limit, seed=args.seed))
    else:
        xlsx_files: List[Path] = []
        if args.input_files:
            xlsx_files.extend(Path(p) for p in args.input_files)
        if args.input_dir:
            d = Path(args.input_dir)
            xlsx_files.extend(sorted(p for p in d.rglob("cleaned_*.xlsx") if not p.name.startswith("~$")))
        if not xlsx_files:
            print("❌ 請提供 --input-dir、--input-files 或 --demo-jsonl。", file=sys.stderr)
            return 1
        for xp in xlsx_files:
            print(f"處理中：{xp.name} ...")
            entry = process_cleaned_excel(
                xp, out_dir, access_level=args.access_level, limit=args.limit, seed=args.seed
            )
            datasets.append(entry)
            print(
                f"  -> {entry['city']} / {entry['year_month']}: "
                f"母體 {entry['raw_job_count']:,} -> 篩選後 {entry['available_job_count']:,} -> 抽樣 {entry['sample_size']} 筆"
            )

    manifest = {
        "manifest_version": "1.0.0",
        "generated_at": datetime.now(ZoneInfo("Asia/Taipei")).isoformat(),
        "datasets": datasets,
    }
    manifest_path = out_dir / "dataset_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 已產生 Manifest：{manifest_path}（共 {len(datasets)} 個資料集）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
