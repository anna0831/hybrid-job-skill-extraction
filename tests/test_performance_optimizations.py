"""Regression tests for approved safe performance optimizations:
1. NaN lexicon field guards
2. Fast wide-table formatter equivalence
3. Optimized column iteration in process_dataframe
4. Inverted-index BM25 equivalence
"""

import math
import os
import re
import difflib
from typing import Dict, List, Tuple, Any
import numpy as np
import pandas as pd
import pytest

from src.lexicon.loader import LexiconLoader, _clean_str
from src.ac_matcher.engine import ACMatcher
from src.outputs.formatter import skills_to_wide, _DEFAULT_CAT9_ZH
from src.hybrid_pipeline import HybridJobSkillPipeline
from src.retrieval.bm25 import BM25Retriever, tokenize_text


# ============================================================
# Test A: NaN Lexicon Field Guards
# ============================================================

def test_clean_str_handles_missing_values():
    """Verify _clean_str converts NaN/None/literal nan/none to empty string."""
    assert _clean_str(None) == ""
    assert _clean_str(np.nan) == ""
    assert _clean_str(float("nan")) == ""
    assert _clean_str("nan") == ""
    assert _clean_str("NaN") == ""
    assert _clean_str("none") == ""
    assert _clean_str("None") == ""
    assert _clean_str("null") == ""
    assert _clean_str("  nan  ") == ""
    assert _clean_str("Python") == "Python"
    assert _clean_str("  專案管理  ") == "專案管理"


def test_nan_skill_name_zh_does_not_create_nan_matching_term(tmp_path):
    """Verify that a row with Skill_Name_ZH = NaN does not register 'nan' as a matching term."""
    test_csv = tmp_path / "test_nan_lexicon.csv"
    df_lex = pd.DataFrame([
        {
            "Skill_ID": "TEST_001",
            "Skill_Name": "Hotel Operations",
            "Skill_Name_ZH": np.nan,  # Missing Chinese name
            "Skill_Type": "Hard Skill",
            "Skill_Category": "Management Skills",
            "Category_Code": "100",
            "Category_Name": "Management",
            "Subcategory_Code": "101",
            "Subcategory_Name": "Operations",
            "Keywords": "Hotel運作｜飯店營運",
        },
        {
            "Skill_ID": "TEST_002",
            "Skill_Name": "Python Programming",
            "Skill_Name_ZH": "Python程式設計",
            "Skill_Type": "Hard Skill",
            "Skill_Category": "Advanced Computer Skills",
            "Category_Code": "17",
            "Category_Name": "Software",
            "Subcategory_Code": "171",
            "Subcategory_Name": "Dev",
            "Keywords": np.nan,  # Missing Keywords
        },
    ])
    df_lex.to_csv(test_csv, index=False)

    loader = LexiconLoader()
    term_to_entries, skill_index = loader.load_lexicon(str(test_csv))

    # 'nan' must NOT be in term_to_entries
    assert "nan" not in term_to_entries
    assert "none" not in term_to_entries
    assert "null" not in term_to_entries

    # The English name 'hotel operations' should be present
    assert "hotel operations" in term_to_entries

    # AC Matcher must not match the word 'nan' in text
    matcher = ACMatcher.build_from_lexicon(term_to_entries, skill_index)
    matches = matcher.match_texts(["This job requires nan and nothing else"])
    matched_ids = [m.skill_id for m in matches]
    assert "TEST_001" not in matched_ids


# ============================================================
# Test B: Fast Formatter Equivalence
# ============================================================

def _legacy_skills_to_wide(
    long_df: pd.DataFrame,
    raw_df: pd.DataFrame,
    mapping: Dict[str, str] = _DEFAULT_CAT9_ZH,
) -> pd.DataFrame:
    """Legacy groupby.apply + nested iterrows implementation."""
    raw_df = raw_df.copy()
    id_col = "ID" if "ID" in raw_df.columns else "id"
    raw_df["ID"] = raw_df[id_col].astype(str)

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

        agg_df = (
            long_df.groupby("ID")
            .apply(agg, include_groups=False)
            .reset_index()
        )

    desc_cols = ["ID", "職位名稱", "job_desc"]
    desc_cols = [c for c in desc_cols if c in raw_df.columns]
    desc = raw_df[desc_cols]
    return desc.merge(agg_df, on="ID", how="left")


