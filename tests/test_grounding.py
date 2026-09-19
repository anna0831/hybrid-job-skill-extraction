"""兩階段概念接地與假陰性召回單元測試 (Two-Stage Concept Grounding Tests)。"""

import pytest
from src.grounding.schemas import (
    DiscoveredConcept,
    LexiconCandidate,
    GroundingDecision,
    GroundingStatus,
    FNRecoveryResult,
)
from src.grounding.discovery import ConceptDiscoverer
from src.grounding.grounder import ConceptGrounder
from src.grounding.providers import MockConceptGrounder, get_concept_grounder
from src.hybrid_pipeline import HybridJobSkillPipeline
from src.lexicon.loader import LexiconLoader


@pytest.fixture
def sample_lexicon_data():
    """載入測試用迷你詞庫。"""
    loader = LexiconLoader(
        rules_path="configs/rules.yaml",
        synonyms_path="configs/synonyms.yaml",
    )
    term_to_entries, skill_index = loader.load_lexicon("lexicon/sample/mini_skill_lexicon.csv")
    return term_to_entries, skill_index


def test_grounding_schemas():
    """驗證 Pydantic 資料模型結構與預設值。"""
    concept = DiscoveredConcept(
        concept_text="統計製程管制",
        quote_evidence="負責統計製程管制 SPC 作業",
        confidence=0.9,
    )
    assert concept.concept_text == "統計製程管制"
    assert concept.confidence == 0.9
    assert concept.source_field == "job_desc"

    decision = GroundingDecision(
        concept_text="統計製程管制",
        status=GroundingStatus.GROUNDED,
        selected_skill_id="KS1289C6QS0TSSB4PNGG",
        selected_skill_name_zh="品質管理",
    )
    assert decision.status == GroundingStatus.GROUNDED
    assert decision.selected_skill_id == "KS1289C6QS0TSSB4PNGG"


def test_concept_discovery_heuristic():
    """驗證 Stage 1 啟發式概念發現器能否從職缺文字中抽取出技術短語。"""
    discoverer = ConceptDiscoverer()
    
    job_desc = "主導晶圓產線 defect reduction 與統計製程管制 SPC，負責品質異常排查與全面品質管制流程。"
    job_skills = "統計製程管制"
    tools = "JMP"

    concepts = discoverer.discover_concepts(
        job_title="半導體良率改善工程師",
        job_desc=job_desc,
        tools=tools,
        job_skills=job_skills,
    )

    concept_texts = {c.concept_text.lower() for c in concepts}
    # 驗證抽取到關鍵短語
    assert "統計製程管制" in concept_texts or "spc" in concept_texts or "jmp" in concept_texts
    assert any(c.source_field in ("tools", "job_skills", "job_desc") for c in concepts)


def test_concept_discovery_filters_stopwords():
    """驗證非技能的通用口語與停用詞被有效過濾。"""
    discoverer = ConceptDiscoverer()
    job_desc = "公司提供良好福利，工作環境佳，無經驗可，需具備良好體力與抗壓性高。"
    concepts = discoverer.discover_concepts(
        job_title="門市人員",
        job_desc=job_desc,
    )
    concept_texts = {c.concept_text for c in concepts}
    assert "公司提供" not in concept_texts
    assert "工作環境" not in concept_texts
    assert "良好體力" not in concept_texts


def test_lexicon_candidate_retrieval(sample_lexicon_data):
    """驗證 Stage 2 能檢索出高相似度的詞庫候選。"""
    term_to_entries, skill_index = sample_lexicon_data
    grounder = ConceptGrounder(skill_id_index=skill_index, term_to_entries=term_to_entries)

    # 1. 精確比對
    cands_exact = grounder.retrieve_lexicon_candidates("Python", top_k=3)
    assert len(cands_exact) > 0
    assert cands_exact[0].skill_name_en.lower() == "python"
    assert cands_exact[0].similarity_score == 1.0

    # 2. 模糊/重疊比對
    cands_fuzzy = grounder.retrieve_lexicon_candidates("品質管理", top_k=3)
    assert len(cands_fuzzy) > 0
    assert any(c.skill_name_zh == "品質管理" for c in cands_fuzzy)


def test_strict_lexicon_boundary_guard(sample_lexicon_data):
    """驗證防偽機制：若模型捏造不存在的 Skill_ID，強制攔截重設為 UNGROUNDED。"""
    term_to_entries, skill_index = sample_lexicon_data
    grounder = ConceptGrounder(skill_id_index=skill_index, term_to_entries=term_to_entries)

    # 模擬模型產生幻覺，回傳捏造的 Skill_ID
    fake_decision = GroundingDecision(
        concept_text="量子糾纏演算法",
        status=GroundingStatus.GROUNDED,
        selected_skill_id="FAKE_HALLUCINATED_ID_9999",
        selected_skill_name_zh="量子糾纏演算法",
    )

    validated = grounder.validate_grounding_decision(fake_decision)
    assert validated.status == GroundingStatus.UNGROUNDED
    assert validated.selected_skill_id is None
    assert "does not exist in lexicon" in validated.reason


