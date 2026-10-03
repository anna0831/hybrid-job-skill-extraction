"""Full Real-Data Regression and Performance Benchmark.
Using dataset/cleaned_彰化縣_202608.xlsx and 詞庫skill_lexicon_v13_20260918.xlsx.
"""

import os
import sys
import time
import pandas as pd
import numpy as np

REPO_ROOT = "/Users/anna/Desktop/Job_Description_fetch"
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

DATASET_PATH = os.path.join(REPO_ROOT, "dataset/cleaned_彰化縣_202608.xlsx")
LEXICON_PATH = os.path.join(REPO_ROOT, "詞庫skill_lexicon_v13_20260918.xlsx")

from src.lexicon.loader import LexiconLoader
from src.hybrid_pipeline import HybridJobSkillPipeline
from src.outputs.formatter import skills_to_wide, _DEFAULT_CAT9_ZH
import scratch_standalone as standalone


def legacy_skills_to_wide(long_df: pd.DataFrame, raw_df: pd.DataFrame, mapping=_DEFAULT_CAT9_ZH) -> pd.DataFrame:
    raw_df = raw_df.copy()
    def find_col(candidates, default=""):
        for c in candidates:
            if c in raw_df.columns:
                return c
        return default

    id_col = find_col(["工作編號", "ID", "id"], default="id")
    raw_df["ID"] = raw_df[id_col].astype(str) if id_col in raw_df.columns else [f"JOB_{i}" for i in range(len(raw_df))]
    tool_col = find_col(["擅長工具", "電腦工具", "tools"], default="tools")
    title_col = find_col(["職位名稱", "104職位名稱", "job_title"], default="job_title")
    title_code_col = find_col(["職位名稱碼", "104職位名稱碼", "job_code"], default="job_code")
    desc_col = find_col(["職位描述", "job_desc"], default="job_desc")
    skill_col = find_col(["工作技能", "job_skills"], default="job_skills")

    if long_df.empty:
        empty_cols = ["ID", "技能數", "技能_中文"] + list(mapping.values())
        agg_df = pd.DataFrame(columns=empty_cols)
    else:
        def agg(group: pd.DataFrame) -> pd.Series:
            result = {
                "技能數": len(group),
                "技能_中文": "｜".join(group["SKILL_NAME_ZH"].astype(str)),
            }
            for en_cat, zh_col in mapping.items():
                skills_in_cat = "｜".join(
                    r["SKILL_NAME_ZH"]
                    for _, r in group.iterrows()
                    if r.get("SKILL_CAT9", "Unclassified") == en_cat
                )
                result[zh_col] = skills_in_cat
            return pd.Series(result)

        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            agg_df = long_df.groupby("ID").apply(agg, include_groups=False).reset_index()

    desc_cols = ["ID", "資料月份", "刊登日期", "工作角色", title_col, title_code_col, desc_col, skill_col, tool_col]
    desc_cols = [c for c in desc_cols if c in raw_df.columns]
    desc = raw_df[desc_cols]
    return desc.merge(agg_df, on="ID", how="left")


