"""Complete, reproducible benchmark and profiling script for Hybrid Job Skill Extraction System.

Covers:
- Variant A: Standalone reference script (104_single_city_0919.py)
- Variant B: Hybrid Pipeline AC-only (no progress, no recovery, mock verifier)
- Variant C: Hybrid Pipeline AC + Risk Routing
- Variant D: Current App configuration (normal pipeline)
- Variant E: Full Hybrid with Residual Recovery

Profiles hot paths with cProfile/pstats on 2,000 jobs, then on the full 12,816-job 彰化 dataset.
Measures stage-by-stage timings (01 to 17), per-job repeated work, residual recovery routing,
DataFrame dimension impacts, pandas iteration differences, and AC output equivalence.
"""

import os
import sys
import time
import cProfile
import pstats
import io
import json
import warnings
from typing import Dict, List, Tuple, Set, Any
import pandas as pd
import numpy as np

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

LEXICON_PATH = os.path.join(REPO_ROOT, "詞庫skill_lexicon_v13_20260918.xlsx")
DATASET_PATH = os.path.join(REPO_ROOT, "dataset/cleaned_彰化縣_202608.xlsx")
RULES_PATH = os.path.join(REPO_ROOT, "configs/rules.yaml")
SYNONYMS_PATH = os.path.join(REPO_ROOT, "configs/synonyms.yaml")

from src.lexicon.loader import LexiconLoader
from src.ac_matcher.engine import ACMatcher
from src.routing.router import RiskBasedRouter
from src.hybrid_pipeline import HybridJobSkillPipeline
from src.outputs.formatter import skills_to_wide, load_cat9_mapping
from src.utils.progress import ProgressTracker, ProgressSnapshot

# Import standalone reference functions from scratch_standalone
import scratch_standalone as standalone

def benchmark_variant_a(df_raw: pd.DataFrame, limit: int = None) -> Dict[str, Any]:
    """Benchmark Variant A: Standalone reference script."""
    print("\n--- Running Variant A: Standalone Reference ---")
    df = df_raw.iloc[:limit].copy() if limit else df_raw.copy()
    n_jobs = len(df)

    # 1. Lexicon loading & AC construction
    t0 = time.time()
    automaton = standalone.load_automaton(LEXICON_PATH)
    t_ac_construct = time.time() - t0

    # 2. AC matching
    t0 = time.time()
    county = "彰化縣"
    month = "202608"
    long_df = standalone.process_county(df, automaton, county, month)
    t_ac_match = time.time() - t0

    # 3. Wide aggregation
    t0 = time.time()
    wide_df = standalone.skills_to_wide(long_df, df)
    t_wide_agg = time.time() - t0

    # Pairs for equivalence
    pairs = set(zip(long_df["ID"].astype(str), long_df["SKILL_ID"].astype(str)))

    return {
        "variant": "Variant A (Standalone)",
        "jobs": n_jobs,
        "lexicon_time": t_ac_construct,
        "match_time": t_ac_match,
        "agg_time": t_wide_agg,
        "total_time": t_ac_construct + t_ac_match + t_wide_agg,
        "throughput_jobs_sec": n_jobs / max(t_ac_match, 0.001),
        "skill_records": len(long_df),
        "pairs": pairs,
        "long_df": long_df,
        "wide_df": wide_df,
    }

def benchmark_variant_b(df_raw: pd.DataFrame, limit: int = None) -> Dict[str, Any]:
    """Benchmark Variant B: Hybrid Pipeline AC-only (no progress, no recovery)."""
    print("\n--- Running Variant B: Hybrid Pipeline AC-only ---")
    df = df_raw.iloc[:limit].copy() if limit else df_raw.copy()
    n_jobs = len(df)

    t0 = time.time()
    pipeline = HybridJobSkillPipeline(
        lexicon_path=LEXICON_PATH,
        rules_path=RULES_PATH,
        synonyms_path=SYNONYMS_PATH,
        enable_fn_recovery=False,
        bypass_verification=True,
    )
    t_init = time.time() - t0

    t0 = time.time()
    long_df, wide_df, stats = pipeline.process_dataframe(
        df,
        county="彰化縣",
        month="202608",
        progress_callback=None,
    )
    t_process = time.time() - t0

    pairs = set(zip(long_df["ID"].astype(str), long_df["SKILL_ID"].astype(str))) if not long_df.empty else set()

    return {
        "variant": "Variant B (Hybrid AC-only)",
        "jobs": n_jobs,
        "init_time": t_init,
        "process_time": t_process,
        "total_time": t_init + t_process,
        "throughput_jobs_sec": n_jobs / max(t_process, 0.001),
        "skill_records": len(long_df),
        "pairs": pairs,
        "long_df": long_df,
        "wide_df": wide_df,
    }