def test_fast_formatter_exact_equivalence():
    """Verify fast dictionary aggregation produces 100% identical DataFrame to legacy groupby.apply."""
    raw_df = pd.DataFrame({
        "ID": ["1001", "1002", "1003", "1004"],
        "職位名稱": ["軟體工程師", "會計專員", "專案經理", "無技能職缺"],
        "job_desc": ["開發 Python 與 AI 模型", "處理財務報表", "溝通與專案管理", "一般行政"],
    })

    long_df = pd.DataFrame([
        {"ID": "1001", "SKILL_NAME_ZH": "Python程式設計", "SKILL_CAT9": "Advanced Computer Skills"},
        {"ID": "1001", "SKILL_NAME_ZH": "機器學習", "SKILL_CAT9": "AI & Big Data Skills"},
        {"ID": "1002", "SKILL_NAME_ZH": "財務報表", "SKILL_CAT9": "Financial Skills"},
        {"ID": "1003", "SKILL_NAME_ZH": "專案管理", "SKILL_CAT9": "Management Skills"},
        {"ID": "1003", "SKILL_NAME_ZH": "團隊溝通", "SKILL_CAT9": "Social Skills"},
        {"ID": "1003", "SKILL_NAME_ZH": "問題分析", "SKILL_CAT9": "Cognitive Skills"},
    ])

    df_legacy = _legacy_skills_to_wide(long_df, raw_df)
    df_fast = skills_to_wide(long_df, raw_df)

    pd.testing.assert_frame_equal(df_legacy, df_fast, check_dtype=True)


def test_fast_formatter_empty_long_df():
    """Verify empty long_df handling."""
    raw_df = pd.DataFrame({
        "ID": ["1001"],
        "職位名稱": ["工程師"],
    })
    long_df = pd.DataFrame(columns=["ID", "SKILL_NAME_ZH", "SKILL_CAT9"])

    df_legacy = _legacy_skills_to_wide(long_df, raw_df)
    df_fast = skills_to_wide(long_df, raw_df)

    pd.testing.assert_frame_equal(df_legacy, df_fast, check_dtype=False)


# ============================================================
# Test C: Pre-extracted Column Iteration Equivalence
# ============================================================

def test_process_dataframe_equivalence(tmp_path):
    """Verify pre-extracted iteration produces identical long_df and wide_df results."""
    test_csv = tmp_path / "test_pipeline_lexicon.csv"
    pd.DataFrame([
        {
            "Skill_ID": "S1",
            "Skill_Name": "Python",
            "Skill_Name_ZH": "Python程式設計",
            "Skill_Type": "Hard Skill",
            "Skill_Category": "Advanced Computer Skills",
            "Category_Code": "17",
            "Category_Name": "Software",
            "Subcategory_Code": "171",
            "Subcategory_Name": "Dev",
            "Keywords": "Python",
        },
        {
            "Skill_ID": "S2",
            "Skill_Name": "SQL",
            "Skill_Name_ZH": "SQL資料庫",
            "Skill_Type": "Hard Skill",
            "Skill_Category": "Advanced Computer Skills",
            "Category_Code": "17",
            "Category_Name": "Software",
            "Subcategory_Code": "171",
            "Subcategory_Name": "Dev",
            "Keywords": "SQL",
        },
    ]).to_csv(test_csv, index=False)

    df_jobs = pd.DataFrame({
        "ID": ["J1", "J2", "J3"],
        "職位名稱": ["後端工程師", "資料分析師", "行銷專員"],
        "職位描述": ["精通 Python 開發", "精通 SQL 資料庫與 Python 分析", "社群文案撰寫"],
        "擅長工具": ["Python", "SQL", ""],
        "工作技能": ["", "", ""],
    })

    pipeline = HybridJobSkillPipeline(
        lexicon_path=str(test_csv),
        enable_fn_recovery=False,
        bypass_verification=True,
    )

    long_df, wide_df, stats = pipeline.process_dataframe(df_jobs)

    assert len(long_df) == 3
    assert set(long_df["ID"]) == {"J1", "J2"}
    assert len(wide_df) == 3
    assert list(wide_df["ID"]) == ["J1", "J2", "J3"]
    assert wide_df.loc[wide_df["ID"] == "J1", "技能數"].values[0] == 1
    assert wide_df.loc[wide_df["ID"] == "J2", "技能數"].values[0] == 2
    assert pd.isna(wide_df.loc[wide_df["ID"] == "J3", "技能數"].values[0])


