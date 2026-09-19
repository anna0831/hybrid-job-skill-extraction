"""兩階段概念接地與假陰性召回資料模型 (Two-Stage Concept Grounding Schemas)。"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class GroundingStatus(str, Enum):
    """接地狀態列舉。"""
    GROUNDED = "GROUNDED"        # 成功對齊至詞庫已知 Skill_ID
    UNGROUNDED = "UNGROUNDED"    # 無法在詞庫中找到對應技能，強制拒絕
    AMBIGUOUS = "AMBIGUOUS"      # 候選過多且無法確定，保守放棄


class DiscoveredConcept(BaseModel):
    """第一階段：從職缺內文挖掘出的潛在技能短語 (Stage 1 Discovered Concept)。"""
    concept_text: str = Field(..., description="從內文抽取出的潛在技能詞彙或短語，如『統計製程管制』、『SPC』")
    quote_evidence: str = Field(..., description="原文引用語句作為依據，如『主導晶圓產線 defect reduction 與統計製程管制 SPC』")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="短語抽取信心度")
    source_field: str = Field(default="job_desc", description="來源欄位：job_desc, tools, job_skills 等")


class LexiconCandidate(BaseModel):
    """候選詞庫技能項目 (Lexicon Retrieval Candidate)。"""
    skill_id: str = Field(..., description="Lightcast 技能 ID")
    skill_name_zh: str = Field(..., description="中文標準技能名稱")
    skill_name_en: str = Field(..., description="英文標準技能名稱")
    category_zh: str = Field(default="", description="9 大類中文技能分類")
    similarity_score: float = Field(default=0.0, ge=0.0, le=1.0, description="語意或字串匹配相似度")


class GroundingDecision(BaseModel):
    """第二階段：概念接地判定結果 (Stage 2 Grounding Decision)。"""
    concept_text: str = Field(..., description="待接地的概念短語")
    status: GroundingStatus = Field(..., description="接地狀態")
    selected_skill_id: Optional[str] = Field(default=None, description="選定的合法 Skill_ID，若未接地則為 None")
    selected_skill_name_zh: Optional[str] = Field(default=None, description="選定的中文標準技能名稱")
    selected_skill_name_en: Optional[str] = Field(default=None, description="選定的英文標準技能名稱")
    selected_category_zh: Optional[str] = Field(default=None, description="選定的 9 大類中文分類")
    quote_evidence: str = Field(default="", description="原文依據")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="接地判定信心度")
    reason: str = Field(default="", description="接地或拒絕之判定理由")


class FNRecoveryResult(BaseModel):
    """單篇職缺之假陰性召回整合結果 (FN Recovery Summary)。"""
    job_id: str = Field(..., description="職缺編號")
    job_title: str = Field(default="", description="職稱")
    discovered_concepts: List[DiscoveredConcept] = Field(default_factory=list, description="挖掘出的概念短語清單")
    decisions: List[GroundingDecision] = Field(default_factory=list, description="接地決策清單")
    recovered_skill_ids: List[str] = Field(default_factory=list, description="最終成功召回之 Skill_ID 清單")
    stats: Dict[str, Any] = Field(default_factory=dict, description="統計數據")