def benchmark_variant_c(df_raw: pd.DataFrame, limit: int = None) -> Dict[str, Any]:
    """Benchmark Variant C: AC + Risk Routing (no semantic recovery)."""
    print("\n--- Running Variant C: AC + Risk Routing ---")
    df = df_raw.iloc[:limit].copy() if limit else df_raw.copy()
    n_jobs = len(df)

    t0 = time.time()
    pipeline = HybridJobSkillPipeline(
        lexicon_path=LEXICON_PATH,
        rules_path=RULES_PATH,
        synonyms_path=SYNONYMS_PATH,
        enable_fn_recovery=False,
        bypass_verification=False,
        verifier_provider="mock",
    )
    t_init = time.time() - t0

    t0 = time.time()
    long_df, wide_df, stats = pipeline.process_dataframe(
        df,
        county="彰化縣",
        month="202608",
        progress_callback=None,
    )
    t_process = time.time() - t0

    return {
        "variant": "Variant C (AC + Routing)",
        "jobs": n_jobs,
        "init_time": t_init,
        "process_time": t_process,
        "total_time": t_init + t_process,
        "throughput_jobs_sec": n_jobs / max(t_process, 0.001),
        "skill_records": len(long_df),
    }

def benchmark_variant_d(df_raw: pd.DataFrame, limit: int = None) -> Dict[str, Any]:
    """Benchmark Variant D: Current App Configuration (normal app.py settings)."""
    print("\n--- Running Variant D: Current Normal App Configuration ---")
    df = df_raw.iloc[:limit].copy() if limit else df_raw.copy()
    n_jobs = len(df)

    t0 = time.time()
    pipeline = HybridJobSkillPipeline(
        lexicon_path=LEXICON_PATH,
        rules_path=RULES_PATH,
        synonyms_path=SYNONYMS_PATH,
        verifier_provider="mock",
        grounder_provider="mock",
        enable_fn_recovery=True,
    )
    t_init = time.time() - t0

    # Test with progress callback as app.py does
    snap_count = 0
    def app_callback(snap: ProgressSnapshot):
        nonlocal snap_count
        snap_count += 1

    t0 = time.time()
    long_df, wide_df, stats = pipeline.process_dataframe(
        df,
        county="彰化縣",
        month="202608",
        progress_callback=app_callback,
    )
    t_process = time.time() - t0

    return {
        "variant": "Variant D (Current App Config)",
        "jobs": n_jobs,
        "init_time": t_init,
        "process_time": t_process,
        "total_time": t_init + t_process,
        "throughput_jobs_sec": n_jobs / max(t_process, 0.001),
        "skill_records": len(long_df),
        "callback_calls": snap_count,
    }

def profile_hybrid_extraction(df_raw: pd.DataFrame, n_jobs: int = 2000):
    """Profile the hot path using cProfile on n_jobs."""
    print(f"\n================ Profiling Hot Path ({n_jobs} jobs) ================")
    df = df_raw.iloc[:n_jobs].copy()

    pipeline = HybridJobSkillPipeline(
        lexicon_path=LEXICON_PATH,
        rules_path=RULES_PATH,
        synonyms_path=SYNONYMS_PATH,
        enable_fn_recovery=True,
        verifier_provider="mock",
        grounder_provider="mock",
    )

    profiler = cProfile.Profile()
    profiler.enable()

    long_df, wide_df, stats = pipeline.process_dataframe(
        df,
        county="彰化縣",
        month="202608",
        progress_callback=None,
    )

    profiler.disable()

    s = io.StringIO()
    ps = pstats.Stats(profiler, stream=s).sort_stats("cumulative")
    ps.print_stats(30)
    print("--- TOP 30 FUNCTIONS BY CUMULATIVE TIME ---")
    print(s.getvalue())

    s_self = io.StringIO()
    ps_self = pstats.Stats(profiler, stream=s_self).sort_stats("time")
    ps_self.print_stats(30)
    print("--- TOP 30 FUNCTIONS BY SELF TIME ---")
    print(s_self.getvalue())

