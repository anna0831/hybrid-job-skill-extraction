"""Risk-based Routing 決策引擎單元測試。

測試項目涵蓋：
1. RouteTrack 列舉與 Schema 結構完整性
2. RiskDetector 語意衝突特徵偵測（薪資、5S清潔、研究所學歷、跨團隊協作者、高信賴欄位放行）
3. RiskBasedRouter 三軌分流決策（直通放行、LLM 驗證、零技能補救）
4. 全域累計統計數據與 API 成本節約率計算
"""

import pytest
from src.lexicon.schema import CandidateSkill
from src.routing.schemas import RouteTrack, SkillRouteDecision, JobRoutingResult
from src.routing.risk_detector import RiskDetector
from src.routing.router import RiskBasedRouter


class TestRoutingSchemas:
    """測試路由資料模型。"""

    def test_route_track_enum(self):
        assert RouteTrack.PASS_THROUGH.value == "PASS_THROUGH"
        assert RouteTrack.VERIFY_CONTEXT.value == "VERIFY_CONTEXT"
        assert RouteTrack.RECOVER_FN.value == "RECOVER_FN"

    def test_skill_route_decision_dict(self):
        cand = CandidateSkill(
            skill_id="KS120000000000000007",
            skill_name="Python",
            skill_name_zh="Python",
            matched_keyword="Python",
        )
        dec = SkillRouteDecision(
            skill_id="KS120000000000000007",
            skill_name_zh="Python",
            matched_keyword="Python",
            track=RouteTrack.PASS_THROUGH,
            risk_score=0.1,
            risk_reasons=["低風險"],
            candidate=cand,
        )
        d = dec.to_dict()
        assert d["track"] == "PASS_THROUGH"
        assert d["risk_score"] == 0.1
        assert "低風險" in d["risk_reasons"]


class TestRiskDetector:
    """測試風險偵測器之衝突指標計算。"""

    @pytest.fixture
    def detector(self):
        return RiskDetector()

    def test_salary_benefit_conflict_high_risk(self, detector):
        """測試薪資福利待遇衝突 (GOLD_002 案型)。"""
        cand = CandidateSkill(
            skill_id="KS120000000000000001",
            skill_name="Compensation Management",
            skill_name_zh="薪資管理",
            matched_keyword="月薪",
            field_source="職位描述",
        )
        score, reasons = detector.evaluate(
            candidate=cand,
            job_title="行政會計專員",
            job_desc="底薪 32,000 元，月薪 35,000 元含全勤。提供完整員工培訓。",
        )
        assert score >= 0.8  # 高風險歧義詞 (0.45) + 薪資衝突 (0.50)
        assert any("薪酬/培訓" in r for r in reasons)

    def test_5s_cleaning_conflict_high_risk(self, detector):
        """測試 5S 環境整潔維持衝突 (GOLD_003 案型)。"""
        cand = CandidateSkill(
            skill_id="KS120000000000000006",
            skill_name="Cleaning Services",
            skill_name_zh="清潔",
            matched_keyword="清潔",
            field_source="職位描述",
        )
        score, reasons = detector.evaluate(
            candidate=cand,
            job_title="塑膠射出機台操作員",
            job_desc="機台操作日常保養。每日工作環境需保持整潔清潔。",
        )
        assert score >= 0.8
        assert any("5S 日常環境維持" in r for r in reasons)

    def test_academic_degree_conflict_high_risk(self, detector):
        """測試學歷機構名詞衝突 (GOLD_003 案型)。"""
        cand = CandidateSkill(
            skill_id="KS120000000000000003",
            skill_name="Scientific Research",
            skill_name_zh="研究",
            matched_keyword="研究",
            field_source="職位描述",
        )
        score, reasons = detector.evaluate(
            candidate=cand,
            job_title="塑膠射出機台操作員",
            job_desc="產線技術員。學歷要求研究所碩士畢業尤佳。",
        )
        assert score >= 0.8
        assert any("學歷要求（研究所）" in r for r in reasons)

    def test_collaborator_conflict_high_risk(self, detector):
        """測試跨團隊協作者衝突 (GOLD_014 案型)。"""
        cand = CandidateSkill(
            skill_id="KS120000000000000007",
            skill_name="Python",
            skill_name_zh="Python",
            matched_keyword="Python",
            field_source="職位描述",
        )
        score, reasons = detector.evaluate(
            candidate=cand,
            job_title="Vue 前端工程師",
            job_desc="負責企業後台管理系統前端頁面實作，需與後端 Python 工程師密切溝通協調。",
        )
        assert score >= 0.5
        assert any("前端" in r and "後端" in r for r in reasons)

    def test_high_trust_field_reduces_risk(self, detector):
        """測試來自結構化『工作技能』或『工具欄』之關鍵字獲得信用放行。"""
        cand_free = CandidateSkill(
            skill_id="KS120000000000000004",
            skill_name="Equipment Maintenance",
            skill_name_zh="設備維護",
            matched_keyword="維護",
            field_source="職位描述",
        )
        cand_tool = CandidateSkill(
            skill_id="KS120000000000000004",
            skill_name="Equipment Maintenance",
            skill_name_zh="設備維護",
            matched_keyword="維護",
            field_source="工作技能",
        )

        score_free, _ = detector.evaluate(
            cand_free, "工程師", "負責系統與機台設備維護"
        )
        score_tool, _ = detector.evaluate(
            cand_tool, "工程師", "負責系統與機台設備維護"
        )
        assert score_tool < score_free


