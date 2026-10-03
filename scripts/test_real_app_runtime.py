"""Simulate the exact Streamlit app runtime execution twice consecutively.
Tests the exact batch processing path in app.py with data/demo/demo_彰化縣_202608_500.xlsx.
"""

import os
import sys
import io
import time
import pandas as pd

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

DEMO_FILE = os.path.join(REPO_ROOT, "data/demo/demo_彰化縣_202608_500.xlsx")
LEXICON_PATH = os.path.join(REPO_ROOT, "詞庫skill_lexicon_v13_20260918.xlsx")

import app
from src.utils.progress import ProgressSnapshot, ProgressTracker


def simulate_app_batch_run(run_num: int, pipeline, df_raw):
    print(f"\n--- Simulation Run #{run_num} ---")
    
    # Track progress callback events
    callback_stages = []
    
    # Exact callback implementation from app.py line 349
    def on_batch_progress(snapshot: ProgressSnapshot):
        current_stage = snapshot.stage
        if snapshot.percent >= 100 or snapshot.stage == ProgressTracker.STAGE_AGGREGATING:
            current_stage = "正在產生輸出表格..."
        callback_stages.append({
            "processed": snapshot.processed,
            "total": snapshot.total,
            "percent": snapshot.percent,
            "stage": current_stage,
            "speed": snapshot.formatted_speed,
            "eta": snapshot.formatted_eta,
            "elapsed": snapshot.formatted_elapsed,
        })

    t0 = time.time()
    # Exact call from app.py line 363
    long_df, wide_df, stats = pipeline.process_dataframe(
        df_raw,
        county="彰化縣",
        month="202608",
        progress_callback=on_batch_progress,
    )
    batch_duration = time.time() - t0

    print(f"Run #{run_num} completed in {batch_duration:.4f}s ({len(df_raw)/batch_duration:.1f} jobs/s)")
    print(f"Total callback snapshots captured: {len(callback_stages)}")
    
    # Verify aggregation stage was captured
    stages_seen = [evt["stage"] for evt in callback_stages]
    has_agg_or_100 = any(
        evt["stage"] == "正在產生輸出表格..." or evt["percent"] >= 100
        for evt in callback_stages
    )
    print(f"Aggregation / 100% stage reached: {has_agg_or_100}")
    print(f"Final snapshot: {callback_stages[-1]}")

    # Validate output
    assert len(wide_df) == len(df_raw), f"Expected {len(df_raw)} rows, got {len(wide_df)}"
    assert "技能數" in wide_df.columns
    assert "技能_中文" in wide_df.columns
    print(f"Output verified: {len(wide_df)} rows, {len(wide_df.columns)} columns")
    return True


def main():
    print("Loading demo dataset: " + DEMO_FILE)
    df_raw = pd.read_excel(DEMO_FILE)
    print(f"Loaded {len(df_raw)} jobs.")

    print("Initializing demo pipeline (Fast Extraction Mode)...")
    pipeline = app.get_pipeline(lexicon_path=LEXICON_PATH, is_fast_mode=True)

    # Run 1
    ok1 = simulate_app_batch_run(1, pipeline, df_raw)

    # Run 2 (same process / session)
    ok2 = simulate_app_batch_run(2, pipeline, df_raw)

    print("\n==================================================")
    print(f"Run #1: {'PASS' if ok1 else 'FAIL'}")
    print(f"Run #2: {'PASS' if ok2 else 'FAIL'}")
    print("==================================================")

    if ok1 and ok2:
        print(">>> DEMO RUNTIME VERIFICATION PASSED (TWICE CONSECUTIVELY) <<<")


if __name__ == "__main__":
    main()
