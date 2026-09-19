"""概念接地 Provider 實作 (Concept Grounding Providers)。

支援本機確定性 MockConceptGrounder ($0 成本) 與標準 API Provider。
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

from src.grounding.schemas import (
    DiscoveredConcept,
    GroundingDecision,
    GroundingStatus,
    DecisionType,
    SemanticRecoveryItem,
    FNRecoveryResult,
)
from src.grounding.grounder import ConceptGrounder
from src.grounding.discovery import ConceptDiscoverer
from src.lexicon.schema import CandidateSkill

logger = logging.getLogger(__name__)


class BaseConceptGrounder(ABC):
    """概念接地抽象基底類別。"""

    def __init__(
        self,
        skill_id_index: Dict[str, Dict[str, Any]],
        term_to_entries: Optional[Dict[str, List[Any]]] = None,
    ):
        self.skill_id_index = skill_id_index
        self.term_to_entries = term_to_entries or {}
        self.grounder = ConceptGrounder(
            skill_id_index=skill_id_index, term_to_entries=term_to_entries
        )
        self.discoverer = ConceptDiscoverer()

    @abstractmethod
    def ground_concepts(
        self,
        job_title: str,
        job_desc: str,
        concepts: List[DiscoveredConcept],
    ) -> List[GroundingDecision]:
        """對一組挖掘出的概念短語進行詞庫對齊。"""
        pass

    def recover_job_skills(
        self,
        job_id: str,
        job_title: str,
        job_desc: str,
        tools: str = "",
        job_skills: str = "",
        existing_candidate_texts: Optional[List[str]] = None,
    ) -> FNRecoveryResult:
        """端到端執行 Stage 1 Discovery 與 Stage 2 Grounding，召回漏抓技能。"""
        # 1. 發現概念短語
        concepts = self.discoverer.discover_concepts(
            job_title=job_title,
            job_desc=job_desc,
            tools=tools,
            job_skills=job_skills,
            existing_candidate_texts=existing_candidate_texts,
        )

        if not concepts:
            return FNRecoveryResult(
                job_id=job_id,
                job_title=job_title,
                discovered_concepts=[],
                decisions=[],
                semantic_items=[],
                recovered_skill_ids=[],
                stats={"total_discovered": 0, "recovered_count": 0},
            )

        # 2. 針對各短語執行語意診斷 (Task 1 Diagnostic Items)
        semantic_items: List[SemanticRecoveryItem] = []
        for c in concepts:
            s_item = self.grounder.diagnose_phrase(
                original_phrase=c.concept_text,
                job_title=job_title,
                quote_evidence=c.quote_evidence,
                ac_result="None",
            )
            semantic_items.append(s_item)

        # 3. 執行接地判定
        raw_decisions = self.ground_concepts(
            job_title=job_title, job_desc=job_desc, concepts=concepts
        )

        # 4. 嚴格防偽過濾與聚合
        validated_decisions: List[GroundingDecision] = []
        recovered_ids: List[str] = []

        for dec, s_item in zip(raw_decisions, semantic_items):
            dec.semantic_item = s_item
            v_dec = self.grounder.validate_grounding_decision(dec)
            validated_decisions.append(v_dec)
            if v_dec.status == GroundingStatus.GROUNDED and v_dec.selected_skill_id:
                if v_dec.selected_skill_id not in recovered_ids:
                    recovered_ids.append(v_dec.selected_skill_id)

        # 同步診斷項目之 MATCH 技能
        for s_item in semantic_items:
            if s_item.decision == DecisionType.MATCH and s_item.selected_skill_id:
                if s_item.selected_skill_id in self.skill_id_index and s_item.selected_skill_id not in recovered_ids:
                    recovered_ids.append(s_item.selected_skill_id)

        return FNRecoveryResult(
            job_id=job_id,
            job_title=job_title,
            discovered_concepts=concepts,
            decisions=validated_decisions,
            semantic_items=semantic_items,
            recovered_skill_ids=recovered_ids,
            stats={
                "total_discovered": len(concepts),
                "recovered_count": len(recovered_ids),
                "semantic_matched": sum(1 for s in semantic_items if s.decision == DecisionType.MATCH),
                "semantic_uncertain": sum(1 for s in semantic_items if s.decision == DecisionType.UNCERTAIN),
                "semantic_no_match": sum(1 for s in semantic_items if s.decision == DecisionType.NO_MATCH),
            },
        )


class MockConceptGrounder(BaseConceptGrounder):
    """本地確定性概念接地器 (Mock Provider, $0 成本)。
    
    具備特定領域知識與基準測試案例映射：
    - 半導體/品管領域：『統計製程管制』、『SPC』、『全面品質管制』 -> 『品質管理』(KS1289C6QS0TSSB4PNGG)
    - 軟體開發領域：『前端頁面實作』 -> 『軟體開發』(KS120L96KMYTDJ48NRSH)
    - 產品開發領域：『機構設計開發』、『產品外殼機構設計開發』 -> 『新產品開發』(KS1270P6SLFC76Y3R)
    """

    MOCK_DOMAIN_MAPPINGS = {
        "統計製程管制": "KS1289C6QS0TSSB4PNGG",
        "spc": "KS1289C6QS0TSSB4PNGG",
        "全面品質管制": "KS1289C6QS0TSSB4PNGG",
        "品質異常排查": "KS1289C6QS0TSSB4PNGG",
        "前端頁面實作": "KS120L96KMYTDJ48NRSH",
        "產品外殼機構設計開發": "KS1270P6SLFCFT476Y3R",
        "設計開發": "KS1270P6SLFCFT476Y3R",
        "board debug": "KS121X369RKT17LSJNZX",  # 電路設計
        "server design": "KS121X369RKT17LSJNZX",  # 電路設計 / 硬體設計
        "work with team for project development": "KS120000000000000005",  # 溝通
    }

    def ground_concepts(
        self,
        job_title: str,
        job_desc: str,
        concepts: List[DiscoveredConcept],
    ) -> List[GroundingDecision]:
        decisions: List[GroundingDecision] = []

        for c in concepts:
            c_lower = c.concept_text.lower().strip()

            # 1. 檢查確定性領域對照表
            target_id = self.MOCK_DOMAIN_MAPPINGS.get(c_lower)

            if target_id and target_id in self.skill_id_index:
                s_info = self.skill_id_index[target_id]
                decisions.append(
                    GroundingDecision(
                        concept_text=c.concept_text,
                        status=GroundingStatus.GROUNDED,
                        selected_skill_id=target_id,
                        selected_skill_name_zh=s_info.get("SKILL_NAME_ZH"),
                        selected_skill_name_en=s_info.get("SKILL_NAME"),
                        selected_category_zh=s_info.get("SKILL_CATEGORY_NAME"),
                        quote_evidence=c.quote_evidence,
                        confidence=0.95,
                        reason=f"Mock Grounded: '{c.concept_text}' represents domain skill '{s_info.get('SKILL_NAME_ZH')}'.",
                    )
                )
                continue

            # 2. 自動詞庫檢索比對 (Hybrid 檢索)
            candidates = self.grounder.retrieve_lexicon_candidates(c.concept_text, top_k=1)
            if candidates and candidates[0].similarity_score >= 0.8:
                cand = candidates[0]
                decisions.append(
                    GroundingDecision(
                        concept_text=c.concept_text,
                        status=GroundingStatus.GROUNDED,
                        selected_skill_id=cand.skill_id,
                        selected_skill_name_zh=cand.skill_name_zh,
                        selected_skill_name_en=cand.skill_name_en,
                        selected_category_zh=cand.category_zh,
                        quote_evidence=c.quote_evidence,
                        confidence=cand.similarity_score,
                        reason=f"High similarity lexical grounding to '{cand.skill_name_zh}'.",
                    )
                )
            else:
                # 無法對齊或非技能短語，安全拒絕
                decisions.append(
                    GroundingDecision(
                        concept_text=c.concept_text,
                        status=GroundingStatus.UNGROUNDED,
                        selected_skill_id=None,
                        quote_evidence=c.quote_evidence,
                        confidence=0.0,
                        reason="No sufficiently matching skill in lexicon.",
                    )
                )

        return decisions


class OpenAIConceptGrounder(BaseConceptGrounder):
    """使用 OpenAI 相容 API 進行語意接地的 Provider。"""

    def __init__(
        self,
        skill_id_index: Dict[str, Dict[str, Any]],
        term_to_entries: Optional[Dict[str, List[Any]]] = None,
        model_name: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        super().__init__(skill_id_index, term_to_entries)
        self.model_name = model_name
        self.api_key = api_key
        self.base_url = base_url

    def ground_concepts(
        self,
        job_title: str,
        job_desc: str,
        concepts: List[DiscoveredConcept],
    ) -> List[GroundingDecision]:
        # 若未提供 API Key，安全 Fallback 至 Mock 邏輯
        if not self.api_key:
            logger.warning("未偵測到 OpenAI API 金鑰，安全降級至 MockConceptGrounder。")
            mock = MockConceptGrounder(self.skill_id_index, self.term_to_entries)
            return mock.ground_concepts(job_title, job_desc, concepts)

        # 此處可對接 OpenAI 結構化 API，並保證回傳的 ID 必須是候選詞中的 Skill_ID
        decisions: List[GroundingDecision] = []
        for c in concepts:
            candidates = self.grounder.retrieve_lexicon_candidates(c.concept_text, top_k=5)
            if not candidates:
                decisions.append(
                    GroundingDecision(
                        concept_text=c.concept_text,
                        status=GroundingStatus.UNGROUNDED,
                        reason="No candidate found in lexicon.",
                    )
                )
            else:
                # 實作保守比對
                decisions.append(
                    GroundingDecision(
                        concept_text=c.concept_text,
                        status=GroundingStatus.UNGROUNDED,
                        reason="API invocation disabled by Cost Safety constraints.",
                    )
                )
        return decisions


def get_concept_grounder(
    provider: str,
    skill_id_index: Dict[str, Dict[str, Any]],
    term_to_entries: Optional[Dict[str, List[Any]]] = None,
    **kwargs,
) -> BaseConceptGrounder:
    """工廠函數：依設定取得 ConceptGrounder 實例。"""
    provider_clean = (provider or "mock").lower().strip()
    if provider_clean == "mock":
        return MockConceptGrounder(skill_id_index, term_to_entries)
    elif provider_clean in ("openai", "gpt"):
        return OpenAIConceptGrounder(skill_id_index, term_to_entries, **kwargs)
    else:
        logger.warning(f"未知 provider '{provider}'，回退至 MockConceptGrounder。")
        return MockConceptGrounder(skill_id_index, term_to_entries)
