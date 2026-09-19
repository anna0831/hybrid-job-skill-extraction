"""LLM 驗證層資料結構定義 (Pydantic Schemas)。"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class LLMVerdict(str, Enum):
    """LLM 對候選技能的判決列舉。"""
    KEEP = "KEEP"            # 職缺內容確實要求、描述或明確涉及這項專業技能
    REJECT = "REJECT"        # keyword 雖然出現，但屬於福利、薪資、學歷、產品或非技能語境
    UNCERTAIN = "UNCERTAIN"  # 上下文資訊不足，無法可靠判定


class VerificationResult(BaseModel):
    """單一候選技能的 LLM 驗證結果結構。"""
    skill_id: str = Field(..., description="唯一技能代碼 (與輸入之 Skill_ID 嚴格一致)")
    skill_name_zh: str = Field(..., description="技能中文名稱")
    matched_keyword: str = Field(..., description="AC 命中之關鍵字")
    ac_match: bool = Field(default=True, description="是否由 AC Matcher 所產出")
    llm_verdict: LLMVerdict = Field(..., description="判決結論：KEEP | REJECT | UNCERTAIN")
    confidence: float = Field(
        default=0.9, ge=0.0, le=1.0, description="模型判斷置信度 (0.0 ~ 1.0)"
    )
    evidence: str = Field(..., description="引用職缺原文節錄作為判斷依據 (必須為原文子字串)")
    reason: str = Field(..., description="判斷理由說明")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "skill_name_zh": self.skill_name_zh,
            "matched_keyword": self.matched_keyword,
            "ac_match": self.ac_match,
            "llm_verdict": self.llm_verdict.value,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "reason": self.reason,
        }


class BatchVerificationResponse(BaseModel):
    """批次候選技能驗證的回應容器。"""
    results: List[VerificationResult] = Field(
        default_factory=list, description="該篇職缺所有候選技能之驗證列表"
    )
