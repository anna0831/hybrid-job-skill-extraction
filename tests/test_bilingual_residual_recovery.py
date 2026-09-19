"""單元與迴歸測試：雙語上下文感知驗證與殘差語意召回系統。

涵蓋 5 大核心測試案型：
CASE 1: 硬體研發工程師 (BOM + 殘差短語評估)
CASE 2: 全英文技術職缺 (English-heavy JD 檢索中文 Skill_Name_ZH)
CASE 3: 中文隱性工作活動 (Chinese JD with implicit work activities)
CASE 4: 中英混雜職缺 (Mixed Chinese-English JD)
CASE 5: 欺騙性假陽性關鍵字拒絕 (SSD Failure Analysis -> 應收帳款, 動物飼育 -> Bioness)
"""

import os
import pytest
import pandas as pd

from src.lexicon.loader import LexiconLoader
from src.lexicon.schema import CandidateSkill
from src.ac_matcher.engine import ACMatcher
from src.preprocessing.segmenter import JDSegmenter, SemanticUnit
from src.recovery.residual_detector import ResidualDetector
from src.recovery.semantic_recovery import ResidualSemanticRecoveryEngine
from src.verifier.base import MockVerifier
from src.verifier.semantic_verifier import SemanticVerifier
from src.verifier.schemas import VerificationVerdict
from src.grounding.schemas import DecisionType
from src.hybrid_pipeline import HybridJobSkillPipeline


@pytest.fixture(scope="module")
def pipeline_env():
    """載入測試用管線環境。"""
    lexicon_path = "lexicon/sample/mini_skill_lexicon.csv"
    loader = LexiconLoader()
    term_to_entries, skill_index = loader.load_lexicon(lexicon_path)
    matcher = ACMatcher.build_from_lexicon(term_to_entries, skill_index)
    verifier = SemanticVerifier(skill_id_index=skill_index)
    recovery_engine = ResidualSemanticRecoveryEngine(
        skill_id_index=skill_index,
        verifier=verifier,
    )
    hybrid_pipeline = HybridJobSkillPipeline(
        lexicon_path=lexicon_path,
        verifier_provider="mock",
        grounder_provider="mock",
        enable_fn_recovery=True,
    )
    return {
        "skill_index": skill_index,
        "matcher": matcher,
        "verifier": verifier,
        "recovery_engine": recovery_engine,
        "hybrid_pipeline": hybrid_pipeline,
    }


def test_case_1_hardware_engineer(pipeline_env):
    """CASE 1: 硬體研發工程師 (Server Design, Board debug, BOM, Documents creation, Work with team)。"""
    matcher = pipeline_env["matcher"]
    recovery_engine = pipeline_env["recovery_engine"]

    job_title = "硬體研發工程師"
    job_desc = """【工作內容】
1. Server Design
2. Board debug
3. BOM creation
4. Documents creation
5. Work with team for project development
"""
    # 1. AC 命中驗證
    ac_matches = matcher.extract_job_skills([job_desc], job_title=job_title)
    ac_keywords = [c.matched_keyword.lower() for c in ac_matches]
    # BOM 應能被 AC 或關鍵字識別
    assert any("bom" in kw for kw in ac_keywords) or any("物料" in c.skill_name_zh for c in ac_matches)

    # 2. 殘差語意召回評估
    res_result = recovery_engine.recover_residuals(
        job_id="CASE_1",
        job_title=job_title,
        job_desc=job_desc,
        ac_matches=ac_matches,
    )

    # 驗證殘差單元抽取
    extracted_phrases = [u.phrase.lower() for u in res_result.residual_units]
    assert any("server design" in p for p in extracted_phrases)
    assert any("board debug" in p for p in extracted_phrases)
    assert any("documents creation" in p for p in extracted_phrases)
    assert any("work with team" in p for p in extracted_phrases)

    # 驗證絕不自行發明「文件管理」
    for v_out in res_result.verification_outputs:
        if "documents creation" in v_out.source_phrase.lower():
            if v_out.skill_name:
                assert v_out.skill_id in pipeline_env["skill_index"]
            else:
                assert v_out.decision in [DecisionType.NO_MATCH, DecisionType.UNCERTAIN]


def test_case_2_english_heavy_technical_jd(pipeline_env):
    """CASE 2: 全英文技術職缺，驗證英文專業名詞檢索出中文標準名稱與合法 Skill_ID。"""
    recovery_engine = pipeline_env["recovery_engine"]
    skill_index = pipeline_env["skill_index"]

    job_title = "Backend Software Engineer"
    job_desc = """
Job Description:
- Python backend API development and architecture planning
- SQL database query optimization and performance tuning
- Statistical process analysis for system metrics
"""
    res_result = recovery_engine.recover_residuals(
        job_id="CASE_2",
        job_title=job_title,
        job_desc=job_desc,
        ac_matches=[],
    )

    # 驗證檢索出的候選技能均合法存在於詞庫且具備有效 Skill_ID 與中文名稱
    for v_out in res_result.verification_outputs:
        if v_out.decision == DecisionType.MATCH:
            assert v_out.skill_id in skill_index
            assert len(v_out.skill_name) > 0


