"""雙語上下文感知語意驗證器 (Bilingual Context-Aware Semantic Verifier)。

整合 Stage B 假陽性驗證與 Stage E 殘差語意候選驗證：
針對目標短語、職缺完整上下文與 Top-K 詞庫候選，輸出嚴格結構化判定，
杜絕模型幻覺，落實嚴格詞庫邊界防護。
"""

import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from src.lexicon.schema import CandidateSkill
from src.grounding.schemas import LexiconCandidate, DecisionType
from src.verifier.schemas import VerificationVerdict, VerificationRecord
from src.verifier.base import BaseVerifier, MockVerifier

logger = logging.getLogger(__name__)


class SemanticVerificationOutput(BaseModel):
    """Stage E 殘差語意候選驗證輸出結構。"""
    source_phrase: str = Field(..., description="職缺中抽取之原始目標短語")
    skill_id: Optional[str] = Field(default=None, description="選定之合法 Skill_ID (若 MATCH)")
    skill_name: Optional[str] = Field(default=None, description="選定之標準中文技能名稱")
    decision: DecisionType = Field(..., description="決策：MATCH | UNCERTAIN | NO_MATCH")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="驗證置信度")
    evidence: str = Field(..., description="來自原始職缺之佐證依據")
    reason: str = Field(default="", description="判定理由說明")


