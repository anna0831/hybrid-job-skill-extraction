"""詞庫載入器模組：負責讀取 Excel/CSV 詞庫、註冊 Jieba 詞庫並生成 AC 詞條對照表。"""

import logging
from typing import Dict, List, Tuple, Set, Any
import pandas as pd
import yaml
import jieba

from src.preprocessing.boundary import has_chinese
from src.lexicon.schema import SkillEntry
from src.lexicon.expander import expand_synonyms, get_stemmed_term

logger = logging.getLogger(__name__)


class LexiconLoader:
    """詞庫載入與索引構建器。"""

    def __init__(
        self,
        rules_path: str = "configs/rules.yaml",
        synonyms_path: str = "configs/synonyms.yaml",
    ):
        with open(rules_path, "r", encoding="utf-8") as f:
            self.rules = yaml.safe_load(f)
        with open(synonyms_path, "r", encoding="utf-8") as f:
            self.synonyms_config = yaml.safe_load(f)

        self.jieba_whitelist: Set[str] = set(self.rules.get("jieba_2char_whitelist", []))
        self.zh_allowlist: Set[str] = set(self.rules.get("zh_2char_skill_allowlist", []))
        self.software_categories: Set[int] = set(self.rules.get("software_categories", []))
        self.synonym_groups: List[Set[str]] = [
            set(g) for g in self.synonyms_config.get("synonym_groups", [])
        ]

    def load_lexicon(
        self, lexicon_path: str
    ) -> Tuple[Dict[str, List[Tuple[int, Dict[str, Any], bool]]], Dict[str, Dict[str, Any]]]:
        """讀取指定路徑詞庫檔案 (CSV 或 Excel)，回傳 term_to_entries 與 skill_id_index。"""
        logger.info(f"載入詞庫檔案：{lexicon_path}")
        if lexicon_path.endswith(".csv"):
            df = pd.read_csv(lexicon_path)
        else:
            df = pd.read_excel(lexicon_path)

        # 預先將領域 2 字詞註冊至 jieba
        for w in self.jieba_whitelist:
            jieba.add_word(w, freq=1000)

        jcount = 0
        term_to_entries: Dict[str, List[Tuple[int, Dict[str, Any], bool]]] = {}
        skill_id_index: Dict[str, Dict[str, Any]] = {}

        for _, row in df.iterrows():
            try:
                cat_code = int(row.get("Category_Code", 0))
            except (ValueError, TypeError):
                cat_code = 0

            skill_entry = SkillEntry(
                skill_id=str(row["Skill_ID"]),
                skill_name=str(row.get("Skill_Name", "")),
                skill_name_zh=str(row.get("Skill_Name_ZH", "")),
                skill_type=str(row.get("Skill_Type", "Hard Skill")),
                skill_cat9=str(row.get("Skill_Category", "Unclassified")),
                category_code=str(row.get("Category_Code", "0")),
                category_name=str(row.get("Category_Name", "")),
                subcategory_code=str(row.get("Subcategory_Code", "0")),
                subcategory_name=str(row.get("Subcategory_Name", "")),
                is_software=(cat_code in self.software_categories),
            )
            skill_dict = skill_entry.model_dump()
            # 轉換 key 名稱為大寫以相容舊版 pipeline 慣例
            compat_skill_dict = {
                "SKILL_ID": skill_entry.skill_id,
                "SKILL_NAME": skill_entry.skill_name,
                "SKILL_NAME_ZH": skill_entry.skill_name_zh,
                "SKILL_TYPE": skill_entry.skill_type,
                "SKILL_CAT9": skill_entry.skill_cat9,
                "SKILL_CATEGORY": skill_entry.category_code,
                "SKILL_CATEGORY_NAME": skill_entry.category_name,
                "SKILL_SUBCATEGORY": skill_entry.subcategory_code,
                "SKILL_SUBCATEGORY_NAME": skill_entry.subcategory_name,
                "IS_SOFTWARE": skill_entry.is_software,
            }
            skill_id_index[skill_entry.skill_id] = compat_skill_dict

            terms: List[Tuple[str, bool]] = []
            zh = str(row.get("Skill_Name_ZH", "")).strip()
            if has_chinese(zh) and (len(zh) >= 3 or zh in self.zh_allowlist):
                terms.append((zh, True))
                jieba.add_word(zh, freq=1000)
                jcount += 1
            elif not has_chinese(zh):
                if len(zh) >= 2:
                    terms.append((zh.lower(), False))
                en = str(row.get("Skill_Name", "")).strip().lower()
                if len(en) >= 2:
                    terms.append((en, False))

            kw_str = str(row.get("Keywords", "")).strip()
            if kw_str and kw_str.lower() != "nan":
                for kw in kw_str.split("｜"):
                    kw = kw.strip()
                    if has_chinese(kw):
                        if len(kw) < 2 or (len(kw) == 2 and kw not in self.zh_allowlist):
                            continue
                        terms.append((kw, True))
                        jieba.add_word(kw, freq=1000)
                        jcount += 1
                    else:
                        if len(kw) >= 2:
                            terms.append((kw.lower(), False))

            # 同義詞擴充
            extra_syn: List[Tuple[str, bool]] = []
            for term, is_zh in terms:
                if not is_zh:
                    continue
                for variant in expand_synonyms(term, self.synonym_groups):
                    if len(variant) >= 3 or variant in self.zh_allowlist:
                        extra_syn.append((variant, True))
                        jieba.add_word(variant, freq=1000)
                        jcount += 1
            terms.extend(extra_syn)

            # 英文詞幹化擴充 (長度門檻 >= 7)
            extra_stem: List[Tuple[str, bool]] = []
            for term, is_zh in terms:
                if not is_zh:
                    stemmed = get_stemmed_term(term, min_len=7)
                    if stemmed != term:
                        extra_stem.append((stemmed, False))
            terms.extend(extra_stem)

            # 登錄至 term_to_entries
            seen: Set[str] = set()
            for term, is_zh in terms:
                if term in seen:
                    continue
                seen.add(term)
                entry = (len(term), compat_skill_dict, is_zh)
                if term not in term_to_entries:
                    term_to_entries[term] = []
                if not any(e[1]["SKILL_ID"] == skill_entry.skill_id for e in term_to_entries[term]):
                    term_to_entries[term].append(entry)

        logger.info(f"詞庫建立完成：共 {len(term_to_entries):,} 個詞條，註冊 Jieba 詞 {jcount:,} 個")
        return term_to_entries, skill_id_index
