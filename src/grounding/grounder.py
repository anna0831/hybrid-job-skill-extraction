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
    DecisionType,
    SemanticRecoveryItem,
    FNRecoveryResult,
)
from src.grounding.discovery import ConceptDiscoverer
from src.retrieval.hybrid import HybridRetriever
from src.preprocessing.normalizer import clean_text

logger = logging.getLogger(__name__)


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
        self.hybrid_retriever = HybridRetriever(skill_id_index=skill_id_index)

    def retrieve_lexicon_candidates(
        self, concept_text: str, top_k: int = 5
    ) -> List[LexiconCandidate]:
        """從既有詞庫中檢索與概念短語最相關的 Top-K 候選技能 (嚴格約束於詞庫宇宙)。"""
        c_clean = concept_text.strip().lower()
        candidates: List[LexiconCandidate] = []
        seen_skill_ids = set()

        # 1. 優先精確比對（中文或英文名稱完全一致者，給予 1.0）
        for s_id, s_info in self.skill_id_index.items():
            name_zh = (s_info.get("SKILL_NAME_ZH") or "").strip().lower()
            name_en = (s_info.get("SKILL_NAME") or "").strip().lower()

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

        # 2. Hybrid (BM25 + Dense) 語意檢索
        ranked = self.hybrid_retriever.retrieve(concept_text, top_k=top_k * 2, fusion_method="rrf")

        for s_id, score in ranked:
            if s_id in seen_skill_ids or s_id not in self.skill_id_index:
                continue
            s_info = self.skill_id_index[s_id]
            candidates.append(
                LexiconCandidate(
                    skill_id=s_id,
                    skill_name_zh=s_info.get("SKILL_NAME_ZH", ""),
                    skill_name_en=s_info.get("SKILL_NAME", ""),
                    category_zh=s_info.get("SKILL_CATEGORY_NAME", ""),
                    similarity_score=round(score, 4),
                )
            )
            seen_skill_ids.add(s_id)
            if len(candidates) >= top_k:
                break

        return candidates

    def compare_retrieval(
        self, concept_text: str, top_k: int = 5
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Task 2 檢索對比：同時取得 BM25, Dense, Hybrid 候選。"""
        cmp_raw = self.hybrid_retriever.compare_retrieval(concept_text, top_k=top_k)
        cmp_result: Dict[str, List[Dict[str, Any]]] = {}

        for method, items in cmp_raw.items():
            res_list = []
            for s_id, score in items:
                if s_id in self.skill_id_index:
                    info = self.skill_id_index[s_id]
                    res_list.append({
                        "skill_id": s_id,
                        "skill_name_zh": info.get("SKILL_NAME_ZH", ""),
                        "skill_name_en": info.get("SKILL_NAME", ""),
                        "score": score,
                    })
            cmp_result[method] = res_list

        return cmp_result

    def diagnose_phrase(
        self,
        original_phrase: str,
        job_title: str,
        quote_evidence: str,
        ac_result: str = "None",
        match_threshold: float = 0.80,
        uncertain_threshold: float = 0.50,
    ) -> SemanticRecoveryItem:
        """Task 1 假陰性診斷核心：分析單一短語並輸出完整診斷項目。"""
        norm_phrase = clean_text(original_phrase).lower()
        candidates = self.retrieve_lexicon_candidates(original_phrase, top_k=5)

        cand_ids = [c.skill_id for c in candidates]
        cand_names = [f"{c.skill_name_zh} ({c.skill_name_en})" for c in candidates]
        top_cand = candidates[0] if candidates else None
        best_score = top_cand.similarity_score if top_cand else 0.0

        if top_cand:
            semantic_interp = f"語意對齊詞庫技能: {top_cand.skill_name_zh} ({top_cand.skill_name_en})"
        else:
            semantic_interp = "詞庫中無足夠相似之既有技能"

        # 決策邏輯 (MATCH / UNCERTAIN / NO_MATCH)
        if best_score >= match_threshold and top_cand:
            decision = DecisionType.MATCH
            conf = best_score
            selected_id = top_cand.skill_id
            selected_name_zh = top_cand.skill_name_zh
        elif best_score >= uncertain_threshold and top_cand:
            decision = DecisionType.UNCERTAIN
            conf = best_score
            selected_id = None
            selected_name_zh = None
        else:
            decision = DecisionType.NO_MATCH
            conf = best_score
            selected_id = None
            selected_name_zh = None

        # 嚴格防偽防幻覺約束 (Strict Anti-Hallucination Guard)
        if decision == DecisionType.MATCH:
            if not selected_id or selected_id not in self.skill_id_index:
                decision = DecisionType.NO_MATCH
                selected_id = None
                selected_name_zh = None

        return SemanticRecoveryItem(
            original_phrase=original_phrase,
            normalized_phrase=norm_phrase,
            semantic_interpretation=semantic_interp,
            candidate_skill_ids=cand_ids,
            candidate_skill_names=cand_names,
            retrieval_score=round(best_score, 4),
            evidence=quote_evidence,
            confidence=round(conf, 4),
            decision=decision,
            selected_skill_id=selected_id,
            selected_skill_name_zh=selected_name_zh,
            ac_result=ac_result,
        )

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