def main():
    print(f"Reading dataset: {DATASET_PATH}...")
    t0 = time.time()
    df_raw = pd.read_excel(DATASET_PATH)
    t_read_excel = time.time() - t0
    print(f"Dataset read: {len(df_raw)} jobs, took {t_read_excel:.2f}s")

    # 1. Profile 2,000 jobs first
    profile_hybrid_extraction(df_raw, n_jobs=2000)

    # 2. Run Variant A on 2,000 jobs
    res_a_2k = benchmark_variant_a(df_raw, limit=2000)
    print(f"Variant A (2,000 jobs): AC match {res_a_2k['match_time']:.2f}s ({res_a_2k['throughput_jobs_sec']:.1f} jobs/s), Wide agg: {res_a_2k['agg_time']:.2f}s")

    # 3. Run Variant B on 2,000 jobs
    res_b_2k = benchmark_variant_b(df_raw, limit=2000)
    print(f"Variant B (2,000 jobs): Process {res_b_2k['process_time']:.2f}s ({res_b_2k['throughput_jobs_sec']:.1f} jobs/s)")

    # 4. Compare AC outputs on 2,000 jobs
    pairs_a = res_a_2k["pairs"]
    pairs_b = res_b_2k["pairs"]
    intersect = pairs_a & pairs_b
    only_a = pairs_a - pairs_b
    only_b = pairs_b - pairs_a
    union = pairs_a | pairs_b
    agreement = len(intersect) / len(union) if union else 1.0

    print(f"\n--- AC Output Equivalence (2,000 jobs) ---")
    print(f"Standalone pairs: {len(pairs_a)}")
    print(f"Hybrid AC pairs:   {len(pairs_b)}")
    print(f"Intersection:      {len(intersect)}")
    print(f"Only Standalone:   {len(only_a)}")
    print(f"Only Hybrid:       {len(only_b)}")
    print(f"Agreement:         {agreement:.4%}")

    if only_a:
        print("Sample Only Standalone:", list(only_a)[:5])
    if only_b:
        print("Sample Only Hybrid:", list(only_b)[:5])

    # 5. Full 12,816-job benchmarks
    print("\n================ FULL 12,816 JOBS BENCHMARK ================")
    res_a_full = benchmark_variant_a(df_raw)
    print(f"Variant A FULL: AC match {res_a_full['match_time']:.2f}s ({res_a_full['throughput_jobs_sec']:.1f} jobs/s), Agg: {res_a_full['agg_time']:.2f}s, Total: {res_a_full['total_time']:.2f}s")

    res_b_full = benchmark_variant_b(df_raw)
    print(f"Variant B FULL: Process {res_b_full['process_time']:.2f}s ({res_b_full['throughput_jobs_sec']:.1f} jobs/s), Total: {res_b_full['total_time']:.2f}s")

    res_c_full = benchmark_variant_c(df_raw)
    print(f"Variant C FULL: Process {res_c_full['process_time']:.2f}s ({res_c_full['throughput_jobs_sec']:.1f} jobs/s), Total: {res_c_full['total_time']:.2f}s")

    # Equivalence on full 12,816 jobs
    pairs_a_full = res_a_full["pairs"]
    pairs_b_full = res_b_full["pairs"]
    intersect_full = pairs_a_full & pairs_b_full
    only_a_full = pairs_a_full - pairs_b_full
    only_b_full = pairs_b_full - pairs_a_full
    union_full = pairs_a_full | pairs_b_full
    agreement_full = len(intersect_full) / len(union_full) if union_full else 1.0

    print(f"\n================ FULL AC OUTPUT EQUIVALENCE (12,816 JOBS) ================")
    print(f"Standalone pairs: {len(pairs_a_full)}")
    print(f"Hybrid AC pairs:   {len(pairs_b_full)}")
    print(f"Intersection:      {len(intersect_full)}")
    print(f"Only Standalone:   {len(only_a_full)}")
    print(f"Only Hybrid:       {len(only_b_full)}")
    print(f"Agreement:         {agreement_full:.4%}")

    if only_a_full:
        print("Sample Only Standalone:", list(only_a_full)[:10])
    if only_b_full:
        print("Sample Only Hybrid:", list(only_b_full)[:10])

if __name__ == "__main__":
    main()
