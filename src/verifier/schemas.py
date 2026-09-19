"""上下文感知技能驗證資料模型 (Context-Aware Verification Schemas)。"""

from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class VerificationVerdict(str, Enum):
    """上下文假陽性驗證決策 (Stage B Verdict)。"""
    ACCEPT = "ACCEPT"        # 經上下文判定為真實專業技能
    REJECT = "REJECT"        # 判定為假陽性 (福利、學歷、招聘雜訊或領域衝突)
    UNCERTAIN = "UNCERTAIN"  # 語境模糊或資訊不足，保守標記


class VerificationRecord(BaseModel):
    """單一候選技能之上下文驗證審計紀錄。"""
    skill_id: str = Field(..., description="候選技能 ID")
    skill_name_zh: str = Field(..., description="技能中文名稱")
    matched_keyword: str = Field(..., description="AC 命中之關鍵字")
    context: str = Field(default="", description="關鍵字周圍之上下文片段")
    evidence: str = Field(default="", description="職缺內文之原文佐證語句")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="驗證置信度")
    verdict: VerificationVerdict = Field(..., description="驗證結果：ACCEPT / REJECT / UNCERTAIN")
    reason: str = Field(default="", description="判定理由說明")
