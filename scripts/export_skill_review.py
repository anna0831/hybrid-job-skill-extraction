"""Export reproducible human-review candidates; job titles do not prove industry."""
import argparse
import csv
import json
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.outputs.sqlite_preview import connect_readonly, fetch_job
from src.outputs.sqlite_store import columns, quote

# Sampling aids only. Confirm industry using the company's actual industry metadata.
TITLE_HINTS = {
    "餐飲": ["餐飲", "餐廳", "廚", "餐館", "餐食", "咖啡", "飲料", "調酒", "烘焙"],
    "補教": ["補習", "補教", "課輔", "家教", "安親", "教師", "老師", "教務", "招生"],
    "醫療": ["醫師", "護理", "藥師", "藥劑", "醫療", "醫事", "治療師", "診所", "牙醫"],
}


def export_review(db, output, industry, *, limit=50, seed=202609, no_detail=False, month=None):
    if limit < 1:
        raise ValueError("limit must be positive")
    from contextlib import closing
    rng, selected, eligible = random.Random(seed), [], 0
    conditions = ['(' + ' OR '.join('instr(COALESCE(j."104職位名稱",\'\'),?)>0' for _ in TITLE_HINTS[industry]) + ')']
    params = list(TITLE_HINTS[industry])
    if month:
        conditions.append("j.資料月份=?")
        params.append(month)
    if no_detail:
        conditions.append("NOT EXISTS (SELECT 1 FROM skill_records sr WHERE sr.ID=j.ID AND sr.資料月份=j.資料月份)")
    with closing(connect_readonly(db)) as conn:
        query = "SELECT j.ID,j.資料月份 FROM jobs j WHERE " + " AND ".join(conditions) + " ORDER BY j.ID,j.資料月份"
        # Reservoir sampling consumes only O(limit) application memory.
        for eligible, row in enumerate(conn.execute(query, params), 1):
            key = tuple(row)
            if len(selected) < limit:
                selected.append(key)
            else:
                i = rng.randrange(eligible)
                if i < limit:
                    selected[i] = key
        available = columns(conn, "skill_records")
        skill_cols = [c for c in ["record_id", "SKILL_ID", "Skill_Name_ZH", "category", "subcategory",
                                 "MATCHED_FROM", "MATCHED_KEYWORD", "START_POS", "END_POS"] if c in available]
        result = []
        for jid, snapshot_month in sorted(selected):
            job = fetch_job(db, jid, snapshot_month)
            details = [dict(r) for r in conn.execute(
                f"SELECT {','.join(map(quote, skill_cols))} FROM skill_records WHERE ID=? AND 資料月份=? ORDER BY record_id",
                (jid, snapshot_month))]
            raw_sources = []
            if columns(conn, "raw_job_sources"):
                raw_sources = [json.loads(r[0]) for r in conn.execute(
                    "SELECT source_payload FROM raw_job_sources WHERE ID=? AND 資料月份=? ORDER BY source_id",
                    (jid, snapshot_month))]
            result.append({"candidate_industry": industry, "industry_confirmed": "",
                           "sampling_basis": "job_title_proxy", "seed": seed, "ID": jid,
                           "資料月份": snapshot_month, "104職位名稱": job["104職位名稱"],
                           "職位描述": job["職位描述"], "工作技能": job["工作技能"], "電腦工具": job["電腦工具"],
                           "skill_detail_rows": len(details),
                           "extracted_skills_json": json.dumps(details, ensure_ascii=False),
                           "original_job_metadata_json": json.dumps(raw_sources, ensure_ascii=False),
                           "false_positive_record_ids": "", "missing_SKILL_IDs": "",
                           "expected_SKILL_IDs": "", "evidence": "", "reviewer": "", "notes": ""})
    fieldnames = list(result[0]) if result else ["candidate_industry", "industry_confirmed", "ID", "資料月份", "notes"]
    output = Path(output)
    if output.exists():
        raise FileExistsError("Review output already exists; choose a new filename")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(result)
    return {"eligible_job_snapshots": eligible, "exported_job_snapshots": len(result),
            "sampling_basis": "job_title_proxy", "output": str(output.resolve())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--industry", choices=list(TITLE_HINTS), required=True)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--seed", type=int, default=202609)
    parser.add_argument("--month")
    parser.add_argument("--no-detail", action="store_true")
    args = parser.parse_args()
    try:
        result = export_review(args.db, args.output, args.industry, limit=args.limit,
                               seed=args.seed, no_detail=args.no_detail, month=args.month)
    except Exception as exc:
        parser.exit(1, f"Review export failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
