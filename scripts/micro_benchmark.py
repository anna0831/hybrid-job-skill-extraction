"""Micro-benchmark and profiler on real 104 dataset (cleaned_彰化縣_202608.xlsx).

Evaluates:
1. Pandas iteration: iterrows() vs itertuples() vs pre-extracted lists
2. Wide-table aggregation: current groupby.apply(iterrows) vs pre-grouped dict aggregation
3. Progress callback overhead: progress_callback=None vs active callback
4. Residual recovery routing analysis: how many jobs/segments enter recovery
5. Full profiling with cProfile on 2,000 real jobs
"""

import os
import sys
import time
import cProfile
import pstats
import io
import json
import pandas as pd
import numpy as np
from typing import Dict, List, Any

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

DATASET_PATH = os.path.join(REPO_ROOT, "dataset/cleaned_彰化縣_202608.xlsx")
LEXICON_PATH = os.path.join(REPO_ROOT, "lexicon/sample/mini_skill_lexicon.csv")
RULES_PATH = os.path.join(REPO_ROOT, "configs/rules.yaml")
SYNONYMS_PATH = os.path.join(REPO_ROOT, "configs/synonyms.yaml")

from src.lexicon.loader import LexiconLoader
from src.ac_matcher.engine import ACMatcher
from src.routing.router import RiskBasedRouter
from src.hybrid_pipeline import HybridJobSkillPipeline
from src.outputs.formatter import skills_to_wide, load_cat9_mapping, _DEFAULT_CAT9_ZH
from src.utils.progress import ProgressTracker, ProgressSnapshot

def test_pandas_iteration(df: pd.DataFrame, n_rows: int = 12816):
    print(f"\n--- 1. Pandas Iteration Benchmark ({n_rows} rows) ---")
    sub_df = df.iloc[:n_rows]

    # A. Current iterrows()
    t0 = time.time()
    count_a = 0
    for i, row in sub_df.iterrows():
        jid = str(row.get("工作編號", ""))
        title = str(row.get("104職位名稱", ""))
        desc = str(row.get("職位描述", ""))
        count_a += 1
    t_iterrows = time.time() - t0

    # B. itertuples()
    t0 = time.time()
    count_b = 0
    # Map column names to indices
    col_map = {col: idx for idx, col in enumerate(sub_df.columns)}
    id_idx = col_map.get("工作編號", 0)
    title_idx = col_map.get("104職位名稱", 1)
    desc_idx = col_map.get("職位描述", 2)
    for row in sub_df.itertuples(index=False):
        jid = str(row[id_idx])
        title = str(row[title_idx])
        desc = str(row[desc_idx])
        count_b += 1
    t_itertuples = time.time() - t0

    # C. Pre-extracted Python lists / arrays
    t0 = time.time()
    count_c = 0
    ids = sub_df["工作編號"].astype(str).tolist()
    titles = sub_df["104職位名稱"].fillna("").astype(str).tolist()
    descs = sub_df["職位描述"].fillna("").astype(str).tolist()
    for jid, title, desc in zip(ids, titles, descs):
        count_c += 1
    t_pre_extracted = time.time() - t0

    print(f"  iterrows():         {t_iterrows:.3f}s ({n_rows/t_iterrows:.0f} rows/s)")
    print(f"  itertuples():       {t_itertuples:.3f}s ({n_rows/t_itertuples:.0f} rows/s, speedup: {t_iterrows/t_itertuples:.1f}x)")
    print(f"  pre-extracted zip:  {t_pre_extracted:.3f}s ({n_rows/t_pre_extracted:.0f} rows/s, speedup: {t_iterrows/t_pre_extracted:.1f}x)")