def main():
    print(f"Reading dataset: {DATASET_PATH}...")
    df = pd.read_excel(DATASET_PATH)
    n_jobs = len(df)
    print(f"Loaded {n_jobs} jobs.\n")

    # 1. Pipeline Initialization Benchmark
    print("--- 1. Lexicon & Pipeline Initialization ---")
    t0 = time.time()
    pipeline = HybridJobSkillPipeline(
        lexicon_path=LEXICON_PATH,
        enable_fn_recovery=False,
        bypass_verification=True,
    )
    t_init = time.time() - t0
    print(f"Initialization Time: {t_init:.2f}s\n")

    # 2. AC Extraction Benchmark
    print("--- 2. AC Extraction & Column Iteration ---")
    t0 = time.time()
    long_df, wide_df_fast, _ = pipeline.process_dataframe(
        df,
        county="彰化縣",
        month="202608",
        progress_callback=None,
    )
    t_ac_and_agg = time.time() - t0
    print(f"AC + Aggregation Time: {t_ac_and_agg:.2f}s ({n_jobs / t_ac_and_agg:.1f} jobs/s)")

    unique_pairs = set(zip(long_df["ID"].astype(str), long_df["SKILL_ID"].astype(str)))
    print(f"Total long_df rows:    {len(long_df):,}")
    print(f"Unique (ID, Skill_ID): {len(unique_pairs):,}")

    # 3. Wide Table Aggregation Comparison (Old vs New)
    print("\n--- 3. Wide Table Aggregation Benchmark & Equivalence ---")
    t0 = time.time()
    wide_df_fast_re = skills_to_wide(long_df, df)
    t_fast_agg = time.time() - t0
    print(f"Fast Aggregation Time: {t_fast_agg:.4f}s")

    print("Running Legacy Aggregation on 12,816 jobs for exact verification...")
    t0 = time.time()
    wide_df_legacy = legacy_skills_to_wide(long_df, df)
    t_legacy_agg = time.time() - t0
    print(f"Legacy Aggregation Time: {t_legacy_agg:.2f}s")
    print(f"Speedup: {t_legacy_agg / t_fast_agg:.1f}x")

    # Check DataFrame equality
    try:
        pd.testing.assert_frame_equal(wide_df_legacy, wide_df_fast_re, check_dtype=True)
        print("Wide DataFrame Exact Equality: 100.0000% MATCH (assert_frame_equal PASSED)")
    except AssertionError as e:
        print(f"AssertionError: {e}")

    # Column-by-column verification
    target_cols = ["技能數", "技能_中文", "認知技能", "社交技能", "特質技能", "財務技能", "管理技能", "數位技能", "技術技能", "電腦技能", "AI技能", "其他技能"]
    all_cols_match = True
    for col in target_cols:
        if col not in wide_df_legacy.columns or col not in wide_df_fast_re.columns:
            print(f"Missing column: {col}")
            all_cols_match = False
            continue
        s_leg = wide_df_legacy[col].fillna("")
        s_fast = wide_df_fast_re[col].fillna("")
        match_rate = (s_leg == s_fast).mean()
        if match_rate < 1.0:
            print(f"Column '{col}' mismatch: {match_rate:.4%}")
            all_cols_match = False
    if all_cols_match:
        print("All 12 target columns verified 100.0000% EQUAL.")

    # 4. Fast Core Benchmark (Target: <= 15s for 12,816 jobs)
    print("\n--- 4. Fast Core Benchmark (Target: <= 15s) ---")
    t0 = time.time()
    # Fast Core: matcher + fast aggregation
    def find_col(candidates, default=""):
        for c in candidates:
            if c in df.columns:
                return c
        return default

    id_col = find_col(["工作編號", "ID", "id"], default="id")
    title_col = find_col(["職位名稱", "104職位名稱", "job_title"], default="job_title")
    desc_col = find_col(["職位描述", "job_desc"], default="job_desc")
    tool_col = find_col(["擅長工具", "電腦工具", "tools"], default="tools")
    skill_col = find_col(["工作技能", "job_skills"], default="job_skills")

    ids = df[id_col].astype(str).tolist() if id_col in df.columns else [f"JOB_{i}" for i in range(n_jobs)]
    titles = df[title_col].fillna("").astype(str).tolist() if title_col in df.columns else [""] * n_jobs
    descs = df[desc_col].fillna("").astype(str).tolist() if desc_col in df.columns else [""] * n_jobs
    tools_list = df[tool_col].fillna("").astype(str).tolist() if tool_col in df.columns else [""] * n_jobs
    skills_list = df[skill_col].fillna("").astype(str).tolist() if skill_col in df.columns else [""] * n_jobs

    records = []
    matcher = pipeline.matcher
    for jid, title, desc, tools, skills in zip(ids, titles, descs, tools_list, skills_list):
        matches = matcher.match_texts([f"{title} {desc}", skills, tools])
        for m in matches:
            records.append({
                "ID": jid,
                **m.to_dict(),
            })
    long_df_core = pd.DataFrame(records)
    wide_df_core = skills_to_wide(long_df_core, df)
    t_fast_core = time.time() - t0
    print(f"Fast Core (AC Extraction + Fast Wide Aggregation): {t_fast_core:.2f}s for {n_jobs} jobs ({n_jobs/t_fast_core:.1f} jobs/s)")
    print(f"Target <= 15s achieved: {t_fast_core <= 15.0} ({t_fast_core:.2f}s)")


if __name__ == "__main__":
    main()
