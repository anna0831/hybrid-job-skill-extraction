"""LLM Verification Layer 單元測試。

涵蓋：
1. Pydantic Schema 結構與列舉驗證
2. SQLite 本地快取（命中、未命中、過濾、統計、清理）
3. Few-shot Prompt 組裝與格式校驗
4. MockLLMVerifier 假陽性（薪資、教育訓練、清潔、研究所、跨部門語言）精準消除
5. 真實技能（True Positives）保留驗證
6. 幻覺防禦與 Fallback 安全機制
7. Factory 工廠函數驗證
"""

import os
import tempfile
import pytest
from src.lexicon.schema import CandidateSkill
from src.llm_verifier.schemas import (
    LLMVerdict,
    VerificationResult,
    BatchVerificationResponse,
)
from src.llm_verifier.cache import LLMCache
from src.llm_verifier.prompts import (
    SYSTEM_PROMPT,
    FEW_SHOT_EXAMPLES,
    build_verification_prompt,
)
from src.llm_verifier.providers import (
    MockLLMVerifier,
    get_llm_verifier,
)


class TestSchemas:
    """測試 Pydantic 驗證資料結構。"""

    def test_verification_result_valid(self):
        res = VerificationResult(
            skill_id="KS120000000000000007",
            skill_name_zh="Python",
            matched_keyword="Python",
            ac_match=True,
            llm_verdict=LLMVerdict.KEEP,
            confidence=0.98,
            evidence="熟悉 Python 後端開發",
            reason="明確為核心工作技能",
        )
        assert res.skill_id == "KS120000000000000007"
        assert res.llm_verdict == LLMVerdict.KEEP
        d = res.to_dict()
        assert d["llm_verdict"] == "KEEP"
        assert d["confidence"] == 0.98

    def test_batch_response_validation(self):
        item = {
            "skill_id": "TW_MFG_001",
            "skill_name_zh": "機台操作",
            "matched_keyword": "機台操作",
            "ac_match": True,
            "llm_verdict": "KEEP",
            "confidence": 0.95,
            "evidence": "負責機台操作",
            "reason": "工作內容第一項",
        }
        batch = BatchVerificationResponse(results=[VerificationResult(**item)])
        assert len(batch.results) == 1
        assert batch.results[0].llm_verdict == LLMVerdict.KEEP


