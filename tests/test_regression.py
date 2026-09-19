"""Regression test: Ensure modular refactored code outputs identical results to the legacy monolithic script."""

import pytest
import pandas as pd
from src.pipeline import JobSkillPipeline

# Import legacy functions directly for regression verification
import sys
import os
sys.path.insert(0, os.path.abspath("."))
import importlib.util

spec = importlib.util.spec_from_file_location("legacy_script", "104_single_file_20260909.py")
legacy = importlib.util.module_from_spec(spec)
# Don't run main() on import
spec.loader.exec_module(legacy)


@pytest.fixture(scope="module")
def sample_test_data():
    return pd.DataFrame([
        {
            "工作編號": "TEST_001",
            "104職位名稱": "軟體工程師",
            "職位描述": "負責 Python 與 SQL 開發，新產品開發專案",
            "工作技能": "程式開發",
            "擅長工具": "Python",
        },
        {
            "工作編號": "TEST_002",
            "104職位名稱": "美髮設計師",
            "職位描述": "提供剪、染、洗服務",
            "工作技能": "",
            "擅長工具": "",
        },
        {
            "工作編號": "TEST_003",
            "104職位名稱": "產線技術員",
            "職位描述": "機台日常操作與設備保養",
            "工作技能": "",
            "擅長工具": "",
        },
    ])


def test_modular_vs_legacy_consistency(sample_test_data):
    """驗證新模組產出的 Candidate Skills 與舊版邏輯高度一致。"""
    lexicon_path = "lexicon/sample/mini_skill_lexicon.xlsx"
    
    # 1. 舊版方式建構
    legacy_automaton = legacy.load_automaton(lexicon_path)
    
    # 2. 新模組方式建構
    pipeline = JobSkillPipeline(lexicon_path=lexicon_path)
    
    for _, row in sample_test_data.iterrows():
        texts = [
            str(row["職位描述"]),
            str(row["工作技能"]),
            str(row["擅長工具"]),
        ]
        job_title = str(row["104職位名稱"])
        
        # 舊版比對
        legacy_matched = legacy.match_skills(texts, legacy_automaton)
        if not legacy_matched:
            skill_index = legacy.build_skill_id_index(legacy_automaton)
            legacy_matched = legacy.resolve_ambiguous_by_title(texts, job_title, legacy_automaton, skill_index)
            
        # 新模組比對
        new_matched = pipeline.matcher.extract_job_skills(texts, job_title=job_title)
        
        legacy_ids = {s["SKILL_ID"] for s in legacy_matched}
        new_ids = {s.skill_id for s in new_matched}
        
        # 驗證抽取的 Skill_ID 完全一致
        assert legacy_ids == new_ids, f"Mismatch for job {row['工作編號']}: legacy={legacy_ids}, new={new_ids}"
