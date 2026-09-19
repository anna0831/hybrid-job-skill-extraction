"""語意單元切分與殘差標記模組 (Semantic Unit Segmenter & Residual Tagger)。

負責將非結構化職缺描述 (JD) 切分為語意單元 (條列項目、句子、工作職責短語)，
並比對 Aho-Corasick 已命中之字元跨度或關鍵字，標記出「已覆蓋單元」與「未覆蓋/殘差單元 (Residual Units)」。
"""

import re
import logging
from typing import List, Dict, Any, Optional, Set
from pydantic import BaseModel, Field

from src.preprocessing.normalizer import clean_text
from src.lexicon.schema import CandidateSkill

logger = logging.getLogger(__name__)


class SemanticUnit(BaseModel):
    """單一語意單元資料模型 (Semantic Unit)。"""
    unit_id: int = Field(..., description="單元序號 (0-indexed)")
    raw_text: str = Field(..., description="未經清洗之原始單元文字")
    phrase: str = Field(..., description="正規化後之候選核心短語")
    unit_type: str = Field(default="sentence", description="單元類型：bullet_item, sentence, clause")
    start_pos: Optional[int] = Field(default=None, description="在原文中之起始字元索引")
    end_pos: Optional[int] = Field(default=None, description="在原文中之結束字元索引")
    is_covered: bool = Field(default=False, description="是否已被現有 AC 技能涵蓋")
    covering_skills: List[str] = Field(default_factory=list, description="涵蓋本單元之 AC 技能名稱或 ID")
    is_potential_skill: bool = Field(default=True, description="是否具備潛在技能特徵 (排除薪資、福利與免責聲明)")
    source_field: str = Field(default="job_desc", description="來源欄位")


class JDSegmenter:
    """職缺描述語意切分與殘差偵測器。"""

    # 常見條列項目正規表達式 (1. xxx, 2. xxx, - xxx, • xxx)
    BULLET_PATTERN = re.compile(r"^\s*(?:\d+[\.、\)\s]+|[-*•]\s*)(.+)$")

    # 常見句子分隔符
    SENTENCE_SPLIT_PATTERN = re.compile(r"[。！？；;\n\r]+")

    # 非技能干擾詞與招募模板排除庫 (Boilerplate & Benefits Filter)
    BOILERPLATE_PATTERNS = [
        re.compile(r"(?:底薪|月薪|年終|全勤|津貼|獎金|勞健保|供餐|員工旅遊|保險|面議|休假|排班|輪班|週休)"),
        re.compile(r"(?:公司提供|工作環境|福利待遇|相關科系|男女不拘|無經驗可|歡迎社會新鮮人|自備車輛)"),
        re.compile(r"(?:上班地點|上班時間|休假制度|職務聯絡人|應徵方式|聯絡電話)"),
        re.compile(r"^【(?:工作內容|職位要求|條件要求|應徵條件|具備條件)】$"),
    ]

    def __init__(self, min_phrase_len: int = 2, max_phrase_len: int = 60):
        self.min_phrase_len = min_phrase_len
        self.max_phrase_len = max_phrase_len

    def is_boilerplate(self, text: str) -> bool:
        """判定該單元是否為招聘行政、薪酬福利或公司介紹等非技能雜訊。"""
        t = text.strip()
        if not t:
            return True
        for pat in self.BOILERPLATE_PATTERNS:
            if pat.search(t):
                return True
        return False

    def segment_jd(self, job_desc: str) -> List[SemanticUnit]:
        """將職缺文字切分為語意單元列表。"""
        if not job_desc or not isinstance(job_desc, str):
            return []

        units: List[SemanticUnit] = []
        unit_idx = 0
        current_offset = 0

        lines = job_desc.splitlines()
        for line in lines:
            line_str = line.strip()
            if not line_str:
                current_offset += len(line) + 1
                continue

            # 1. 優先檢測條列項目 (如 1. Server Design, 2. Board debug ...)
            bullet_match = self.BULLET_PATTERN.match(line_str)
            if bullet_match:
                content = bullet_match.group(1).strip()
                cleaned = clean_text(content)
                is_bp = self.is_boilerplate(content)
                if len(cleaned) >= self.min_phrase_len:
                    units.append(
                        SemanticUnit(
                            unit_id=unit_idx,
                            raw_text=line_str,
                            phrase=cleaned,
                            unit_type="bullet_item",
                            start_pos=current_offset,
                            end_pos=current_offset + len(line_str),
                            is_covered=False,
                            is_potential_skill=not is_bp,
                            source_field="job_desc_bullet",
                        )
                    )
                    unit_idx += 1
            else:
                # 2. 非條列式文字，以句號/分號/換行切割為子句
                sub_sentences = self.SENTENCE_SPLIT_PATTERN.split(line_str)
                for sent in sub_sentences:
                    sent_str = sent.strip()
                    if not sent_str:
                        continue
                    cleaned = clean_text(sent_str)
                    is_bp = self.is_boilerplate(sent_str)
                    if len(cleaned) >= self.min_phrase_len:
                        units.append(
                            SemanticUnit(
                                unit_id=unit_idx,
                                raw_text=sent_str,
                                phrase=cleaned,
                                unit_type="sentence",
                                is_covered=False,
                                is_potential_skill=not is_bp,
                                source_field="job_desc",
                            )
                        )
                        unit_idx += 1

            current_offset += len(line) + 1

        return units

    def identify_residuals(
        self,
        job_desc: str,
        ac_matches: List[CandidateSkill],
    ) -> List[SemanticUnit]:
        """切分語意單元並對照 AC 命中結果，標記覆蓋狀態，回傳未覆蓋的殘差單元。
        
        Args:
            job_desc: 職缺描述內文
            ac_matches: Aho-Corasick 擷取出的 CandidateSkill 列表
            
        Returns:
            未被 AC 涵蓋且具備潛在技能特徵之殘差語意單元 (Residual Units)
        """
        units = self.segment_jd(job_desc)
        if not units:
            return []

        # 收集 AC 命中的關鍵字與小寫字串
        ac_terms = set()
        for cand in ac_matches:
            kw = cand.matched_keyword.strip().lower()
            if kw:
                ac_terms.add(kw)
            zh = cand.skill_name_zh.strip().lower()
            if zh:
                ac_terms.add(zh)

        residual_units: List[SemanticUnit] = []

        for unit in units:
            unit_phrase_lower = unit.phrase.lower()

            # 檢查 AC 關鍵字是否出現在此單元中
            covered_by = []
            for term in ac_terms:
                if term in unit_phrase_lower:
                    covered_by.append(term)

            if covered_by:
                unit.is_covered = True
                unit.covering_skills = covered_by
            else:
                unit.is_covered = False
                if unit.is_potential_skill and len(unit.phrase) <= self.max_phrase_len:
                    residual_units.append(unit)

        return residual_units