def test_mock_grounder_gold_008(sample_lexicon_data):
    """驗證 MockConceptGrounder 成功召回 GOLD_008 漏抓案例。"""
    term_to_entries, skill_index = sample_lexicon_data
    grounder = MockConceptGrounder(skill_id_index=skill_index, term_to_entries=term_to_entries)

    res: FNRecoveryResult = grounder.recover_job_skills(
        job_id="GOLD_008",
        job_title="半導體良率改善工程師",
        job_desc="主導晶圓產線 defect reduction 與統計製程管制 SPC，負責品質異常排查與全面品質管制流程。",
        tools="JMP",
        job_skills="統計製程管制",
    )

    assert "KS1289C6QS0TSSB4PNGG" in res.recovered_skill_ids
    assert res.stats["recovered_count"] >= 1
    # 檢查對應之技能名稱為品質管理
    decisions = [d for d in res.decisions if d.selected_skill_id == "KS1289C6QS0TSSB4PNGG"]
    assert len(decisions) > 0
    assert decisions[0].selected_skill_name_zh == "品質管理"


def test_mock_grounder_rejects_unrelated(sample_lexicon_data):
    """驗證無關或非技能短語被 MockConceptGrounder 拒絕。"""
    term_to_entries, skill_index = sample_lexicon_data
    grounder = MockConceptGrounder(skill_id_index=skill_index, term_to_entries=term_to_entries)

    concepts = [
        DiscoveredConcept(concept_text="員工旅遊補助", quote_evidence="公司提供員工旅遊補助"),
        DiscoveredConcept(concept_text="完全未知代碼XYZ123", quote_evidence="操作未知代碼XYZ123"),
    ]

    decisions = grounder.ground_concepts(
        job_title="行政助理",
        job_desc="公司提供員工旅遊補助",
        concepts=concepts,
    )

    for dec in decisions:
        assert dec.status == GroundingStatus.UNGROUNDED
        assert dec.selected_skill_id is None


def test_hybrid_pipeline_with_fn_recovery():
    """端到端測試：HybridJobSkillPipeline 啟用 FN 召回後成功擷取 GOLD_008。"""
    pipeline = HybridJobSkillPipeline(
        lexicon_path="lexicon/sample/mini_skill_lexicon.csv",
        verifier_provider="mock",
        grounder_provider="mock",
        enable_fn_recovery=True,
    )

    # 執行 GOLD_008 (原 AC 命中數為 0)
    final_skills, routing_res, ver_records = pipeline.extract_job_skills(
        job_id="GOLD_008",
        job_title="半導體良率改善工程師",
        job_desc="主導晶圓產線 defect reduction 與統計製程管制 SPC，負責品質異常排查與全面品質管制流程。",
        tools="JMP",
        job_skills="統計製程管制",
    )

    # 驗證第三軌被觸發且成功召回「品質管理」
    assert routing_res.needs_fn_recovery is True
    fn_res = routing_res.fn_recovery_result
    assert fn_res is not None
    assert "KS1289C6QS0TSSB4PNGG" in fn_res.recovered_skill_ids

    skill_ids = [s.skill_id for s in final_skills]
    assert "KS1289C6QS0TSSB4PNGG" in skill_ids

    # 驗證 CandidateSkill 標記
    recovered_cand = [s for s in final_skills if s.skill_id == "KS1289C6QS0TSSB4PNGG"][0]
    assert recovered_cand.field_source == "FN_RECOVERY"
    assert "品質管理" in recovered_cand.matched_keyword


def test_hybrid_pipeline_no_fn_when_disabled():
    """端到端測試：當 enable_fn_recovery=False 時，不進行漏抓補救。"""
    pipeline = HybridJobSkillPipeline(
        lexicon_path="lexicon/sample/mini_skill_lexicon.csv",
        verifier_provider="mock",
        grounder_provider="mock",
        enable_fn_recovery=False,
    )

    final_skills, routing_res, ver_records = pipeline.extract_job_skills(
        job_id="GOLD_008",
        job_title="半導體良率改善工程師",
        job_desc="主導晶圓產線 defect reduction 與統計製程管制 SPC，負責品質異常排查與全面品質管制流程。",
        tools="JMP",
        job_skills="統計製程管制",
    )

    assert routing_res.needs_fn_recovery is True
    assert routing_res.fn_recovery_result is None
    assert len(final_skills) == 0