def test_wide_aggregation(long_df: pd.DataFrame, raw_df: pd.DataFrame):
    print(f"\n--- 2. Wide Table Aggregation Benchmark ({len(long_df)} skill records across {len(raw_df)} jobs) ---")
    
    # Current groupby.apply(iterrows)
    t0 = time.time()
    wide_current = skills_to_wide(long_df, raw_df)
    t_current = time.time() - t0

    # Alternative: Fast dictionary-based aggregation
    t0 = time.time()
    # Group in pure Python
    cat_map = _DEFAULT_CAT9_ZH
    grouped_skills = {}
    grouped_cat_skills = {zh: {} for zh in cat_map.values()}

    for row in long_df.itertuples(index=False):
        # row fields: ID, 縣市, 月份, skill_id, skill_name, skill_name_zh, ...
        # Assume standard columns
        r_dict = row._asdict() if hasattr(row, '_asdict') else dict(zip(long_df.columns, row))
        jid = str(r_dict.get("ID", ""))
        szh = str(r_dict.get("SKILL_NAME_ZH", r_dict.get("skill_name_zh", "")))
        cat = str(r_dict.get("SKILL_CAT9", r_dict.get("skill_category", "Unclassified")))

        if jid not in grouped_skills:
            grouped_skills[jid] = []
        grouped_skills[jid].append(szh)

        zh_col = cat_map.get(cat, "其他技能")
        if jid not in grouped_cat_skills[zh_col]:
            grouped_cat_skills[zh_col][jid] = []
        grouped_cat_skills[zh_col][jid].append(szh)

    # Build agg dataframe directly
    all_jids = list(grouped_skills.keys())
    agg_records = []
    for jid in all_jids:
        rec = {
            "ID": jid,
            "技能數": len(grouped_skills[jid]),
            "技能_中文": "｜".join(grouped_skills[jid]),
        }
        for zh_col in cat_map.values():
            rec[zh_col] = "｜".join(grouped_cat_skills[zh_col].get(jid, []))
        agg_records.append(rec)
    
    agg_df_fast = pd.DataFrame(agg_records)
    
    # Merge back to desc
    desc_cols = ["工作編號", "資料月份", "刊登日期", "工作角色", "104職位名稱", "104職位名稱碼", "職位描述", "工作技能", "電腦工具"]
    desc_cols = [c for c in desc_cols if c in raw_df.columns]
    desc = raw_df[desc_cols].copy()
    desc["ID"] = desc["工作編號"].astype(str)
    wide_fast = desc.merge(agg_df_fast, on="ID", how="left")
    t_fast = time.time() - t0

    print(f"  Current groupby.apply(iterrows): {t_current:.3f}s")
    print(f"  Fast dict-based aggregation:      {t_fast:.3f}s (speedup: {t_current/t_fast:.1f}x)")

    # Verify output equality
    cols_to_check = ["技能數", "技能_中文"] + list(cat_map.values())
    equal = True
    for c in cols_to_check:
        if c in wide_current.columns and c in wide_fast.columns:
            s1 = wide_current[c].fillna("").tolist()
            s2 = wide_fast[c].fillna("").tolist()
            if s1 != s2:
                equal = False
                print(f"  Difference found in column: {c}")
                break
    print(f"  Output equivalence: {'100% MATCH' if equal else 'MISMATCH'}")

def test_progress_overhead(df: pd.DataFrame, n_jobs: int = 2000):
    print(f"\n--- 3. Progress Callback Overhead ({n_jobs} jobs) ---")
    sub_df = df.iloc[:n_jobs].copy()

    pipeline = HybridJobSkillPipeline(
        lexicon_path=LEXICON_PATH,
        enable_fn_recovery=False,
        bypass_verification=True,
    )

    # Without callback
    t0 = time.time()
    pipeline.process_dataframe(sub_df, progress_callback=None)
    t_no_callback = time.time() - t0

    # With callback
    callback_calls = 0
    def dummy_callback(snap: ProgressSnapshot):
        nonlocal callback_calls
        callback_calls += 1

    t0 = time.time()
    pipeline.process_dataframe(sub_df, progress_callback=dummy_callback)
    t_with_callback = time.time() - t0

    diff = t_with_callback - t_no_callback
    pct = (diff / t_no_callback) * 100 if t_no_callback > 0 else 0.0

    print(f"  Without progress_callback: {t_no_callback:.3f}s ({n_jobs/t_no_callback:.0f} jobs/s)")
    print(f"  With progress_callback:    {t_with_callback:.3f}s ({n_jobs/t_with_callback:.0f} jobs/s)")
    print(f"  Callback invocations:      {callback_calls}")
    print(f"  Difference:                {diff:+.3f}s ({pct:+.2f}%)")

