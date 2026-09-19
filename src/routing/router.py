"""三軌風險分流決策引擎 (Risk-based Routing Engine)。

實作核心三軌分流架構：
1. 第一軌 (PASS_THROUGH, 約 75% 預算)：高置信度直接放行，零 API 成本與零延遲。
2. 第二軌 (VERIFY_CONTEXT, 約 20% 預算)：語意衝突或歧義候選詞，送入 LLM 驗證層。
3. 第三軌 (RECOVER_FN, 約 5% 預算)：零技能或漏抓職缺，標記送交概念檢索層。
"""

import logging
from typing import List, Dict, Any, Optional

from src.lexicon.schema import CandidateSkill
from src.routing.schemas import RouteTrack, SkillRouteDecision, JobRoutingResult
from src.routing.risk_detector import RiskDetector

logger = logging.getLogger(__name__)


class RiskBasedRouter:
    """以風險為基礎的動態決策路由器。"""

    def __init__(
        self,
        rules_path: str = "configs/rules.yaml",
        risk_threshold: Optional[float] = None,
    ):
        self.detector = RiskDetector(rules_path=rules_path)
        self.risk_threshold = (
            risk_threshold
            if risk_threshold is not None
            else self.detector.risk_threshold
        )

        # 全域累計統計數據
        self.total_jobs = 0
        self.total_candidates = 0
        self.pass_through_count = 0
        self.verify_context_count = 0
        self.zero_skill_jobs_count = 0

    def route_job(
        self,
        job_id: str,
        job_title: str,
        job_desc: str,
        candidates: List[CandidateSkill],
        tools: str = "",
        job_skills: str = "",
    ) -> JobRoutingResult:
        """對單篇職缺的所有候選技能執行風險分流。"""
        self.total_jobs += 1
        num_cands = len(candidates)
        self.total_candidates += num_cands

        # 第三軌檢查：若完全無候選技能，標記為需要漏抓補救 (RECOVER_FN)
        if num_cands == 0:
            self.zero_skill_jobs_count += 1
            logger.debug(f"職缺 {job_id} 候選技能數為 0，路由至第三軌 RECOVER_FN")
            return JobRoutingResult(
                job_id=job_id,
                job_title=job_title,
                pass_through_candidates=[],
                verify_candidates=[],
                needs_fn_recovery=True,
                decisions=[],
                stats={
                    "total_candidates": 0,
                    "pass_through_count": 0,
                    "verify_count": 0,
                    "track": RouteTrack.RECOVER_FN.value,
                },
            )

        pass_through_list: List[CandidateSkill] = []
        verify_list: List[CandidateSkill] = []
        decisions: List[SkillRouteDecision] = []

        for cand in candidates:
            score, reasons = self.detector.evaluate(
                candidate=cand,
                job_title=job_title,
                job_desc=job_desc,
                tools=tools,
                job_skills=job_skills,
            )

            if score >= self.risk_threshold:
                track = RouteTrack.VERIFY_CONTEXT
                verify_list.append(cand)
                self.verify_context_count += 1
            else:
                track = RouteTrack.PASS_THROUGH
                pass_through_list.append(cand)
                self.pass_through_count += 1

            decisions.append(
                SkillRouteDecision(
                    skill_id=cand.skill_id,
                    skill_name_zh=cand.skill_name_zh,
                    matched_keyword=cand.matched_keyword,
                    track=track,
                    risk_score=score,
                    risk_reasons=reasons,
                    candidate=cand,
                )
            )

        pass_ratio = len(pass_through_list) / num_cands if num_cands > 0 else 0.0
        verify_ratio = len(verify_list) / num_cands if num_cands > 0 else 0.0

        return JobRoutingResult(
            job_id=job_id,
            job_title=job_title,
            pass_through_candidates=pass_through_list,
            verify_candidates=verify_list,
            needs_fn_recovery=False,
            decisions=decisions,
            stats={
                "total_candidates": num_cands,
                "pass_through_count": len(pass_through_list),
                "verify_count": len(verify_list),
                "pass_through_ratio": round(pass_ratio, 4),
                "verify_ratio": round(verify_ratio, 4),
            },
        )

    def get_global_stats(self) -> Dict[str, Any]:
        """回傳路由器目前全域累計之分流統計與成本節約指標。"""
        total_cands = self.total_candidates
        pass_rate = (self.pass_through_count / total_cands) if total_cands > 0 else 0.0
        llm_trigger_rate = (
            (self.verify_context_count / total_cands) if total_cands > 0 else 0.0
        )
        zero_skill_rate = (
            (self.zero_skill_jobs_count / self.total_jobs)
            if self.total_jobs > 0
            else 0.0
        )

        return {
            "total_jobs_processed": self.total_jobs,
            "total_candidates_routed": total_cands,
            "pass_through_count": self.pass_through_count,
            "verify_context_count": self.verify_context_count,
            "zero_skill_jobs_count": self.zero_skill_jobs_count,
            "pass_through_rate": round(pass_rate, 4),
            "llm_trigger_rate": round(llm_trigger_rate, 4),
            "zero_skill_job_rate": round(zero_skill_rate, 4),
            "estimated_api_cost_reduction_pct": round(pass_rate * 100.0, 2),
        }

    def reset_stats(self):
        """重設統計數據。"""
        self.total_jobs = 0
        self.total_candidates = 0
        self.pass_through_count = 0
        self.verify_context_count = 0
        self.zero_skill_jobs_count = 0
