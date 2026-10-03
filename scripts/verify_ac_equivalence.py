"""Verify AC output equivalence between standalone logic and Hybrid ACMatcher
using the same lexicon (mini_skill_lexicon.csv) on 12,816 jobs of cleaned_彰化縣_202608.xlsx.
"""

import os
import sys
import time
import pandas as pd

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

DATASET_PATH = os.path.join(REPO_ROOT, "dataset/cleaned_彰化縣_202608.xlsx")
LEXICON_PATH = os.path.join(REPO_ROOT, "詞庫skill_lexicon_v13_20260918.xlsx")
RULES_PATH = os.path.join(REPO_ROOT, "configs/rules.yaml")
SYNONYMS_PATH = os.path.join(REPO_ROOT, "configs/synonyms.yaml")

import scratch_standalone as standalone
from src.hybrid_pipeline import HybridJobSkillPipeline

def main():
    print(f"Reading dataset: {DATASET_PATH}...")
    df = pd.read_excel(DATASET_PATH)
    n_jobs = len(df)
    print(f"Loaded {n_jobs} jobs.")

    # 1. Standalone AC
    print("\n--- Running Standalone AC ---")
    t0 = time.time()
    automaton = standalone.load_automaton(LEXICON_PATH)
    t_auto = time.time() - t0
    
    t0 = time.time()
    long_df_standalone = standalone.process_county(df, automaton, "彰化縣", "202608")
    t_match_standalone = time.time() - t0
    pairs_standalone = set(zip(long_df_standalone["ID"].astype(str), long_df_standalone["SKILL_ID"].astype(str)))
    print(f"Standalone: {len(long_df_standalone)} skill records, {len(pairs_standalone)} unique (job_id, skill_id) pairs in {t_match_standalone:.2f}s ({n_jobs/t_match_standalone:.1f} jobs/s)")

    # 2. Hybrid Pipeline AC-only
    print("\n--- Running Hybrid Pipeline AC-only ---")
    t0 = time.time()
    pipeline = HybridJobSkillPipeline(
        lexicon_path=LEXICON_PATH,
        rules_path=RULES_PATH,
        synonyms_path=SYNONYMS_PATH,
        enable_fn_recovery=False,
        bypass_verification=True,
    )
    t_pipe_init = time.time() - t0

    t0 = time.time()
    long_df_hybrid, wide_df_hybrid, _ = pipeline.process_dataframe(
        df,
        county="彰化縣",
        month="202608",
        progress_callback=None,
    )
    t_match_hybrid = time.time() - t0
    pairs_hybrid = set(zip(long_df_hybrid["ID"].astype(str), long_df_hybrid["SKILL_ID"].astype(str)))
    print(f"Hybrid AC:  {len(long_df_hybrid)} skill records, {len(pairs_hybrid)} unique (job_id, skill_id) pairs in {t_match_hybrid:.2f}s ({n_jobs/t_match_hybrid:.1f} jobs/s)")

    # 3. Equivalence Check
    intersect = pairs_standalone & pairs_hybrid
    only_standalone = pairs_standalone - pairs_hybrid
    only_hybrid = pairs_hybrid - pairs_standalone
    union = pairs_standalone | pairs_hybrid
    agreement = len(intersect) / len(union) if union else 1.0

    print(f"\n================ AC OUTPUT EQUIVALENCE ================")
    print(f"Standalone pair count: {len(pairs_standalone)}")
    print(f"Hybrid pair count:     {len(pairs_hybrid)}")
    print(f"Intersection:          {len(intersect)}")
    print(f"Only Standalone:       {len(only_standalone)}")
    print(f"Only Hybrid:           {len(only_hybrid)}")
    print(f"Exact Agreement:       {agreement:.4%}")

    if only_standalone:
        print("\nFirst 10 Only Standalone:", list(only_standalone)[:10])
    if only_hybrid:
        print("\nFirst 10 Only Hybrid:", list(only_hybrid)[:10])

if __name__ == "__main__":
    main()