def test_residual_routing_analysis(df: pd.DataFrame, n_jobs: int = 500):
    print(f"\n--- 4. Residual Recovery Routing Analysis ({n_jobs} jobs) ---")
    sub_df = df.iloc[:n_jobs].copy()

    pipeline = HybridJobSkillPipeline(
        lexicon_path=LEXICON_PATH,
        enable_fn_recovery=True,
        verifier_provider="mock",
        grounder_provider="mock",
    )

    jobs_entering_recovery = 0
    total_residuals = 0
    bm25_queries = 0
    dense_queries = 0
    verifier_calls = 0

    t0 = time.time()
    for i, row in sub_df.iterrows():
        jid = str(row.get("工作編號", ""))
        title = str(row.get("104職位名稱", ""))
        desc = str(row.get("職位描述", ""))
        tools = str(row.get("電腦工具", ""))
        skills = str(row.get("工作技能", ""))

        final_skills, routing_res, v_recs = pipeline.extract_job_skills(
            job_id=jid,
            job_title=title,
            job_desc=desc,
            tools=tools,
            job_skills=skills,
        )

        if routing_res.fn_recovery_result:
            jobs_entering_recovery += 1
            n_res = len(routing_res.fn_recovery_result.semantic_items)
            total_residuals += n_res
            bm25_queries += n_res
            dense_queries += n_res
            verifier_calls += n_res

    t_total = time.time() - t0

    print(f"  Total jobs tested:            {n_jobs}")
    print(f"  Jobs entering recovery:       {jobs_entering_recovery} ({jobs_entering_recovery/n_jobs*100:.1f}%)")
    print(f"  Total residual segments:      {total_residuals}")
    print(f"  Average residual segs/job:    {total_residuals/max(n_jobs, 1):.2f}")
    print(f"  Total BM25 queries:           {bm25_queries}")
    print(f"  Total Dense queries:          {dense_queries}")
    print(f"  Total Verifier calls:         {verifier_calls}")
    print(f"  Total runtime for {n_jobs} jobs: {t_total:.2f}s ({t_total/n_jobs*1000:.1f} ms/job)")
    print(f"  Extrapolated to 12,816 jobs:  {t_total * (12816 / n_jobs):.1f}s ({t_total * (12816 / n_jobs) / 60:.1f} min)")

def main():
    print(f"Loading dataset from: {DATASET_PATH}")
    t0 = time.time()
    df = pd.read_excel(DATASET_PATH)
    print(f"Loaded {len(df)} jobs in {time.time()-t0:.2f}s")

    # 1. Pandas Iteration Benchmark
    test_pandas_iteration(df, n_rows=12816)

    # 2. Wide Table Aggregation Benchmark
    # First generate long_df using AC-only
    pipeline = HybridJobSkillPipeline(
        lexicon_path=LEXICON_PATH,
        enable_fn_recovery=False,
        bypass_verification=True,
    )
    print("\nGenerating long_df for wide table benchmark on 2,000 jobs...")
    long_df_2k, _, _ = pipeline.process_dataframe(df.iloc[:2000], progress_callback=None)
    test_wide_aggregation(long_df_2k, df.iloc[:2000])

    # 3. Progress Overhead Benchmark
    test_progress_overhead(df, n_jobs=2000)

    # 4. Residual Recovery Routing Analysis
    test_residual_routing_analysis(df, n_jobs=500)

if __name__ == "__main__":
    main()
