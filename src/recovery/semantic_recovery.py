"""殘差語意技能召回引擎 (Stage C-E: Residual Semantic Skill Recovery Engine)。

串聯殘差單元識別、詞庫約束雙語檢索與上下文驗證：
針對 AC 遺漏之工作內容單元，檢索 Top-5 詞庫候選，執行 MATCH / UNCERTAIN / NO_MATCH 判定，
將高置信度召回技能整合輸出，並保留完整審計追蹤紀錄。
"""

import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from src.lexicon.schema import CandidateSkill
from src.preprocessing.segmenter import SemanticUnit
from src.recovery.residual_detector import ResidualDetector
from src.retrieval.hybrid import HybridRetriever
from src.grounding.schemas import LexiconCandidate, DecisionType
from src.verifier.semantic_verifier import SemanticVerifier, SemanticVerificationOutput

logger = logging.getLogger(__name__)


class ResidualRecoveryResult(BaseModel):
    """殘差語意召回總體結果。"""
    job_id: str = Field(..., description="職缺編號")
    job_title: str = Field(default="", description="職缺名稱")
    residual_units: List[SemanticUnit] = Field(default_factory=list, description="偵測出之殘差單元清單")
    verification_outputs: List[SemanticVerificationOutput] = Field(default_factory=list, description="驗證決策明細")
    recovered_skills: List[CandidateSkill] = Field(default_factory=list, description="最終成功召回之技能物件清單")
    stats: Dict[str, Any] = Field(default_factory=dict, description="統計數據")


class ResidualSemanticRecoveryEngine:
    """殘差語意召回引擎。"""

    def __init__(
        self,
        skill_id_index: Dict[str, Dict[str, Any]],
        hybrid_retriever: Optional[HybridRetriever] = None,
        verifier: Optional[SemanticVerifier] = None,
        top_k: int = 5,
        match_threshold: float = 0.80,
        uncertain_threshold: float = 0.50,
        bypass_verification: bool = False,
        disable_retrieval: bool = False,
    ):
        self.skill_id_index = skill_id_index
        self.detector = ResidualDetector()
        self.retriever = hybrid_retriever or HybridRetriever(skill_id_index=skill_id_index)
        self.verifier = verifier or SemanticVerifier(
            skill_id_index=skill_id_index,
            match_threshold=match_threshold,
            uncertain_threshold=uncertain_threshold,
        )
        self.top_k = top_k
        self.bypass_verification = bypass_verification
        self.disable_retrieval = disable_retrieval

    def recover_residuals(
        self,
        job_id: str,
        job_title: str,
        job_desc: str,
        ac_matches: List[CandidateSkill],
        tools: str = "",
        job_skills: str = "",
    ) -> ResidualRecoveryResult:
        """對單篇職缺執行完整的殘差語意召回流程。"""
        # 1. 偵測未被 AC 涵蓋的殘差語意單元 (Stage C)
        residual_units = self.detector.detect_residuals(
            job_desc=job_desc,
            ac_matches=ac_matches,
            tools=tools,
            job_skills=job_skills,
        )

        if not residual_units or self.disable_retrieval:
            return ResidualRecoveryResult(
                job_id=job_id,
                job_title=job_title,
                residual_units=residual_units,
                verification_outputs=[],
                recovered_skills=[],
                stats={"total_residuals": len(residual_units), "recovered_count": 0},
            )

        verification_outputs: List[SemanticVerificationOutput] = []
        recovered_skills: List[CandidateSkill] = []
        seen_skill_ids = set(c.skill_id for c in ac_matches)

        for unit in residual_units:
            phrase = unit.phrase
            # 2. 詞庫約束雙語檢索 Top-K (Stage D)
            ranked_cands = self.retriever.retrieve(phrase, top_k=self.top_k, fusion_method="rrf")

            lexicon_cands: List[LexiconCandidate] = []
            for s_id, score in ranked_cands:
                if s_id in self.skill_id_index:
                    s_info = self.skill_id_index[s_id]
                    lexicon_cands.append(
                        LexiconCandidate(
                            skill_id=s_id,
                            skill_name_zh=s_info.get("SKILL_NAME_ZH", ""),
                            skill_name_en=s_info.get("SKILL_NAME", ""),
                            category_zh=s_info.get("SKILL_CATEGORY_NAME", ""),
                            similarity_score=score,
                        )
                    )

            # 3. 雙語上下文感知驗證 (Stage E)
            if self.bypass_verification:
                # Exp D: 無 Stage E 驗證，直接接受 Top-1 檢索候選 (若相似度 > 0.50)
                if lexicon_cands and lexicon_cands[0].similarity_score >= 0.50:
                    top_cand = lexicon_cands[0]
                    v_output = SemanticVerificationOutput(
                        source_phrase=phrase,
                        decision=DecisionType.MATCH,
                        skill_id=top_cand.skill_id,
                        skill_name=top_cand.skill_name_zh,
                        confidence=top_cand.similarity_score,
                        evidence=unit.raw_text,
                        reason="Bypassed verification (Top-1 retrieval candidate accepted directly)",
                    )
                else:
                    v_output = SemanticVerificationOutput(
                        source_phrase=phrase,
                        decision=DecisionType.NO_MATCH,
                        evidence=unit.raw_text,
                        reason="No retrieval candidate above threshold in unverified mode",
                    )
            else:
                v_output = self.verifier.verify_residual_candidate(
                    target_phrase=phrase,
                    job_title=job_title,
                    job_desc=job_desc,
                    top_k_candidates=lexicon_cands,
                    evidence=unit.raw_text,
                )
            verification_outputs.append(v_output)

            # 4. 若 MATCH 且未重複，聚合至召回技能清單
            if v_output.decision == DecisionType.MATCH and v_output.skill_id:
                s_id = v_output.skill_id
                if s_id in self.skill_id_index and s_id not in seen_skill_ids:
                    s_dict = self.skill_id_index[s_id]
                    recovered_cand = CandidateSkill(
                        skill_id=s_id,
                        skill_name=s_dict["SKILL_NAME"],
                        skill_name_zh=s_dict["SKILL_NAME_ZH"],
                        skill_type=s_dict.get("SKILL_TYPE", "Hard Skill"),
                        skill_cat9=s_dict.get("SKILL_CAT9", "Unclassified"),
                        category_code=s_dict.get("SKILL_CATEGORY", "0"),
                        category_name=s_dict.get("SKILL_CATEGORY_NAME", ""),
                        subcategory_code=s_dict.get("SKILL_SUBCATEGORY", "0"),
                        subcategory_name=s_dict.get("SKILL_SUBCATEGORY_NAME", ""),
                        is_software=s_dict.get("IS_SOFTWARE", False),
                        matched_keyword=f"[RESIDUAL:{phrase}]",
                        field_source="RESIDUAL_RECOVERY",
                        original_text=unit.raw_text,
                    )
                    recovered_skills.append(recovered_cand)
                    seen_skill_ids.add(s_id)

        stats = {
            "total_residuals": len(residual_units),
            "recovered_count": len(recovered_skills),
            "matched_count": sum(1 for v in verification_outputs if v.decision == DecisionType.MATCH),
            "uncertain_count": sum(1 for v in verification_outputs if v.decision == DecisionType.UNCERTAIN),
            "no_match_count": sum(1 for v in verification_outputs if v.decision == DecisionType.NO_MATCH),
        }

        return ResidualRecoveryResult(
            job_id=job_id,
            job_title=job_title,
            residual_units=residual_units,
            verification_outputs=verification_outputs,
            recovered_skills=recovered_skills,
            stats=stats,
        )
