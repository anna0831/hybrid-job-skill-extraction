"""風險分流路由器資料模型 (Routing Schemas)。

定義三軌分流列舉、單項候選技能分流決策，以及整篇職缺的分流結果容器。
"""

from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from src.lexicon.schema import CandidateSkill


class RouteTrack(str, Enum):
    """路由分流軌道。"""
    PASS_THROUGH = "PASS_THROUGH"    # 第一軌：高置信度直接放行 (預算約 75%，0 API 成本，0 ms 延遲)
    VERIFY_CONTEXT = "VERIFY_CONTEXT" # 第二軌：高風險語境消歧 (預算約 20%，送入 LLM 驗證層)
    RECOVER_FN = "RECOVER_FN"         # 第三軌：零技能/低召回補救 (預算約 5%，標記送入概念檢索層)


class SkillRouteDecision(BaseModel):
    """針對單一候選技能之分流決策。"""
    skill_id: str = Field(..., description="技能代碼")
    skill_name_zh: str = Field(..., description="技能中文名稱")
    matched_keyword: str = Field(..., description="AC 命中關鍵字")
    track: RouteTrack = Field(..., description="分流軌道 (PASS_THROUGH | VERIFY_CONTEXT)")
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0, description="風險分數 (0.0 ~ 1.0)")
    risk_reasons: List[str] = Field(default_factory=list, description="風險特徵觸發理由清單")
    candidate: CandidateSkill = Field(..., description="原始候選技能物件")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "skill_name_zh": self.skill_name_zh,
            "matched_keyword": self.matched_keyword,
            "track": self.track.value,
            "risk_score": round(self.risk_score, 3),
            "risk_reasons": self.risk_reasons,
        }


class JobRoutingResult(BaseModel):
    """整篇職缺的比對分流綜合結果。"""
    job_id: str = Field(default="", description="職缺 ID")
    job_title: str = Field(default="", description="職位名稱")
    pass_through_candidates: List[CandidateSkill] = Field(
        default_factory=list, description="直通放行之候選技能清單"
    )
    verify_candidates: List[CandidateSkill] = Field(
        default_factory=list, description="需送交 LLM 裁決之高風險候選技能清單"
    )
    needs_fn_recovery: bool = Field(
        default=False, description="是否為零技能或低召回職缺，需進入第三軌漏抓補救"
    )
    decisions: List[SkillRouteDecision] = Field(
        default_factory=list, description="各候選技能的詳細決策紀錄"
    )
    stats: Dict[str, Any] = Field(
        default_factory=dict, description="本職缺分流統計數據"
    )
    fn_recovery_result: Optional[Any] = Field(
        default=None, description="第三軌概念接地與 FN 召回詳細結果"
    )
