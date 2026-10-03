"""Comprehensive Smoke Test and Performance Measurement for Demo Recording.
Tests the complete user journey TWICE consecutively on data/demo/demo_彰化縣_202608_500.xlsx.
"""

import io
import os
import sys
import time
import pandas as pd
import openpyxl

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

DEMO_FILE = os.path.join(REPO_ROOT, "data/demo/demo_彰化縣_202608_500.xlsx")
LEXICON_PATH = os.path.join(REPO_ROOT, "詞庫skill_lexicon_v13_20260918.xlsx")

from src.hybrid_pipeline import HybridJobSkillPipeline
from src.outputs.formatter import skills_to_wide, _DEFAULT_CAT9_ZH
from src.utils.progress import ProgressTracker, ProgressSnapshot


def run_smoke_test(run_number: int, pipeline: HybridJobSkillPipeline):
    print(f"\n==================================================")
    print(f"  RUNNING SMOKE TEST #{run_number}")
    print(f"==================================================")

    # 1. File Upload & Parsing
    t0 = time.time()
    with open(DEMO_FILE, "rb") as f:
        file_bytes = f.read()
    t_read_start = time.time()
    df_raw = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
    t_file_parse = time.time() - t_read_start
    print(f"1. File recognized: '{os.path.basename(DEMO_FILE)}' ({len(file_bytes)/1024:.1f} KB)")
    print(f"   File parsed in: {t_file_parse:.4f}s ({len(df_raw)} jobs)")

    # 2. Schema Validation
    title_candidates = ["職位名稱", "104職位名稱", "job_title"]
    desc_candidates = ["職位描述", "job_desc"]
    has_title = any(c in df_raw.columns for c in title_candidates)
    has_desc = any(c in df_raw.columns for c in desc_candidates)
    schema_ok = has_title and has_desc
    print(f"2. Column/Schema validation: {'PASSED' if schema_ok else 'FAILED'} (has_title={has_title}, has_desc={has_desc})")

    # 3. Fast Extraction Execution with Progress Tracking
    print(f"3. Executing Fast Extraction...")
    progress_events = []

    def on_progress(snap: ProgressSnapshot):
        progress_events.append({
            "processed": snap.processed,
            "total": snap.total,
            "percent": snap.percent,
            "stage": snap.stage,
            "speed": snap.formatted_speed,
            "eta": snap.formatted_eta,
            "elapsed": snap.formatted_elapsed,
        })

    t_run_start = time.time()
    long_df, wide_df, stats = pipeline.process_dataframe(
        df_raw,
        county="彰化縣",
        month="202608",
        progress_callback=on_progress,
    )
    t_total_run = time.time() - t_run_start

    print(f"   Total run time: {t_run_start:.2f}s -> {t_total_run:.4f}s ({len(df_raw)/t_total_run:.1f} jobs/s)")
    print(f"   Progress events captured: {len(progress_events)}")
    if progress_events:
        first_evt = progress_events[0]
        mid_evt = progress_events[len(progress_events) // 2]
        last_evt = progress_events[-1]
        print(f"   Sample progress updates:")
        print(f"     Start: {first_evt['processed']}/{first_evt['total']} ({first_evt['percent']}%) - {first_evt['stage']}")
        print(f"     Mid:   {mid_evt['processed']}/{mid_evt['total']} ({mid_evt['percent']}%) - {mid_evt['stage']} - {mid_evt['speed']} - ETA {mid_evt['eta']}")
        print(f"     End:   {last_evt['processed']}/{last_evt['total']} ({last_evt['percent']}%) - {last_evt['stage']} - {last_evt['speed']}")

    # 4. Wide output generation & persistence
    t0 = time.time()
    out_buffer = io.BytesIO()
    with pd.ExcelWriter(out_buffer, engine="openpyxl") as writer:
        wide_df.to_excel(writer, index=False, sheet_name="9大類技能寬表格")
    excel_bytes = out_buffer.getvalue()
    t_excel_export = time.time() - t0
    print(f"4. Excel export generated: {len(excel_bytes)/1024:.1f} KB in {t_excel_export:.4f}s")

    # 5. Open and validate downloaded Excel
    t0 = time.time()
    df_downloaded = pd.read_excel(io.BytesIO(excel_bytes), sheet_name="9大類技能寬表格")
    t_verify_read = time.time() - t0

    # Validation Checks
    row_count_ok = (len(df_downloaded) == len(df_raw))
    id_order_ok = (list(df_downloaded["ID"].astype(str)) == list(df_raw["工作編號"].astype(str)))
    skills_count_col_ok = ("技能數" in df_downloaded.columns)
    skills_zh_col_ok = ("技能_中文" in df_downloaded.columns)

    target_cat_cols = [
        "認知技能", "社交技能", "特質技能", "財務技能", "管理技能",
        "數位技能", "技術技能", "電腦技能", "AI技能", "其他技能",
    ]
    all_cats_ok = all(col in df_downloaded.columns for col in target_cat_cols)

    print(f"5. Downloaded Excel Validation:")
    print(f"   - Row count: {len(df_downloaded)} == {len(df_raw)} ({'OK' if row_count_ok else 'FAIL'})")
    print(f"   - Job ID ordering: {'OK' if id_order_ok else 'FAIL'}")
    print(f"   - 技能數 column: {'OK' if skills_count_col_ok else 'FAIL'} (Max={df_downloaded['技能數'].max()}, Mean={df_downloaded['技能數'].mean():.2f})")
    print(f"   - 技能_中文 column: {'OK' if skills_zh_col_ok else 'FAIL'}")
    print(f"   - All 10 category columns: {'OK' if all_cats_ok else 'FAIL'}")

    return {
        "file_parse_sec": t_file_parse,
        "total_run_sec": t_total_run,
        "excel_export_sec": t_excel_export,
        "row_count": len(df_downloaded),
        "columns": list(df_downloaded.columns),
        "all_valid": row_count_ok and id_order_ok and skills_count_col_ok and skills_zh_col_ok and all_cats_ok,
    }


def main():
    print("Initializing Pipeline for Demo (Fast Extraction Mode)...")
    t0 = time.time()
    pipeline = HybridJobSkillPipeline(
        lexicon_path=LEXICON_PATH,
        verifier_provider="mock",
        grounder_provider="mock",
        enable_fn_recovery=False,
        bypass_verification=True,
        disable_retrieval=True,
    )
    t_init = time.time() - t0
    print(f"Pipeline Initialized in: {t_init:.2f}s")

    # Smoke Test #1
    res1 = run_smoke_test(1, pipeline)

    # Smoke Test #2 (consecutive run to test caching, state, progress)
    res2 = run_smoke_test(2, pipeline)

    print(f"\n==================================================")
    print(f"  SMOKE TEST SUMMARY")
    print(f"==================================================")
    print(f"Smoke Test #1 All Valid: {res1['all_valid']} (Run Time: {res1['total_run_sec']:.2f}s)")
    print(f"Smoke Test #2 All Valid: {res2['all_valid']} (Run Time: {res2['total_run_sec']:.2f}s)")

    if res1["all_valid"] and res2["all_valid"]:
        print("\n>>> ALL TESTS PASSED: READY FOR DEMO RECORDING <<<")


if __name__ == "__main__":
    main()