class SemanticVerifier:
    """雙語上下文感知驗證器。"""

    def __init__(
        self,
        skill_id_index: Dict[str, Dict[str, Any]],
        verifier: Optional[BaseVerifier] = None,
        match_threshold: float = 0.60,
        uncertain_threshold: float = 0.45,
    ):
        self.skill_id_index = skill_id_index
        self.verifier = verifier or MockVerifier()
        self.match_threshold = match_threshold
        self.uncertain_threshold = uncertain_threshold

    def verify_ac_match(
        self,
        candidate: CandidateSkill,
        job_title: str,
        job_desc: str,
        tools: str = "",
        job_skills: str = "",
    ) -> VerificationRecord:
        """Stage B: 驗證 AC 候選技能是否為上下文假陽性。"""
        return self.verifier.verify_candidate(
            candidate=candidate,
            job_title=job_title,
            job_desc=job_desc,
            tools=tools,
            job_skills=job_skills,
        )

    def verify_residual_candidate(
        self,
        target_phrase: str,
        job_title: str,
        job_desc: str,
        top_k_candidates: List[LexiconCandidate],
        evidence: str = "",
    ) -> SemanticVerificationOutput:
        """Stage E: 對殘差單元之 Top-K 候選技能執行雙語上下文驗證。
        
        嚴格鐵律：
        1. 候選技能必須存在於詞庫中。
        2. 若無充分支持，判定為 NO_MATCH。
        3. 若具備歧義或關聯稍弱，判定為 UNCERTAIN。
        4. 絕不自行發明新技能名稱。
        """
        if not top_k_candidates:
            return SemanticVerificationOutput(
                source_phrase=target_phrase,
                skill_id=None,
                skill_name=None,
                decision=DecisionType.NO_MATCH,
                confidence=0.0,
                evidence=evidence or target_phrase,
                reason="詞庫中無任何相關候選項目",
            )

        top_cand = top_k_candidates[0]
        score = top_cand.similarity_score

        # 檢驗候選 ID 是否真實存在於詞庫中
        if top_cand.skill_id not in self.skill_id_index:
            return SemanticVerificationOutput(
                source_phrase=target_phrase,
                skill_id=None,
                skill_name=None,
                decision=DecisionType.NO_MATCH,
                confidence=0.0,
                evidence=evidence or target_phrase,
                reason="安全性攔截：候選 Skill_ID 不存在於合法詞庫中",
            )

        # 決策判定 (包含領域消歧與邊界差異判定)
        second_score = top_k_candidates[1].similarity_score if len(top_k_candidates) > 1 else 0.0
        if score >= self.match_threshold:
            title_lower = (job_title or "").lower()
            top1_cat = (top_cand.category_zh or "").lower()
            top2_cat = (top_k_candidates[1].category_zh or "").lower() if len(top_k_candidates) > 1 else ""

            is_eng_job = any(k in title_lower for k in ["工程", "硬體", "電子", "研發", "engineer", "hardware"])
            top1_is_eng = any(k in top1_cat for k in ["製造", "工程", "技術", "資訊", "it", "manufacturing"])
            top2_is_eng = any(k in top2_cat for k in ["製造", "工程", "技術", "資訊", "it", "manufacturing"])

            if len(top_k_candidates) > 1 and (score - second_score < 0.15) and is_eng_job:
                if top1_is_eng and not top2_is_eng:
                    decision = DecisionType.MATCH
                    conf = score
                    sel_id = top_cand.skill_id
                    sel_name = top_cand.skill_name_zh
                    reason = f"語意與領域支持：短語 '{target_phrase}' 與工程職位領域相符，消歧後判定為 '{sel_name}' ({top_cand.skill_name_en})"
                elif top2_is_eng and not top1_is_eng:
                    top2 = top_k_candidates[1]
                    decision = DecisionType.MATCH
                    conf = second_score
                    sel_id = top2.skill_id
                    sel_name = top2.skill_name_zh
                    reason = f"語意與領域支持：短語 '{target_phrase}' 與工程職位領域相符，消歧後選擇工程領域技能 '{sel_name}' ({top2.skill_name_en}) 排除跨領域 '{top_cand.skill_name_zh}'"
                elif score < 0.70 and (score - second_score < 0.05):
                    decision = DecisionType.UNCERTAIN
                    conf = score
                    sel_id = None
                    sel_name = None
                    reason = f"候選歧義：短語 '{target_phrase}' 與多個候選相似度過於接近 (Top 1: {top_cand.skill_name_zh} {score:.4f}, Top 2: {top_k_candidates[1].skill_name_zh} {second_score:.4f})，留存人工審核"
                else:
                    decision = DecisionType.MATCH
                    conf = score
                    sel_id = top_cand.skill_id
                    sel_name = top_cand.skill_name_zh
                    reason = f"語意強烈支持：短語 '{target_phrase}' 與詞庫標準技能 '{sel_name}' ({top_cand.skill_name_en}) 高度吻合"
            elif is_eng_job and not top1_is_eng and any(k in top1_cat for k in ["設計與媒體", "視覺", "media", "visual", "個人照顧"]):
                decision = DecisionType.NO_MATCH
                conf = score
                sel_id = None
                sel_name = None
                reason = f"領域衝突：工程職位短語 '{target_phrase}' 檢索出非工程領域技能 '{top_cand.skill_name_zh}' ({top_cand.category_zh})，安全駁回"
            elif score < 0.70 and len(top_k_candidates) > 1 and (score - second_score < 0.05):
                decision = DecisionType.UNCERTAIN
                conf = score
                sel_id = None
                sel_name = None
                reason = f"候選歧義：短語 '{target_phrase}' 與多個候選相似度過於接近 (Top 1: {top_cand.skill_name_zh} {score:.4f}, Top 2: {top_k_candidates[1].skill_name_zh} {second_score:.4f})，留存人工審核"
            else:
                decision = DecisionType.MATCH
                conf = score
                sel_id = top_cand.skill_id
                sel_name = top_cand.skill_name_zh
                reason = f"語意強烈支持：短語 '{target_phrase}' 與詞庫標準技能 '{sel_name}' ({top_cand.skill_name_en}) 高度吻合"
        elif score >= self.uncertain_threshold:
            decision = DecisionType.UNCERTAIN
            conf = score
            sel_id = None
            sel_name = None
            reason = f"語意模糊或關聯普通：短語 '{target_phrase}' 與候選 '{top_cand.skill_name_zh}' 關聯度未達明確門檻，留存人工審核"
        else:
            decision = DecisionType.NO_MATCH
            conf = score
            sel_id = None
            sel_name = None
            reason = f"語意支持不足：短語 '{target_phrase}' 與詞庫中現有技能均無充分吻合"

        return SemanticVerificationOutput(
            source_phrase=target_phrase,
            skill_id=sel_id,
            skill_name=sel_name,
            decision=decision,
            confidence=round(conf, 4),
            evidence=evidence or target_phrase,
            reason=reason,
        )