class TestRiskBasedRouter:
    """測試三軌分流路由器行為。"""

    @pytest.fixture
    def router(self):
        return RiskBasedRouter()

    def test_route_standard_job_pass_through(self, router):
        """標準軟體工程職缺：無歧義技能直接走第一軌 (PASS_THROUGH)。"""
        cands = [
            CandidateSkill(
                skill_id="KS120L96KMYTDJ48NRSH",
                skill_name="Software Development",
                skill_name_zh="軟體開發",
                matched_keyword="軟體開發",
                field_source="職位描述",
            ),
            CandidateSkill(
                skill_id="KS120000000000000008",
                skill_name="SQL",
                skill_name_zh="SQL",
                matched_keyword="SQL",
                field_source="工具欄",
            ),
        ]
        result = router.route_job(
            job_id="GOLD_001",
            job_title="Python 後端工程師",
            job_desc="負責後端 API 開發與架構規劃，需熟悉 SQL 資料庫調優。",
            candidates=cands,
        )

        assert not result.needs_fn_recovery
        assert len(result.pass_through_candidates) == 2
        assert len(result.verify_candidates) == 0
        assert result.stats["pass_through_ratio"] == 1.0

    def test_route_risky_job_splits_tracks(self, router):
        """高誤判風險職缺 (GOLD_003)：機台操作走第一軌，清潔與研究精準切入第二軌 (VERIFY_CONTEXT)。"""
        cands = [
            CandidateSkill(
                skill_id="TW_MFG_001",
                skill_name="Machine Operation",
                skill_name_zh="機台操作",
                matched_keyword="機台操作",
                field_source="工作技能",
            ),
            CandidateSkill(
                skill_id="KS120000000000000006",
                skill_name="Cleaning Services",
                skill_name_zh="清潔",
                matched_keyword="清潔",
                field_source="職位描述",
            ),
            CandidateSkill(
                skill_id="KS120000000000000003",
                skill_name="Scientific Research",
                skill_name_zh="研究",
                matched_keyword="研究",
                field_source="職位描述",
            ),
        ]
        result = router.route_job(
            job_id="GOLD_003",
            job_title="塑膠射出機台操作員",
            job_desc="產線機台操作、日常設備保養。工作環境每日需保持整潔清潔。學歷要求研究所畢業尤佳。",
            candidates=cands,
        )

        assert not result.needs_fn_recovery
        # 機台操作 (來自工作技能且符合職位) 走第一軌
        assert len(result.pass_through_candidates) == 1
        assert result.pass_through_candidates[0].skill_id == "TW_MFG_001"

        # 清潔 與 研究 走第二軌
        assert len(result.verify_candidates) == 2
        verify_ids = {c.skill_id for c in result.verify_candidates}
        assert "KS120000000000000006" in verify_ids
        assert "KS120000000000000003" in verify_ids

    def test_route_zero_skill_job_enters_track3(self, router):
        """零技能職缺 (GOLD_008)：觸發第三軌漏抓補救 (RECOVER_FN)。"""
        result = router.route_job(
            job_id="GOLD_008",
            job_title="半導體良率改善工程師",
            job_desc="主導晶圓產線 defect reduction 與統計製程管制 SPC。",
            candidates=[],
        )

        assert result.needs_fn_recovery is True
        assert len(result.pass_through_candidates) == 0
        assert len(result.verify_candidates) == 0
        assert result.stats["track"] == RouteTrack.RECOVER_FN.value

    def test_global_stats_and_budget_tracking(self, router):
        """測試全域累計統計與成本節約率計算。"""
        router.reset_stats()

        # Job 1: 2 技能全部直通
        c1 = [
            CandidateSkill(skill_id="1", skill_name="A", skill_name_zh="軟體開發", matched_keyword="軟體開發", field_source="工作技能"),
            CandidateSkill(skill_id="2", skill_name="B", skill_name_zh="SQL", matched_keyword="SQL", field_source="工作技能"),
        ]
        router.route_job("J1", "工程師", "寫程式", c1)

        # Job 2: 1 直通, 1 驗證
        c2 = [
            CandidateSkill(skill_id="3", skill_name="C", skill_name_zh="機台操作", matched_keyword="機台操作", field_source="工作技能"),
            CandidateSkill(skill_id="4", skill_name="D", skill_name_zh="清潔", matched_keyword="清潔", field_source="職位描述"),
        ]
        router.route_job("J2", "技術員", "保持整潔清潔", c2)

        # Job 3: 0 技能
        router.route_job("J3", "未知", "無技能描述", [])

        stats = router.get_global_stats()
        assert stats["total_jobs_processed"] == 3
        assert stats["total_candidates_routed"] == 4
        assert stats["pass_through_count"] == 3
        assert stats["verify_context_count"] == 1
        assert stats["zero_skill_jobs_count"] == 1
        # pass_through_rate = 3 / 4 = 75%
        assert stats["pass_through_rate"] == 0.75
        # llm_trigger_rate = 1 / 4 = 25%
        assert stats["llm_trigger_rate"] == 0.25
        # 成本節約率 75%
        assert stats["estimated_api_cost_reduction_pct"] == 75.0