# ============================================================
# Test D: Inverted-Index BM25 Equivalence
# ============================================================

def test_bm25_inverted_index_exact_equivalence():
    """Verify inverted-index BM25 produces 100% identical top-K candidates and scores."""
    skill_index = {
        "SK001": {
            "SKILL_ID": "SK001",
            "SKILL_NAME": "Python Programming",
            "SKILL_NAME_ZH": "Python程式設計",
            "KEYWORDS": "Python｜程式開發｜Django｜Flask",
            "SKILL_CATEGORY_NAME": "資訊軟體",
            "SKILL_SUBCATEGORY_NAME": "軟體工程",
        },
        "SK002": {
            "SKILL_ID": "SK002",
            "SKILL_NAME": "Machine Learning",
            "SKILL_NAME_ZH": "機器學習",
            "KEYWORDS": "機器學習｜深度學習｜TensorFlow｜PyTorch",
            "SKILL_CATEGORY_NAME": "資訊軟體",
            "SKILL_SUBCATEGORY_NAME": "人工智慧",
        },
        "SK003": {
            "SKILL_ID": "SK003",
            "SKILL_NAME": "Financial Reporting",
            "SKILL_NAME_ZH": "財務報表編製",
            "KEYWORDS": "財務報表｜會計｜審計",
            "SKILL_CATEGORY_NAME": "財務會計",
            "SKILL_SUBCATEGORY_NAME": "會計",
        },
        "SK004": {
            "SKILL_ID": "SK004",
            "SKILL_NAME": "Statistical Process Control",
            "SKILL_NAME_ZH": "統計製程管制",
            "KEYWORDS": "SPC｜製程管制｜良率分析",
            "SKILL_CATEGORY_NAME": "生產品質",
            "SKILL_SUBCATEGORY_NAME": "品保",
        },
    }

    # Reference linear scan BM25
    class LinearBM25(BM25Retriever):
        def retrieve(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
            query_tokens = tokenize_text(query)
            if not query_tokens or not self.skill_ids:
                return []
            scores = [0.0] * len(self.skill_ids)
            for q in query_tokens:
                if q not in self.idf:
                    continue
                idf_val = self.idf[q]
                for i, tf_dict in enumerate(self.doc_term_freqs):
                    tf = tf_dict.get(q, 0)
                    if tf == 0:
                        continue
                    d_len = self.doc_lengths[i]
                    num = tf * (self.k1 + 1.0)
                    den = tf + self.k1 * (1.0 - self.b + self.b * (d_len / self.avgdl))
                    scores[i] += idf_val * (num / den)
            ranked = sorted(range(len(scores)), key=lambda idx: scores[idx], reverse=True)
            results = []
            max_s = scores[ranked[0]] if ranked and scores[ranked[0]] > 0 else 1.0
            nq = len(query_tokens)
            for idx in ranked[:top_k]:
                s = scores[idx]
                if s <= 0:
                    continue
                tf_dict = self.doc_term_freqs[idx]
                mq = sum(1 for q in query_tokens if tf_dict.get(q, 0) > 0)
                cov = (mq / nq) if nq > 0 else 1.0
                norm = min(1.0, (s / max_s) * (0.5 + 0.5 * cov))
                results.append((self.skill_ids[idx], round(norm, 4)))
            return results

    linear_retriever = LinearBM25(skill_index)
    inverted_retriever = BM25Retriever(skill_index)

    queries = [
        "Python 資料分析",
        "深度學習 與 機器學習",
        "財務報表",
        "spc 品質管制",
        "完全無關的查詢字串xyz",
    ]

    for q in queries:
        linear_res = linear_retriever.retrieve(q, top_k=3)
        inverted_res = inverted_retriever.retrieve(q, top_k=3)
        assert linear_res == inverted_res, f"Mismatch for query '{q}': {linear_res} != {inverted_res}"
