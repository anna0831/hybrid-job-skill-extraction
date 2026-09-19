"""Aho-Corasick 比對引擎：封裝 Trie 自動機、雙掃描機制與消歧邏輯。"""

import re
import logging
from typing import List, Dict, Set, Any, Optional
import ahocorasick
import yaml

from src.preprocessing.boundary import (
    get_zh_boundaries,
    is_word_boundary,
)
from src.preprocessing.enumerator import expand_enumeration
from src.lexicon.expander import stem_english_text
from src.lexicon.schema import CandidateSkill
from src.ac_matcher.suppression import suppress_shorter_matches

logger = logging.getLogger(__name__)


class ACMatcher:
    """Aho-Corasick 技能匹配引擎。"""

    def __init__(
        self,
        automaton: ahocorasick.Automaton,
        skill_index: Dict[str, Dict[str, Any]],
        rules_path: str = "configs/rules.yaml",
    ):
        self.automaton = automaton
        self.skill_index = skill_index

        with open(rules_path, "r", encoding="utf-8") as f:
            self.rules = yaml.safe_load(f)

        self.enum_suffixes: List[str] = self.rules.get("enum_suffixes", [])
        self.local_context_rules: Dict[str, List[Dict[str, str]]] = self.rules.get(
            "local_context_rules", {}
        )
        self.title_disambiguation: Dict[str, List[Dict[str, Any]]] = self.rules.get(
            "title_disambiguation", {}
        )

    @classmethod
    def build_from_lexicon(
        cls,
        term_to_entries: Dict[str, List[Any]],
        skill_index: Dict[str, Dict[str, Any]],
        rules_path: str = "configs/rules.yaml",
    ) -> "ACMatcher":
        """根據 term_to_entries 建立 ahocorasick.Automaton 並實例化 ACMatcher。"""
        A = ahocorasick.Automaton()
        for term, entries in term_to_entries.items():
            A.add_word(term, entries)
        A.make_automaton()
        return cls(automaton=A, skill_index=skill_index, rules_path=rules_path)

    def match_texts(
        self,
        texts: List[str],
        field_labels: Optional[List[str]] = None,
        enable_rules: bool = True,
    ) -> List[CandidateSkill]:
        """對給定的多個欄位文字進行多模式匹配。
        
        預設欄位順序：["職位描述", "工作技能", "工具欄"]
        """
        if field_labels is None:
            field_labels = ["職位描述", "工作技能", "工具欄"]

        seen_ids: Set[str] = set()
        seen_zh_terms: Set[str] = set()
        candidates: List[CandidateSkill] = []

        for label, raw_text in zip(field_labels, texts):
            if not isinstance(raw_text, str) or not raw_text.strip():
                continue

            if enable_rules:
                raw_text = expand_enumeration(raw_text, self.enum_suffixes)
            text_lower = raw_text.lower()
            text_stemmed = stem_english_text(text_lower) if enable_rules else text_lower
            scan_texts = (
                [text_lower] if text_lower == text_stemmed else [text_lower, text_stemmed]
            )
            zh_boundaries = get_zh_boundaries(text_lower)
            suppressed_texts: Set[str] = set()

            for scan_text in scan_texts:
                step_cands = []
                for end_idx, entries in self.automaton.iter(scan_text):
                    for term_len, skill, is_zh in entries:
                        start_idx = end_idx - term_len + 1
                        if is_zh:
                            if scan_text is text_lower:
                                if (
                                    start_idx not in zh_boundaries
                                    or (end_idx + 1) not in zh_boundaries
                                ):
                                    continue
                        else:
                            if not is_word_boundary(scan_text, start_idx, end_idx + 1):
                                continue

                        step_cands.append(
                            {
                                "start": start_idx,
                                "end": end_idx,
                                "term_len": term_len,
                                "skill": skill,
                                "is_zh": is_zh,
                            }
                        )

                if enable_rules:
                    kept, newly_suppressed = suppress_shorter_matches(step_cands, scan_text)
                    suppressed_texts |= newly_suppressed
                else:
                    kept = step_cands

                for cand in kept:
                    matched_term = scan_text[cand["start"] : cand["end"] + 1]
                    if enable_rules and matched_term in suppressed_texts:
                        continue
                    if cand["is_zh"]:
                        if matched_term in seen_zh_terms:
                            continue
                        seen_zh_terms.add(matched_term)

                    skill_dict = cand["skill"]
                    skill_id = skill_dict["SKILL_ID"]
                    if skill_id in seen_ids:
                        continue
                    seen_ids.add(skill_id)

                    candidates.append(
                        CandidateSkill(
                            skill_id=skill_id,
                            skill_name=skill_dict["SKILL_NAME"],
                            skill_name_zh=skill_dict["SKILL_NAME_ZH"],
                            skill_type=skill_dict.get("SKILL_TYPE", "Hard Skill"),
                            skill_cat9=skill_dict.get("SKILL_CAT9", "Unclassified"),
                            category_code=skill_dict.get("SKILL_CATEGORY", "0"),
                            category_name=skill_dict.get("SKILL_CATEGORY_NAME", ""),
                            subcategory_code=skill_dict.get("SKILL_SUBCATEGORY", "0"),
                            subcategory_name=skill_dict.get("SKILL_SUBCATEGORY_NAME", ""),
                            is_software=skill_dict.get("IS_SOFTWARE", False),
                            matched_keyword=matched_term,
                            field_source=label,
                            start_pos=cand["start"],
                            end_pos=cand["end"],
                            original_text=raw_text,
                        )
                    )

        return candidates

    def resolve_ambiguous_by_title(
        self, texts: List[str], job_title: str
    ) -> List[CandidateSkill]:
        """當整篇職缺完全抓不到技能時的消歧 fallback 邏輯。
        
        第一層：就近文意規則 (Local context regex)
        第二層：職稱關鍵字消歧 (Title disambiguation)
        """
        combined = "".join(t for t in texts if isinstance(t, str))
        title = job_title if isinstance(job_title, str) else ""
        resolved: List[CandidateSkill] = []
        seen_ids: Set[str] = set()
        resolved_words: Set[str] = set()

        # 第一層：就近文意
        for word, rules in self.local_context_rules.items():
            if word not in combined:
                continue
            for rule in rules:
                pattern = rule["pattern"]
                skill_id = rule["skill_id"]
                if skill_id not in self.skill_index or not re.search(pattern, combined):
                    continue
                if skill_id not in seen_ids:
                    seen_ids.add(skill_id)
                    skill_dict = self.skill_index[skill_id]
                    resolved.append(
                        CandidateSkill(
                            skill_id=skill_id,
                            skill_name=skill_dict["SKILL_NAME"],
                            skill_name_zh=skill_dict["SKILL_NAME_ZH"],
                            skill_type=skill_dict.get("SKILL_TYPE", "Hard Skill"),
                            skill_cat9=skill_dict.get("SKILL_CAT9", "Unclassified"),
                            category_code=skill_dict.get("SKILL_CATEGORY", "0"),
                            category_name=skill_dict.get("SKILL_CATEGORY_NAME", ""),
                            subcategory_code=skill_dict.get("SKILL_SUBCATEGORY", "0"),
                            subcategory_name=skill_dict.get("SKILL_SUBCATEGORY_NAME", ""),
                            is_software=skill_dict.get("IS_SOFTWARE", False),
                            matched_keyword=word,
                            field_source="就近文意",
                        )
                    )
                resolved_words.add(word)

        # 第二層：職稱消歧
        for word, rules in self.title_disambiguation.items():
            if word not in combined or word in resolved_words:
                continue
            for rule in rules:
                title_keywords = rule["title_keywords"]
                skill_id = rule["skill_id"]
                if not skill_id or skill_id not in self.skill_index:
                    continue
                if any(kw in title for kw in title_keywords):
                    if skill_id in seen_ids:
                        continue
                    seen_ids.add(skill_id)
                    skill_dict = self.skill_index[skill_id]
                    resolved.append(
                        CandidateSkill(
                            skill_id=skill_id,
                            skill_name=skill_dict["SKILL_NAME"],
                            skill_name_zh=skill_dict["SKILL_NAME_ZH"],
                            skill_type=skill_dict.get("SKILL_TYPE", "Hard Skill"),
                            skill_cat9=skill_dict.get("SKILL_CAT9", "Unclassified"),
                            category_code=skill_dict.get("SKILL_CATEGORY", "0"),
                            category_name=skill_dict.get("SKILL_CATEGORY_NAME", ""),
                            subcategory_code=skill_dict.get("SKILL_SUBCATEGORY", "0"),
                            subcategory_name=skill_dict.get("SKILL_SUBCATEGORY_NAME", ""),
                            is_software=skill_dict.get("IS_SOFTWARE", False),
                            matched_keyword=word,
                            field_source="職稱消歧",
                        )
                    )
                    break

        return resolved

    def extract_job_skills(
        self, texts: List[str], job_title: str = "", enable_rules: bool = True
    ) -> List[CandidateSkill]:
        """對單一職缺執行完整候選技能擷取 (含 Fallback)。"""
        matched = self.match_texts(texts, enable_rules=enable_rules)
        if not matched and enable_rules:
            matched = self.resolve_ambiguous_by_title(texts, job_title)
        return matched
