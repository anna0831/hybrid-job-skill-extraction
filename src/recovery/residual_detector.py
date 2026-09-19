"""殘差文字偵測器 (Stage C: Residual Semantic Detector)。

負責對比 AC 已擷取技能與職缺全文，精準找出尚未被任何技能解釋的工作描述單元。
適用於 skill_count == 0、skill_count == 1、skill_count == 2 及所有部分覆蓋職缺。
"""

import logging
from typing import List, Dict, Any, Optional

from src.preprocessing.segmenter import JDSegmenter, SemanticUnit
from src.lexicon.schema import CandidateSkill

logger = logging.getLogger(__name__)


class ResidualDetector:
    """殘差語意單元偵測器。"""

    def __init__(self, segmenter: Optional[JDSegmenter] = None):
        self.segmenter = segmenter or JDSegmenter()

    def detect_residuals(
        self,
        job_desc: str,
        ac_matches: List[CandidateSkill],
        tools: str = "",
        job_skills: str = "",
    ) -> List[SemanticUnit]:
        """偵測未被現有 AC 候選技能涵蓋之語意殘差單元。
        
        Args:
            job_desc: 職位描述
            ac_matches: AC 階段已命中之技能
            tools: 擅長工具
            job_skills: 工作技能
            
        Returns:
            未覆蓋之 SemanticUnit 清單
        """
        # 1. 對職位描述執行切分與殘差標記
        residual_units = self.segmenter.identify_residuals(
            job_desc=job_desc, ac_matches=ac_matches
        )

        # 2. 補充檢查結構化欄位 (job_skills, tools) 中尚未被 AC 涵蓋的詞項
        ac_skill_ids = set(c.skill_id for c in ac_matches)
        ac_terms = set(c.matched_keyword.lower() for c in ac_matches)

        for field_name, field_text in [("job_skills", job_skills), ("tools", tools)]:
            if not field_text or not isinstance(field_text, str):
                continue
            import re
            parts = re.split(r"[,、;/\s]+", field_text)
            for part in parts:
                p_clean = part.strip()
                if len(p_clean) >= 2 and p_clean.lower() not in ac_terms:
                    # 建立結構化欄位之殘差單元
                    residual_units.append(
                        SemanticUnit(
                            unit_id=len(residual_units),
                            raw_text=p_clean,
                            phrase=p_clean,
                            unit_type="structured_field",
                            is_covered=False,
                            is_potential_skill=True,
                            source_field=field_name,
                        )
                    )

        return residual_units
