"""單元與整合測試：詞庫約束語意檢索、假陰性召回與防幻覺機制。"""

import os
import pytest
import pandas as pd

from src.lexicon.loader import LexiconLoader
from src.retrieval.bm25 import BM25Retriever
from src.retrieval.dense import DenseRetriever
from src.retrieval.hybrid import HybridRetriever
from src.grounding.discovery import ConceptDiscoverer
from src.grounding.grounder import ConceptGrounder
from src.grounding.schemas import DecisionType, GroundingDecision, GroundingStatus
from src.grounding.review_table import build_review_table
from src.grounding.expansion import KeywordCandidateManager
from src.hybrid_pipeline import HybridJobSkillPipeline


@pytest.fixture
def lexicon_data():
    """載入測試用迷你詞庫。"""
    loader = LexiconLoader(
        rules_path="configs/rules.yaml", synonyms_path="configs/synonyms.yaml"
    )
    term_to_entries, skill_index = loader.load_lexicon(
        "lexicon/sample/mini_skill_lexicon.csv"
    )
    return term_to_entries, skill_index


def test_bm25_retriever(lexicon_data):
    """測試 BM25 檢索器之關鍵字匹配與 IDF 評分。"""
    _, skill_index = lexicon_data
    bm25 = BM25Retriever(skill_id_index=skill_index)

    # 檢索 Python
    results = bm25.retrieve("Python 開發", top_k=3)
    assert len(results) > 0
    top_id, score = results[0]
    assert skill_index[top_id]["SKILL_NAME_ZH"] == "Python"
    assert score > 0.5


def test_dense_retriever(lexicon_data):
    """測試 Dense 語意向量檢索器之餘弦相似度與跨語言映射。"""
    _, skill_index = lexicon_data
    dense = DenseRetriever(skill_id_index=skill_index)

    # 檢索電路/硬體相關
    results = dense.retrieve("circuit hardware debug", top_k=3)
    assert len(results) > 0
    top_id, score = results[0]
    # 應能關聯至電路設計或相關工程
    assert top_id in skill_index
    assert 0.0 <= score <= 1.0


def test_hybrid_retriever_and_comparison(lexicon_data):
    """測試 Hybrid RRF 融合檢索與三種方法對比 (Task 2)。"""
    _, skill_index = lexicon_data
    hybrid = HybridRetriever(skill_id_index=skill_index)

    cmp_res = hybrid.compare_retrieval("SPC 統計製程管制", top_k=5)
    assert "bm25" in cmp_res
    assert "dense" in cmp_res
    assert "hybrid" in cmp_res

    # 驗證 Hybrid 結果中所有 ID 皆合法存在於詞庫
    for s_id, score in cmp_res["hybrid"]:
        assert s_id in skill_index


def test_hardware_engineer_prompt_example(lexicon_data):
    """測試使用者提出之硬體研發工程師範例短語抽取與診斷 (Task 1 & Task 3)。"""
    _, skill_index = lexicon_data
    discoverer = ConceptDiscoverer()

    job_title = "硬體研發工程師"
    job_desc = """【工作內容】
1. Server Design
2. Board debug
3. BOM creation
4. Documents creation
5. Work with team for project development
"""
    # 假設 AC 已經匹配了 BOM
    concepts = discoverer.discover_concepts(
        job_title=job_title,
        job_desc=job_desc,
        existing_candidate_texts=["BOM"],
    )

    extracted_texts = [c.concept_text.lower() for c in concepts]
    assert any("server design" in t for t in extracted_texts)
    assert any("board debug" in t for t in extracted_texts)
    assert any("documents creation" in t for t in extracted_texts)
    assert any("work with team" in t for t in extracted_texts)


def test_anti_hallucination_strict_guard(lexicon_data):
    """測試防幻覺鐵律：絕不自行發明 Skill_Name_ZH，無匹配即 NO_MATCH (Task 4)。"""
    _, skill_index = lexicon_data
    grounder = ConceptGrounder(skill_id_index=skill_index)

    # 針對迷你詞庫中完全不存在的技能概念 (如 'Documents creation')
    item = grounder.diagnose_phrase(
        original_phrase="Documents creation",
        job_title="硬體研發工程師",
        quote_evidence="4. Documents creation",
    )

    # 1. 嚴禁發明 "文件管理"
    if item.selected_skill_name_zh:
        assert item.selected_skill_id in skill_index
        assert skill_index[item.selected_skill_id]["SKILL_NAME_ZH"] == item.selected_skill_name_zh
    else:
        # 詞庫無符合者必須為 UNCERTAIN 或 NO_MATCH，絕不可為 MATCH
        assert item.decision in [DecisionType.UNCERTAIN, DecisionType.NO_MATCH]

    # 2. 偽造不存在的 ID 測試防偽攔截
    fake_dec = GroundingDecision(
        concept_text="虛構技能短語",
        status=GroundingStatus.GROUNDED,
        selected_skill_id="FAKE_ID_99999",
        quote_evidence="測試",
    )
    validated = grounder.validate_grounding_decision(fake_dec)
    assert validated.status == GroundingStatus.UNGROUNDED
    assert validated.selected_skill_id is None


def test_human_review_table_generation():
    """測試 Task 5 人工審核總表產出。"""
    from src.grounding.schemas import SemanticRecoveryItem

    mock_item = SemanticRecoveryItem(
        original_phrase="Documents creation",
        normalized_phrase="documents creation",
        semantic_interpretation="無詞庫對應項目",
        candidate_skill_ids=["KS120L96KMYTDJ48NRSH"],
        candidate_skill_names=["軟體開發 (Software Development)"],
        retrieval_score=0.25,
        evidence="4. Documents creation",
        confidence=0.25,
        decision=DecisionType.NO_MATCH,
        ac_result="None",
    )

    records = [{"job_title": "硬體研發工程師", "item": mock_item}]
    df_review = build_review_table(records)

    assert not df_review.empty
    expected_cols = [
        "job_title", "original_phrase", "AC_result", "candidate_skill",
        "Skill_ID", "evidence", "confidence", "decision"
    ]
    for col in expected_cols:
        assert col in df_review.columns

    assert df_review.iloc[0]["decision"] == "NO_MATCH"
    assert df_review.iloc[0]["job_title"] == "硬體研發工程師"


def test_keyword_candidate_manager(tmp_path):
    """測試 Task 6 關鍵字擴充候選輸出至 CSV。"""
    from src.grounding.schemas import SemanticRecoveryItem

    csv_file = tmp_path / "keyword_candidates.csv"
    manager = KeywordCandidateManager(output_path=str(csv_file))

    # MATCH 案例
    match_item = SemanticRecoveryItem(
        original_phrase="SPC",
        normalized_phrase="spc",
        semantic_interpretation="對齊品質管理",
        candidate_skill_ids=["KS1289C6QS0TSSB4PNGG"],
        candidate_skill_names=["品質管理 (Quality Management)"],
        retrieval_score=0.95,
        evidence="統計製程管制 SPC",
        confidence=0.95,
        decision=DecisionType.MATCH,
        selected_skill_id="KS1289C6QS0TSSB4PNGG",
        selected_skill_name_zh="品質管理",
    )

    records = [{"job_title": "製程工程師", "item": match_item}]
    df_out = manager.export_candidates(records, confidence_threshold=0.80)

    assert os.path.exists(csv_file)
    assert len(df_out) == 1
    row = df_out.iloc[0]
    assert row["Skill_ID"] == "KS1289C6QS0TSSB4PNGG"
    assert row["Skill_Name_ZH"] == "品質管理"
    assert row["new_keyword"] == "SPC"
    assert row["confidence"] == 0.95