class TestLLMCache:
    """測試 SQLite 呼叫快取機制。"""

    def test_cache_put_and_get(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_cache.db")
            cache = LLMCache(db_path=db_path)

            res = VerificationResult(
                skill_id="KS120000000000000007",
                skill_name_zh="Python",
                matched_keyword="Python",
                ac_match=True,
                llm_verdict=LLMVerdict.KEEP,
                confidence=0.99,
                evidence="需熟悉 Python",
                reason="核心條件",
            )

            # 初始未命中
            cached = cache.get(
                job_title="軟體工程師",
                job_desc="需熟悉 Python 程式設計",
                skill_id="KS120000000000000007",
                matched_keyword="Python",
                model_name="mock-model",
            )
            assert cached is None

            # 寫入快取
            cache.put(
                job_title="軟體工程師",
                job_desc="需熟悉 Python 程式設計",
                result=res,
                model_name="mock-model",
            )

            # 再次查詢應命中
            cached_after = cache.get(
                job_title="軟體工程師",
                job_desc="需熟悉 Python 程式設計",
                skill_id="KS120000000000000007",
                matched_keyword="Python",
                model_name="mock-model",
            )
            assert cached_after is not None
            assert cached_after.skill_id == "KS120000000000000007"
            assert cached_after.llm_verdict == LLMVerdict.KEEP

            # 驗證統計數字
            stats = cache.stats()
            assert stats["total_cached_records"] == 1
            assert stats["hit_count"] == 1
            assert stats["miss_count"] == 1

            # 清除快取
            cache.clear()
            assert cache.stats()["total_cached_records"] == 0

    def test_filter_cached(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_filter.db")
            cache = LLMCache(db_path=db_path)

            c1 = CandidateSkill(
                skill_id="KS001",
                skill_name="Python",
                skill_name_zh="Python",
                matched_keyword="Python",
                start_pos=0,
                end_pos=6,
                source_field="job_desc",
            )
            c2 = CandidateSkill(
                skill_id="KS002",
                skill_name="SQL",
                skill_name_zh="SQL",
                matched_keyword="SQL",
                start_pos=10,
                end_pos=13,
                source_field="job_desc",
            )

            # 預先存入 c1
            res1 = VerificationResult(
                skill_id="KS001",
                skill_name_zh="Python",
                matched_keyword="Python",
                ac_match=True,
                llm_verdict=LLMVerdict.KEEP,
                confidence=0.9,
                evidence="Python",
                reason="Hit",
            )
            cache.put("工程師", "熟悉 Python 與 SQL", res1, "m1")

            cached_res, uncached_cands = cache.filter_cached(
                "工程師", "熟悉 Python 與 SQL", [c1, c2], "m1"
            )
            assert len(cached_res) == 1
            assert cached_res[0].skill_id == "KS001"
            assert len(uncached_cands) == 1
            assert uncached_cands[0].skill_id == "KS002"


class TestPromptEngineering:
    """測試提示詞格式與建構。"""

    def test_build_prompt_structure(self):
        c1 = CandidateSkill(
            skill_id="KS120000000000000007",
            skill_name="Python",
            skill_name_zh="Python",
            matched_keyword="Python",
            start_pos=0,
            end_pos=6,
            source_field="job_desc",
        )
        messages = build_verification_prompt(
            job_title="後端研發",
            job_desc="主導 Python 系統開發",
            candidates=[c1],
            include_few_shot=True,
        )
        assert len(messages) > 1
        assert messages[0]["role"] == "system"
        assert "Aho-Corasick" in messages[0]["content"]
        assert "KEEP" in messages[0]["content"]
        assert messages[-1]["role"] == "user"
        assert "KS120000000000000007" in messages[-1]["content"]


class TestMockLLMVerifier:
    """測試 Mock 驗證器的假陽性消除與真技能保留邏輯。"""

    @pytest.fixture
    def verifier(self):
        return MockLLMVerifier()

    def test_reject_salary_benefit_false_positive(self, verifier):
        """測試薪資待遇假陽性消除 (GOLD_002 案型)。"""
        cands = [
            CandidateSkill(
                skill_id="KS120000000000000001",
                skill_name="Compensation Management",
                skill_name_zh="薪資管理",
                matched_keyword="月薪",
                start_pos=0,
                end_pos=2,
                source_field="job_desc",
            ),
            CandidateSkill(
                skill_id="KS120000000000000002",
                skill_name="Training and Development",
                skill_name_zh="訓練與發展",
                matched_keyword="教育訓練",
                start_pos=10,
                end_pos=14,
                source_field="job_desc",
            ),
            CandidateSkill(
                skill_id="KS120000000000000011",
                skill_name="Customer Reception",
                skill_name_zh="會客登記",
                matched_keyword="會客登記",
                start_pos=20,
                end_pos=24,
                source_field="job_desc",
            ),
        ]
        results = verifier.verify_candidates(
            job_title="行政會計專員",
            job_desc="負責日常總務事務、會客登記與訪客接待。底薪 32,000 元，月薪 35,000 元含全勤。公司提供完整教育訓練與員工旅遊。",
            candidates=cands,
        )

        res_dict = {r.skill_id: r for r in results}
        # 薪資管理應被 REJECT
        assert res_dict["KS120000000000000001"].llm_verdict == LLMVerdict.REJECT
        # 訓練與發展應被 REJECT
        assert res_dict["KS120000000000000002"].llm_verdict == LLMVerdict.REJECT
        # 會客登記應被 KEEP
        assert res_dict["KS120000000000000011"].llm_verdict == LLMVerdict.KEEP
        assert res_dict["KS120000000000000011"].evidence != ""

    def test_reject_cleaning_and_graduate_school_false_positive(self, verifier):
        """測試 5S 環境清潔與研究所學歷假陽性消除 (GOLD_003 案型)。"""
        cands = [
            CandidateSkill(
                skill_id="TW_MFG_001",
                skill_name="Machine Operation",
                skill_name_zh="機台操作",
                matched_keyword="機台操作",
                start_pos=0,
                end_pos=4,
                source_field="job_desc",
            ),
            CandidateSkill(
                skill_id="KS120000000000000006",
                skill_name="Cleaning Services",
                skill_name_zh="清潔",
                matched_keyword="清潔",
                start_pos=10,
                end_pos=12,
                source_field="job_desc",
            ),
            CandidateSkill(
                skill_id="KS120000000000000003",
                skill_name="Scientific Research",
                skill_name_zh="研究",
                matched_keyword="研究",
                start_pos=20,
                end_pos=22,
                source_field="job_desc",
            ),
        ]
        results = verifier.verify_candidates(
            job_title="塑膠射出機台操作員",
            job_desc="產線機台操作、日常設備保養與維護。工作環境每日需保持整潔清潔。學歷要求研究所畢業尤佳。",
            candidates=cands,
        )

        res_dict = {r.skill_id: r for r in results}
        assert res_dict["TW_MFG_001"].llm_verdict == LLMVerdict.KEEP
        assert res_dict["KS120000000000000006"].llm_verdict == LLMVerdict.REJECT
        assert res_dict["KS120000000000000003"].llm_verdict == LLMVerdict.REJECT

    def test_reject_collaborator_skill_false_positive(self, verifier):
        """測試跨部門協作者語言假陽性消除 (GOLD_014 案型)。"""
        cands = [
            CandidateSkill(
                skill_id="KS120L96KMYTDJ48NRSH",
                skill_name="Software Development",
                skill_name_zh="軟體開發",
                matched_keyword="前端頁面實作",
                start_pos=0,
                end_pos=6,
                source_field="job_desc",
            ),
            CandidateSkill(
                skill_id="KS120000000000000007",
                skill_name="Python",
                skill_name_zh="Python",
                matched_keyword="Python",
                start_pos=10,
                end_pos=16,
                source_field="job_desc",
            ),
        ]
        results = verifier.verify_candidates(
            job_title="Vue 前端工程師",
            job_desc="負責企業後台管理系統前端頁面實作，需與後端 Python 工程師密切溝通協調。",
            candidates=cands,
        )

        res_dict = {r.skill_id: r for r in results}
        assert res_dict["KS120L96KMYTDJ48NRSH"].llm_verdict == LLMVerdict.KEEP
        # 前端工程師不需要寫 Python
        assert res_dict["KS120000000000000007"].llm_verdict == LLMVerdict.REJECT

    def test_keep_genuine_cleaning_and_salary_skills(self, verifier):
        """測試在真正技能情境下 (GOLD_011 房務員, GOLD_012 薪酬師)，正確保留技能。"""
        # GOLD_011: 飯店客房清潔人員
        cands_clean = [
            CandidateSkill(
                skill_id="KS120000000000000006",
                skill_name="Cleaning Services",
                skill_name_zh="清潔",
                matched_keyword="清潔",
                start_pos=0,
                end_pos=2,
                source_field="job_desc",
            )
        ]
        res_clean = verifier.verify_candidates(
            job_title="飯店客房清潔人員",
            job_desc="負責客房退房後的環境打掃、床單更換與衛浴消毒清潔服務。",
            candidates=cands_clean,
        )
        assert res_clean[0].llm_verdict == LLMVerdict.KEEP

        # GOLD_012: 薪酬福利管理師
        cands_salary = [
            CandidateSkill(
                skill_id="KS120000000000000001",
                skill_name="Compensation Management",
                skill_name_zh="薪資管理",
                matched_keyword="薪資作業",
                start_pos=0,
                end_pos=4,
                source_field="job_desc",
            )
        ]
        res_salary = verifier.verify_candidates(
            job_title="薪酬福利管理師",
            job_desc="主導每月全公司員工薪資作業與薪資管理制度制定。",
            candidates=cands_salary,
        )
        assert res_salary[0].llm_verdict == LLMVerdict.KEEP


class TestFactoryAndFallback:
    """測試工廠函數與例外安全性。"""

    def test_get_verifier_factory(self):
        mock_v = get_llm_verifier(provider="mock")
        assert isinstance(mock_v, MockLLMVerifier)

        with pytest.raises(ValueError):
            get_llm_verifier(provider="unsupported_provider")

    def test_fallback_on_empty_or_broken_response(self):
        class BrokenVerifier(MockLLMVerifier):
            def _call_llm_api(self, messages):
                return "Not a valid JSON at all!"

        verifier = BrokenVerifier()
        cands = [
            CandidateSkill(
                skill_id="KS001",
                skill_name="Test",
                skill_name_zh="測試技能",
                matched_keyword="測試",
                start_pos=0,
                end_pos=2,
                source_field="job_desc",
            )
        ]
        results = verifier.verify_candidates(
            job_title="職缺", job_desc="職缺描述包含測試", candidates=cands
        )
        assert len(results) == 1
        assert results[0].llm_verdict == LLMVerdict.UNCERTAIN
