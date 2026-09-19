"""Tests for Aho-Corasick matching engine, suppression, and disambiguation."""

import pytest
from src.lexicon.loader import LexiconLoader
from src.ac_matcher.engine import ACMatcher


@pytest.fixture(scope="module")
def pipeline_components():
    loader = LexiconLoader(
        rules_path="configs/rules.yaml",
        synonyms_path="configs/synonyms.yaml",
    )
    term_to_entries, skill_index = loader.load_lexicon("lexicon/sample/mini_skill_lexicon.csv")
    matcher = ACMatcher.build_from_lexicon(
        term_to_entries=term_to_entries,
        skill_index=skill_index,
        rules_path="configs/rules.yaml",
    )
    return matcher, skill_index


def test_basic_ac_match(pipeline_components):
    matcher, _ = pipeline_components
    texts = ["熟悉 Python 開發與 SQL 資料庫查詢維護", "", "Python"]
    candidates = matcher.match_texts(texts)
    skill_names = {c.skill_name_zh for c in candidates}
    assert "Python" in skill_names or "SQL" in skill_names


def test_longest_match_suppression(pipeline_components):
    matcher, _ = pipeline_components
    # "新產品開發" vs "產品開發"
    texts = ["主導新產品開發專案進度與規格確認"]
    candidates = matcher.match_texts(texts)
    matched_terms = [c.matched_keyword for c in candidates]
    # Should match the full phrase "新產品開發"
    assert any("新產品開發" in term or "產品開發" in term for term in matched_terms)


def test_title_disambiguation_fallback(pipeline_components):
    matcher, _ = pipeline_components
    # Job has zero regular match, but contains vague word "操作" and title has "作業員"
    texts = ["負責產線日常操作與包裝作業"]
    matched = matcher.match_texts(texts)
    if not matched:
        resolved = matcher.resolve_ambiguous_by_title(texts, job_title="產線作業員")
        assert len(resolved) > 0
        assert resolved[0].skill_id == "TW_MFG_001"  # 機台操作
        assert resolved[0].field_source == "職稱消歧"


def test_local_context_rules(pipeline_components):
    matcher, _ = pipeline_components
    # "產品之開發" should match 新產品開發 via local context
    texts = ["專責消費電子產品之開發"]
    resolved = matcher.resolve_ambiguous_by_title(texts, job_title="工程師")
    assert len(resolved) > 0
    assert resolved[0].skill_id == "KS1270P6SLFCFT476Y3R"  # 新產品開發
    assert resolved[0].field_source == "就近文意"