class TestHybridPipelineIntegration:
    """測試整合 AC + Router + LLM Verifier 的混合式擷取管線。"""

    @pytest.fixture
    def pipeline(self):
        import tempfile
        import os
        from src.hybrid_pipeline import HybridJobSkillPipeline

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = os.path.join(tmpdir, "test_hybrid_cache.db")
            pipe = HybridJobSkillPipeline(
                lexicon_path="lexicon/sample/mini_skill_lexicon.csv",
                rules_path="configs/rules.yaml",
                verifier_provider="mock",
                cache_db_path=cache_path,
            )
            yield pipe

    def test_hybrid_pipeline_eliminates_gold_002_fps(self, pipeline):
        """GOLD_002 行政會計：AC 命中薪資管理與訓練，Hybrid 管線精準剔除，僅保留會客登記。"""
        final_skills, routing_res, verif_records = pipeline.extract_job_skills(
            job_id="GOLD_002",
            job_title="行政會計專員",
            job_desc="負責日常總務事務、會客登記與訪客接待。底薪 32,000 元，月薪 35,000 元含全勤。公司提供完整教育訓練與員工旅遊。",
            tools="Excel, Word",
            job_skills="會客登記, 文書處理",
        )
        final_ids = {s.skill_id for s in final_skills}
        # 薪資管理 (KS120000000000000001) 與 訓練與發展 (KS120000000000000002) 必須被剔除
        assert "KS120000000000000001" not in final_ids
        assert "KS120000000000000002" not in final_ids
        # 會客登記 必須被保留
        assert "KS120000000000000011" in final_ids

    def test_hybrid_pipeline_eliminates_gold_003_fps(self, pipeline):
        """GOLD_003 塑膠射出操作員：AC 命中清潔與研究，Hybrid 管線精準剔除，保留機台操作與設備維護。"""
        final_skills, routing_res, verif_records = pipeline.extract_job_skills(
            job_id="GOLD_003",
            job_title="塑膠射出機台操作員",
            job_desc="產線機台操作、日常設備保養與維護。工作環境每日需保持整潔清潔。學歷要求研究所畢業尤佳。",
            tools="傳統車床",
            job_skills="機台操作",
        )
        final_ids = {s.skill_id for s in final_skills}
        # 清潔 與 研究 必須被剔除
        assert "KS120000000000000006" not in final_ids
        assert "KS120000000000000003" not in final_ids
        # 機台操作 必須被保留
        assert "TW_MFG_001" in final_ids

    def test_hybrid_pipeline_eliminates_gold_014_collaborator_fp(self, pipeline):
        """GOLD_014 Vue 前端：AC 額外命中協作夥伴 Python，Hybrid 管線精準剔除。"""
        final_skills, routing_res, verif_records = pipeline.extract_job_skills(
            job_id="GOLD_014",
            job_title="Vue 前端工程師",
            job_desc="負責企業後台管理系統前端頁面實作，需與後端 Python 工程師密切溝通協調。",
            tools="Vue.js, Git",
            job_skills="JavaScript, Vue",
        )
        final_ids = {s.skill_id for s in final_skills}
        # Python 必須被剔除
        assert "KS120000000000000007" not in final_ids
        # 且 Python 在 LLM 驗證層被精準判定為 REJECT
        rejected_ids = {
            r.skill_id for r in verif_records if r.llm_verdict.value == "REJECT"
        }
        assert "KS120000000000000007" in rejected_ids

    def test_hybrid_pipeline_keeps_genuine_skills_gold_001(self, pipeline):
        """GOLD_001 Python 後端：軟體開發、Python、SQL、溝通等真正技能全數通過並保留。"""
        final_skills, routing_res, verif_records = pipeline.extract_job_skills(
            job_id="GOLD_001",
            job_title="Python 後端工程師",
            job_desc="負責後端 API 開發與架構規劃，需熟悉 Python 與 SQL 資料庫調優。具備跨部門溝通協調能力者佳。",
            tools="Python, PostgreSQL, Docker",
            job_skills="Python, SQL, 軟體開發",
        )
        final_ids = {s.skill_id for s in final_skills}
        # Python、SQL、軟體開發、溝通 皆應保留
        assert "KS120000000000000007" in final_ids  # Python
        assert "KS120000000000000008" in final_ids  # SQL
        assert "KS120L96KMYTDJ48NRSH" in final_ids  # 軟體開發
        assert "KS120000000000000005" in final_ids  # 溝通


