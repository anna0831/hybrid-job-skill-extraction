"""第一階段：概念發現模組 (Stage 1: Concept Discovery)。

從職缺標題、內文、工具與工作技能欄位中，挖掘尚未被 AC 詞庫覆蓋的專業技術、方法論或能力短語。
提供啟發式規則抽取 (Heuristic Extraction) 與 LLM 提示詞介面。
"""

import re
import logging
from typing import List, Dict, Any, Optional
import jieba

from src.grounding.schemas import DiscoveredConcept
from src.preprocessing.normalizer import clean_text

logger = logging.getLogger(__name__)


class ConceptDiscoverer:
    """概念發現器：負責從非結構化職缺文字中提取候選技能短語。"""

    # 常見技能與方法論字尾模式 (Chinese Skill Suffix Patterns)
    SKILL_PATTERNS = [
        re.compile(r"[\u4e00-\u9fa5]{2,10}(?:管制|排查|調校|量測|優化|改善|分析|開發|維護|管理|設計|測試|演算|建模|製作|撰寫|建置|協調|溝通)"),
        re.compile(r"(?:撰寫|製作|規劃|建置|維護|操作|設計|開發|分析)[\u4e00-\u9fa5]{2,8}"),
        re.compile(r"\b[A-Za-z0-9\+\#\.\-]+(?:\s+[A-Za-z0-9\+\#\.\-]+){1,5}\b"),  # 英文複合工作短語，如 Documents creation, Board debug
        re.compile(r"\b[A-Za-z0-9\+\#\.\-]{2,15}\b"),  # 英文縮寫與專有名詞，如 SPC, JMP, CI/CD, PyTorch, BOM
    ]

    # 常見非技能干擾詞 (Stopwords / False Alarm Patterns)
    STOP_PHRASES = {
        "工作環境", "公司提供", "工作內容", "相關經驗", "相關科系", "良好體力",
        "配合排班", "夜間排班", "男女不拘", "無經驗可", "抗壓性高",
        "主導", "負責", "協助", "具備", "熟悉", "配合", "執行", "確保", "工作", "內容",
    }

    def __init__(self, stopwords: Optional[set] = None):
        self.stopwords = stopwords or self.STOP_PHRASES

    def discover_concepts(
        self,
        job_title: str,
        job_desc: str,
        tools: str = "",
        job_skills: str = "",
        existing_candidate_texts: Optional[List[str]] = None,
    ) -> List[DiscoveredConcept]:
        """從職缺多個欄位中發現候選技能短語。
        
        Args:
            job_title: 職位名稱
            job_desc: 職位描述
            tools: 擅長工具欄位
            job_skills: 工作技能欄位
            existing_candidate_texts: 已被 AC 命中的關鍵字清單（用於去重避免重複處理）
            
        Returns:
            DiscoveredConcept 物件清單
        """
        existing_set = set(t.lower().strip() for t in (existing_candidate_texts or []))
        discovered: Dict[str, DiscoveredConcept] = {}

        # 1. 優先從 104 結構化欄位 (job_skills, tools) 抽取
        for field_name, field_text in [("tools", tools), ("job_skills", job_skills)]:
            if not field_text:
                continue
            parts = re.split(r"[,、;/\s]+", field_text)
            for part in parts:
                p_clean = clean_text(part)
                if len(p_clean) >= 2 and p_clean.lower() not in existing_set and p_clean not in self.stopwords:
                    discovered[p_clean.lower()] = DiscoveredConcept(
                        concept_text=p_clean,
                        quote_evidence=field_text,
                        confidence=0.9,
                        source_field=field_name,
                    )

        # 2. 逐行分析職位描述 (job_desc) 中的列舉項目 (如 1. Server Design, 2. Board debug ...)
        raw_lines = job_desc.splitlines()
        for raw_line in raw_lines:
            line_str = raw_line.strip()
            if not line_str:
                continue

            # 檢測條列編號 (如 1. xxx, 2. xxx, - xxx, • xxx)
            bullet_match = re.match(r"^(?:\d+[\.、\)\s]+|[-*•]\s*)(.+)$", line_str)
            if bullet_match:
                item_text = bullet_match.group(1).strip()
                item_clean = clean_text(item_text)
                item_lower = item_clean.lower()
                if (
                    len(item_clean) >= 2
                    and item_lower not in existing_set
                    and item_clean not in self.stopwords
                    and not item_clean.isdigit()
                ):
                    discovered[item_lower] = DiscoveredConcept(
                        concept_text=item_clean,
                        quote_evidence=raw_line.strip(),
                        confidence=0.85,
                        source_field="job_desc_bullet",
                    )

        # 3. 從斷句中進行正規表達式模式比對
        sentences = re.split(r"[。！？\n\r]+", job_desc)
        for sent in sentences:
            sent_clean = clean_text(sent)
            if not sent_clean:
                continue

            # 比對中文技能模式與英文短語
            for pattern in self.SKILL_PATTERNS:
                for match in pattern.finditer(sent_clean):
                    phrase = match.group(0).strip()
                    phrase_clean = clean_text(phrase)
                    phrase_lower = phrase_clean.lower()

                    # 過濾過短、純數字、停用詞或完全已被 AC 命中詞
                    if (
                        len(phrase_clean) < 2
                        or phrase_lower in existing_set
                        or phrase_clean in self.stopwords
                        or phrase_clean.isdigit()
                    ):
                        continue

                    if phrase_lower not in discovered:
                        discovered[phrase_lower] = DiscoveredConcept(
                            concept_text=phrase_clean,
                            quote_evidence=sent.strip(),
                            confidence=0.8,
                            source_field="job_desc",
                        )

        return list(discovered.values())

    @staticmethod
    def build_discovery_prompt(
        job_title: str,
        job_desc: str,
        tools: str = "",
        job_skills: str = "",
    ) -> str:
        """建立用於 LLM 抽取未知技能短語之提示詞 (Prompt)。"""
        return f"""你是一名資深技術招聘專家與技能分析師。請分析以下 104 職缺，找出文章中明確要求或提及的所有「專業技術、工具、工程方法或專業技能」短語。

【職位名稱】: {job_title}
【擅長工具】: {tools or "無"}
【工作技能】: {job_skills or "無"}
【工作內容】:
{job_desc}

【抽取規則】:
1. 僅抽取職缺中「明確提及」的具體技術、工具、方法論（如：統計製程管制、SPC、CI/CD、JMP、全面品質管制）。
2. 不得抽取通用工作態度（如：抗壓、配合加班、具備責任心）。
3. 必須提供職缺中的「原文依據」(quote_evidence)。
4. 請以 JSON 陣列格式輸出，格式：
[
  {{"concept_text": "統計製程管制", "quote_evidence": "主導晶圓產線 defect reduction 與統計製程管制 SPC"}},
  {{"concept_text": "SPC", "quote_evidence": "主導晶圓產線 defect reduction 與統計製程管制 SPC"}}
]
"""
