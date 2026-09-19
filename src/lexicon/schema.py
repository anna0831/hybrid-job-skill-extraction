"""資料模型定義模組：定義詞庫項目、候選技能與驗證結果之型別架構。"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class SkillEntry(BaseModel):
    """詞庫中單一技能項目的資料模型。"""
    skill_id: str = Field(..., description="唯一技能代碼 (如 Lightcast KS ID 或自訂 TW ID)")
    skill_name: str = Field(..., description="英文技能名稱")
    skill_name_zh: str = Field(..., description="繁體中文技能名稱")
    skill_type: str = Field(default="Hard Skill", description="技能類型 (Hard Skill / Soft Skill)")
    skill_cat9: str = Field(default="Unclassified", description="9 大分類名稱 (英文)")
    category_code: str = Field(default="0", description="大分類代碼")
    category_name: str = Field(default="", description="大分類名稱")
    subcategory_code: str = Field(default="0", description="子分類代碼")
    subcategory_name: str = Field(default="", description="子分類名稱")
    is_software: bool = Field(default=False, description="是否屬於軟體資訊類技能")


class CandidateSkill(BaseModel):
    """Aho-Corasick 或 Retrieval 階段產出的候選技能模型。"""
    skill_id: str
    skill_name: str
    skill_name_zh: str
    skill_type: str = Field(default="Hard Skill", description="技能類型 (Hard Skill / Soft Skill)")
    skill_cat9: str = Field(default="Unclassified", description="9 大分類名稱 (英文)")
    category_code: str = Field(default="0", description="大分類代碼")
    category_name: str = Field(default="", description="大分類名稱")
    subcategory_code: str = Field(default="0", description="子分類代碼")
    subcategory_name: str = Field(default="", description="子分類名稱")
    is_software: bool = Field(default=False, description="是否屬於軟體資訊類技能")
    matched_keyword: str = Field(..., description="在職缺文字中命中之關鍵字")
    field_source: str = Field(default="職位描述", description="命中來源欄位 (職位描述 / 工作技能 / 工具欄 / 職稱消歧 / 就近文意)")
    start_pos: Optional[int] = Field(default=None, description="命中關鍵字之起始字元索引")
    end_pos: Optional[int] = Field(default=None, description="命中關鍵字之結束字元索引")
    original_text: Optional[str] = Field(default=None, description="命中之完整原文或句子")

    def to_dict(self) -> Dict[str, Any]:
        """轉為與原系統相容的字典格式。"""
        d = {
            "SKILL_ID": self.skill_id,
            "SKILL_NAME": self.skill_name,
            "SKILL_NAME_ZH": self.skill_name_zh,
            "SKILL_TYPE": self.skill_type,
            "SKILL_CAT9": self.skill_cat9,
            "SKILL_CATEGORY": self.category_code,
            "SKILL_CATEGORY_NAME": self.category_name,
            "SKILL_SUBCATEGORY": self.subcategory_code,
            "SKILL_SUBCATEGORY_NAME": self.subcategory_name,
            "IS_SOFTWARE": self.is_software,
            "MATCHED_KEYWORD": self.matched_keyword,
            "MATCHED_FROM": self.field_source,
        }
        if self.start_pos is not None:
            d["START_POS"] = self.start_pos
        if self.end_pos is not None:
            d["END_POS"] = self.end_pos
        if self.original_text is not None:
            d["ORIGINAL_TEXT"] = self.original_text
        return d
