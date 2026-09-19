"""第二階段：嚴格詞庫接地引擎 (Stage 2: Constrained Lexicon Grounder)。

將 Stage 1 挖掘出的概念短語，嚴格映射至 Lightcast 既有詞庫之合法 Skill_ID。
若無法在詞庫中找到對應項目，強制判定為 UNGROUNDED，絕對杜絕模型幻覺與自行發明技能。
"""

import logging
from typing import List, Dict, Any, Optional, Tuple, Set

from src.grounding.schemas import (
    DiscoveredConcept,
    LexiconCandidate,
    GroundingDecision,
    GroundingStatus,
    FNRecoveryResult,
)
from src.grounding.discovery import ConceptDiscoverer

logger = logging.getLogger(__name__)


def char_jaccard_similarity(s1: str, s2: str) -> float:
    """計算兩中文字串的字元級 Jaccard 相似度。"""
    set1, set2 = set(s1), set(s2)
    if not set1 or not set2:
        return 0.0
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union > 0 else 0.0


class ConceptGrounder:
    """詞庫約束概念接地引擎。"""

    def __init__(
        self,
        skill_id_index: Dict[str, Dict[str, Any]],
        term_to_entries: Optional[Dict[str, List[Any]]] = None,
        min_similarity_threshold: float = 0.4,
    ):
        """
        Args:
            skill_id_index: 詞庫由 Skill_ID 映射至相容字典的索引表
            term_to_entries: AC 詞條倒排索引（可選）
            min_similarity_threshold: 候選召回之最低字元相似度門檻
        """
        self.skill_id_index = skill_id_index
        self.term_to_entries = term_to_entries or {}
        self.min_similarity_threshold = min_similarity_threshold
        self.discoverer = ConceptDiscoverer()

    def retrieve_lexicon_candidates(
        self, concept_text: str, top_k: int = 5
    ) -> List[LexiconCandidate]:
        """從詞庫中檢索與概念短語最相關的 Top-K 候選技能。"""
        c_clean = concept_text.strip().lower()
        candidates: List[LexiconCandidate] = []
        seen_skill_ids: Set[str] = set()

        # 1. 優先精確比對（包含英文名稱與中文名稱完全相同者）
        for s_id, s_info in self.skill_id_index.items():
            name_zh = s_info.get("SKILL_NAME_ZH", "").strip().lower()
            name_en = s_info.get("SKILL_NAME", "").strip().lower()

            if c_clean == name_zh or c_clean == name_en:
                candidates.append(
                    LexiconCandidate(
                        skill_id=s_id,
                        skill_name_zh=s_info.get("SKILL_NAME_ZH", ""),
                        skill_name_en=s_info.get("SKILL_NAME", ""),
                        category_zh=s_info.get("SKILL_CATEGORY_NAME", ""),
                        similarity_score=1.0,
                    )
                )
                seen_skill_ids.add(s_id)
                if len(candidates) >= top_k:
                    return candidates

        # 2. 模糊與字元重疊檢索 (Character Overlap / Jaccard)
        scored_candidates: List[Tuple[float, str, Dict[str, Any]]] = []
        for s_id, s_info in self.skill_id_index.items():
            if s_id in seen_skill_ids:
                continue

            name_zh = s_info.get("SKILL_NAME_ZH", "").strip()
            name_en = s_info.get("SKILL_NAME", "").strip().lower()

            # 計算中文相似度
            score_zh = char_jaccard_similarity(c_clean, name_zh)
            # 若為子字串給予加權
            if c_clean in name_zh or name_zh in c_clean:
                score_zh = max(score_zh, 0.7)

            # 計算英文包含
            score_en = 0.0
            if len(c_clean) >= 3 and c_clean in name_en:
                score_en = 0.65

            best_score = max(score_zh, score_en)
            if best_score >= self.min_similarity_threshold:
                scored_candidates.append((best_score, s_id, s_info))

        # 排序取 Top-K
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        for score, s_id, s_info in scored_candidates[:top_k]:
            candidates.append(
                LexiconCandidate(
                    skill_id=s_id,
                    skill_name_zh=s_info.get("SKILL_NAME_ZH", ""),
                    skill_name_en=s_info.get("SKILL_NAME", ""),
                    category_zh=s_info.get("SKILL_CATEGORY_NAME", ""),
                    similarity_score=round(score, 4),
                )
            )

        return candidates

    def validate_grounding_decision(self, decision: GroundingDecision) -> GroundingDecision:
        """嚴格防偽檢驗 (Strict Lexicon Boundary Guard)。
        
        任何回傳的 selected_skill_id 必須真實存在於 self.skill_id_index。
        若模型回傳不存在的 ID，強制覆寫為 UNGROUNDED，徹底杜絕幻覺。
        """
        if decision.status == GroundingStatus.GROUNDED:
            if not decision.selected_skill_id or decision.selected_skill_id not in self.skill_id_index:
                logger.warning(
                    f"防偽攔截：選定技能 ID '{decision.selected_skill_id}' 不在詞庫中！強制重設為 UNGROUNDED。"
                )
                return GroundingDecision(
                    concept_text=decision.concept_text,
                    status=GroundingStatus.UNGROUNDED,
                    selected_skill_id=None,
                    selected_skill_name_zh=None,
                    selected_skill_name_en=None,
                    quote_evidence=decision.quote_evidence,
                    confidence=0.0,
                    reason=f"Rejected: Skill_ID '{decision.selected_skill_id}' does not exist in lexicon.",
                )
            # 補齊標準詞庫名稱以求一致
            skill_info = self.skill_id_index[decision.selected_skill_id]
            decision.selected_skill_name_zh = skill_info.get("SKILL_NAME_ZH", "")
            decision.selected_skill_name_en = skill_info.get("SKILL_NAME", "")
            decision.selected_category_zh = skill_info.get("SKILL_CATEGORY_NAME", "")

        return decision