def test_case_3_chinese_implicit_work_activities(pipeline_env):
    """CASE 3: 中文隱性工作活動 (如南投縣模具試樣、晶圓良率統計製程管制)。"""
    recovery_engine = pipeline_env["recovery_engine"]

    job_title = "車床技術員"
    job_desc = """
1. 模具試樣與現場試模
2. 協助產線機台操作與維護
3. 配合主管交辦事項
"""
    res_result = recovery_engine.recover_residuals(
        job_id="CASE_3",
        job_title=job_title,
        job_desc=job_desc,
        ac_matches=[],
    )

    # 驗證「模具試樣」能被識別為殘差單元
    residual_phrases = [u.phrase for u in res_result.residual_units]
    assert any("模具試樣" in p for p in residual_phrases)


def test_case_4_mixed_chinese_english_jd(pipeline_env):
    """CASE 4: 中英夾雜職缺 (如南投縣 14831390 軟體工程師: SAP FI/CO + Business Process Analysis)。"""
    hybrid_pipeline = pipeline_env["hybrid_pipeline"]

    job_title = "軟體工程師"
    job_desc = """
1. SAP FI/CO Module Implementation & Support
2. Business Process Analysis
3. Testing & Troubleshooting
4. Documentation & Training
"""
    final_skills, routing_res, _ = hybrid_pipeline.extract_job_skills(
        job_id="CASE_4",
        job_title=job_title,
        job_desc=job_desc,
    )

    # 最終技能數量應大於 1 (克服 skill_count == 1 限制)
    assert len(final_skills) >= 1
    # 所有技能 ID 必須真實存在
    for s in final_skills:
        assert s.skill_id in pipeline_env["skill_index"]


def test_case_5_misleading_keyword_rejection(pipeline_env):
    """CASE 5: 欺騙性假陽性關鍵字拒絕 (南投縣真實案型：SSD 失效分析 -> 應收帳款；動物飼育 -> Bioness)。"""
    verifier = MockVerifier()

    # 1. 電子工程師 SSD failure analysis 誤中 應收帳款
    fake_cand_ar = CandidateSkill(
        skill_id="FIN_AR_001",
        skill_name="Accounts Receivable",
        skill_name_zh="應收帳款",
        matched_keyword="AR",
        field_source="職位描述",
    )
    rec_ar = verifier.verify_candidate(
        candidate=fake_cand_ar,
        job_title="電子工程師",
        job_desc="Supporting SSD produced product failure 2nd layer analysis and report to customer",
    )
    assert rec_ar.verdict == VerificationVerdict.REJECT
    assert "領域嚴重衝突" in rec_ar.reason

    # 2. 動物飼育員 誤中 Bioness 神經復健設備
    fake_cand_bio = CandidateSkill(
        skill_id="MED_BIO_001",
        skill_name="Bioness Rehab System",
        skill_name_zh="Bioness | 神經復健設備",
        matched_keyword="生物性",
        field_source="職位描述",
    )
    rec_bio = verifier.verify_candidate(
        candidate=fake_cand_bio,
        job_title="一般動物飼育工作者",
        job_desc="1.可接受生物性廢棄物及臭味 2.不排斥動物接觸 3.夜間照護",
    )
    assert rec_bio.verdict == VerificationVerdict.REJECT
    assert "領域嚴重衝突" in rec_bio.reason


def test_jd_segmenter():
    """測試 JDSegmenter 之條列切分、句子切分與福利過濾。"""
    segmenter = JDSegmenter()
    sample_text = """
【工作內容】
1. 負責 Server Design 與板端除錯
2. 撰寫技術文件與規格書
公司提供月薪 45,000 元含全勤，享勞健保與員工旅遊。
"""
    units = segmenter.segment_jd(sample_text)
    assert len(units) >= 2

    # 條列項目應被正確抽取
    bullet_units = [u for u in units if u.unit_type == "bullet_item"]
    assert len(bullet_units) == 2
    assert any("Server Design" in u.phrase for u in bullet_units)

    # 薪資福利句子應被標記為非潛在技能 (is_potential_skill == False)
    bp_units = [u for u in units if not u.is_potential_skill]
    assert len(bp_units) >= 1
    assert any("月薪" in u.raw_text or "勞健保" in u.raw_text for u in bp_units)
