"""
Vercel 教授展示版專用 Adapter（抽離自 104_single_city_merged_20261111.py）。

嚴格限制：
- 僅使用 Aho-Corasick + 11/11 Rule-based Matching。
- 完全停用 LLM、MockLLM、Embedding 與任何付費 AI API。
- 不依賴 pandas / numpy / pyarrow / nltk / streamlit，也不執行 input() 或檔案系統寫入。
- 啟動時從唯讀 JSON(.gz) 詞庫載入並快取 AC 自動機（Singleton）。
"""

from __future__ import annotations

import gzip
import io
import json
import os
import re
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Set, Tuple
from zoneinfo import ZoneInfo

import ahocorasick
import jieba
import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# Vercel /var/task 為唯讀，確保 jieba 快取寫入 /tmp
try:
    if os.path.isdir("/tmp") and os.access("/tmp", os.W_OK):
        jieba.dt.tmp_dir = "/tmp"
except Exception:
    pass
jieba.setLogLevel(60)

CODE_VERSION = "20261111_web_ac_v1"
RULE_VERSION = "20261111_evidence_merged_v1"
MAX_BATCH_JOBS = 100
MAX_FIELD_CHARS = 30000
GROUP10_SKILL_SEPARATOR = "｜"

EXPECTED_GROUP10: Dict[int, str] = {
    1: "認知、分析與創新技能",
    2: "溝通、語言與人際技能",
    3: "個人特質、自我管理與身體能力",
    4: "財務、會計與經濟技能",
    5: "管理、商業、法遵與治理技能",
    6: "行政與一般數位技能",
    7: "營運、技職與第一線服務技能",
    8: "資訊科技、軟體、資料與AI技能",
    9: "醫療、健康與照護技能",
    10: "工程、自然科學、設計、環境與能源技能",
}

SOFTWARE_CATEGORIES = {17, 370, 369, 371, 372, 373, 374, 375, 376, 377, 378, 379, 380}

_STRUCTURED_FIELD_LABELS = ("工作技能", "工具欄")
_STRUCTURED_TAG_PATTERN = re.compile(r"[^、,，]+")

_ZH_CROSS_WORD_GUARD = {
    "媒體", "軟體", "整理", "處理", "辦理", "準備", "具備", "個人", "恢復",
    "依照", "情感", "每年", "力量", "思維", "假日", "團體", "客人", "表現",
    "採光",
}

_JIEBA_2CHAR_WHITELIST = {
    "製程", "量試", "試作", "送樣", "首件", "稼働", "治具",
    "備料", "備件", "標案", "採購", "詢價", "驗收",
    "輪班", "物性", "化性", "採樣",
}

_SYNONYM_GROUPS = [
    {"老師", "教師"},
    {"飲料", "飲品"},
    {"會客登記", "登記換證", "訪客登記"},
    {"駕駛接送", "接送任務"},
    {"車輛加油", "加油作業", "油箱加油"},
    {"打掃", "清潔"},
    {"藥品調劑", "調劑處方", "藥事調劑"},
]

_PLURAL_PROTECTED = {
    "windows", "news", "series", "species", "sales", "goods", "means", "arms",
    "securities",
    "analytics", "statistics", "logistics", "economics", "physics", "mathematics",
    "electronics", "mechanics", "graphics", "robotics", "ethics", "optics",
    "genetics", "diagnostics", "ergonomics", "dynamics", "kinetics", "acoustics",
}

_PLURAL_EXCEPTIONS = {
    "caches": "cache", "niches": "niche", "headaches": "headache",
    "movies": "movie", "cookies": "cookie", "calories": "calorie",
    "analyses": "analysis", "diagnoses": "diagnosis", "hypotheses": "hypothesis",
    "crises": "crisis", "theses": "thesis",
}

_ENUM_SUFFIXES = [
    "服務", "作業", "管理", "處理", "工作", "技巧", "能力",
    "維護", "操作", "製作", "訓練", "分析", "規劃", "執行", "經驗",
]
_ENUM_SUFFIX_PATTERN = "|".join(_ENUM_SUFFIXES)
_ENUM_SEP = r"、|\."
_ENUM_PATTERN = re.compile(
    rf"([^、，,。.\s\d]{{1,2}}(?:(?:{_ENUM_SEP})[^、，,。.\s\d]{{1,2}}){{2,4}})({_ENUM_SUFFIX_PATTERN})"
)
_BARE_CHAR_ENUM_PATTERN = re.compile(r"([^、，,。.\s\d])(?:、[^、，,。.\s\d]){2,}")

_COORD_TAIL_LIST = [
    "評估", "介入", "規劃", "執行", "管理", "分析", "維護",
    "操作", "設計", "測試", "追蹤", "統計", "調配", "開發", "企劃", "教學",
]
_COORD_TAIL_SET = set(_COORD_TAIL_LIST)
_COORD_CONJ = {"與", "及", "和", "暨"}


# =============================================================================
# 文字前處理與詞界檢查
# =============================================================================

def has_chinese(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def expand_synonyms(term: str) -> Set[str]:
    results = {term}
    for group in _SYNONYM_GROUPS:
        for word in group:
            if word in term:
                for alt in group:
                    results.add(term.replace(word, alt))
    return results


def _normalize_fullwidth_alnum(text: str) -> str:
    return "".join(
        chr(ord(c) - 0xFEE0) if (0xFF10 <= ord(c) <= 0xFF19 or 0xFF21 <= ord(c) <= 0xFF3A or 0xFF41 <= ord(c) <= 0xFF5A)
        else (" " if c == "\u3000" else c)
        for c in text
    )


def _normalize_ascii_hyphen(text: str) -> str:
    return re.sub(r"(?<=[A-Za-z0-9])-(?=[A-Za-z0-9])", " ", text)


def _is_lowercased_word_in_english(text_case: str, start: int, end: int) -> bool:
    if start < 0 or end >= len(text_case):
        return False
    orig = text_case[start:end + 1]
    if orig.isupper():
        return False
    prev_ch = text_case[start - 1] if start > 0 else " "
    next_ch = text_case[end + 1] if end + 1 < len(text_case) else " "
    if prev_ch.isascii() and prev_ch.isalpha():
        return True
    if next_ch.isascii() and next_ch.isalpha():
        return True
    if re.search(r"[A-Za-z]\s+$", text_case[max(0, start - 20):start]):
        return True
    if re.search(r"^\s+[A-Za-z]", text_case[end + 1:end + 21]):
        return True
    return False


def _singularize_word(word: str, case_word: Optional[str] = None) -> str:
    if len(word) <= 3 or word in _PLURAL_PROTECTED:
        return word
    if word in _PLURAL_EXCEPTIONS:
        return _PLURAL_EXCEPTIONS[word]
    if case_word:
        if case_word.endswith("s") and len(case_word) >= 3 and case_word[:-1].isupper():
            return word[:-1]
        if case_word.isupper():
            return word
        if re.search(r"[a-z][A-Z]", case_word):
            return word
    if word.endswith(("ss", "us", "is")):
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith("sses"):
        return word[:-2]
    if word.endswith(("xes", "ches", "shes")):
        return word[:-2]
    if word.endswith("s"):
        return word[:-1]
    return word


def _stem_english_text_with_map(text: str, case_text: Optional[str] = None) -> Tuple[str, List[int], List[int]]:
    if not text:
        return text, [], []
    out: List[str] = []
    start_map: List[int] = []
    end_map: List[int] = []
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        if "a" <= ch <= "z":
            j = i
            while j < n and "a" <= text[j] <= "z":
                j += 1
            word = text[i:j]
            cword = case_text[i:j] if case_text is not None and len(case_text) == n else None
            stem = _singularize_word(word, cword)
            if stem == word:
                for k in range(i, j):
                    out.append(text[k])
                    start_map.append(k)
                    end_map.append(k)
            else:
                for pos, sch in enumerate(stem):
                    out.append(sch)
                    start_map.append(i + pos if pos < len(stem) - 1 else i + pos)
                    end_map.append(j - 1 if pos == len(stem) - 1 else i + pos)
            i = j
        else:
            out.append(ch)
            start_map.append(i)
            end_map.append(i)
            i += 1
    return "".join(out), start_map, end_map


def expand_coord(text: str) -> List[str]:
    if not isinstance(text, str) or not any(c in text for c in _COORD_CONJ):
        return []
    tokens = list(jieba.cut(text))
    expansions: List[str] = []
    for i, tok in enumerate(tokens):
        if tok in _COORD_TAIL_SET and i >= 2 and tokens[i - 1] in _COORD_CONJ:
            tail1_idx = i - 2
            if tokens[tail1_idx] in _COORD_TAIL_SET and tail1_idx >= 1:
                prefix = tokens[tail1_idx - 1]
                if len(prefix) >= 2:
                    expansions.append(prefix + tok)
    return expansions


def expand_enumeration(text: str) -> str:
    if not isinstance(text, str):
        return ""
    if "、" not in text and "." not in text and not any(c in text for c in _COORD_CONJ):
        return text
    expansions: List[str] = []
    for m in _ENUM_PATTERN.finditer(text):
        heads = re.split(_ENUM_SEP, m.group(1))
        suffix = m.group(2)
        for h in heads:
            if h and not h.endswith(suffix):
                expansions.append(h + suffix)

    for m in re.finditer(rf"((?:[剪染燙護洗造](?:{_ENUM_SEP})){{1,4}}[剪染燙護洗造])(?:服務|作業)?", text):
        for ch in re.split(_ENUM_SEP, m.group(1)):
            expansions.append(ch + "髮")

    if "、" in text:
        for m in _BARE_CHAR_ENUM_PATTERN.finditer(text):
            chars = m.group(0).split("、")
            expansions.append("".join(chars))

    expansions.extend(expand_coord(text))
    if expansions:
        return text + " " + " ".join(expansions)
    return text


def _get_zh_boundaries(text: str) -> Set[int]:
    positions = {0}
    pos = 0
    for token in jieba.cut(text):
        pos += len(token)
        positions.add(pos)
    return positions


def _is_ascii_alnum(c: str) -> bool:
    return c.isascii() and (c.isalnum() or c == "_")


def _is_glued_list_number(text: str, end: int) -> bool:
    if end >= len(text):
        return False
    ch = text[end]
    if not ch.isdigit():
        return False
    i = end
    while i < len(text) and text[i].isdigit():
        i += 1
    return i < len(text) and text[i] in ".．、)"


def _is_word_boundary(text: str, start: int, end: int) -> bool:
    if start > 0 and _is_ascii_alnum(text[start - 1]):
        return False
    if end < len(text) and _is_ascii_alnum(text[end]):
        if not _is_glued_list_number(text, end):
            return False
    return True


# =============================================================================
# 段落切割與證據過濾規則（11/11 版）
# =============================================================================

_RE_SECTION_HEADERS: List[Tuple[str, re.Pattern]] = [
    ("COMPANY_INTRO", re.compile(
        r"(?:【[^】]*(?:公司|品牌|集團|企業|關於)[^】]*】|"
        r"\[[^\]]*(?:公司|品牌|集團|企業|關於)[^\]]*\]|"
        r"◎[^◎]{0,12}(?:公司|品牌|集團|企業|關於)[^◎]{0,12}◎|"
        r"(?:公司簡介|關於我們|品牌介紹|企業簡介|集團簡介)[：:])"
    )),
    ("WELFARE", re.compile(
        r"(?:【[^】]*(?:福利|待遇|休假|津貼|獎金|補助|活動|環境)[^】]*】|"
        r"\[[^\]]*(?:福利|待遇|休假|獎金)[^\]]*\]|"
        r"◎[^◎]{0,12}(?:福利|待遇|休假|津貼|獎金|補助)[^◎]{0,12}◎|"
        r"(?:福利制度|員工福利|公司福利|休假制度)[：:])"
    )),
    ("REQUIREMENTS", re.compile(
        r"(?:【[^】]*(?:條件|資格|要求|特質|夥伴|特徵|技能|工具|經歷|學歷|加分|必備|徵求)[^】]*】|"
        r"\[[^\]]*(?:條件|資格|要求|特質|技能|工具)[^\]]*\]|"
        r"◎[^◎]{0,12}(?:條件|資格|要求|特質|技能|經歷|學歷|加分|必備)[^◎]{0,12}◎|"
        r"(?:任職條件|具備條件|任職資格|加分條件|必要條件|應徵條件)[：:])"
    )),
    ("JOB_DUTIES", re.compile(
        r"(?:【[^】]*(?:工作內容|職務說明|職務內容|工作職責|主要職責|實戰|工作項目|任務|執掌|服務內容|工作執掌|工作時間|未來店長培訓|培訓服務內容)[^】]*】|"
        r"\[[^\]]*(?:工作內容|職務說明|工作職責|主要職責|工作項目)[^\]]*\]|"
        r"◎[^◎]{0,12}(?:工作內容|職務說明|工作職責|主要職責|工作項目|職務內容)[^◎]{0,12}◎|"
        r"(?:工作內容|主要職責|職務說明|職務內容|職責內容|工作項目|工作執掌)[：:])"
    )),
]

_DECORATED_TITLES = [
    ("COMPANY_INTRO", r"公司簡介|關於我們|公司介紹"),
    ("WELFARE", r"福利制度|員工福利|公司福利|薪資福利|薪資待遇"),
    ("REQUIREMENTS", r"任職條件|應徵條件|條件要求|任職資格|職務需求"),
    ("JOB_DUTIES", r"工作內容|職務內容|工作職責|職務說明|主要職責"),
]
for _sec_type, _titles in _DECORATED_TITLES:
    _RE_SECTION_HEADERS.append((_sec_type, re.compile(
        rf"[-－—=＝~～*＊#]{{2,}}\s*(?:{_titles})\s*[-－—=＝~～*＊#]{{2,}}"
    )))

_EN_SECTION_TITLES = [
    ("COMPANY_INTRO",
     r"(?:more\s+)?about\s+(?:us|the\s+company|our\s+company|"
     r"(?!(?:the|this|you|yourself|position|role|job|opportunity)\b)(?![^】\]:：]{0,40}\bteam\b)"
     r"(?-i:[A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,3}))|who\s+we\s+are|"
     r"(?:company|client)\s+(?:overview|introduction|profile|description)|our\s+(?:company|story|mission)"),
    ("WELFARE",
     r"(?:employee\s+|our\s+|company\s+)?benefits?(?:\s*(?:&|and)\s*perks)?|perks|"
     r"what\s+we\s+offer|we\s+offer|why\s+(?:join\s+us|us|work\s+with\s+us)"),
    ("REQUIREMENTS",
     r"(?:job\s+|basic\s+|minimum\s+|preferred\s+|core\s+|key\s+)?(?:requirements?|qualifications?)|"
     r"what\s+we(?:'|’)?re\s+looking\s+for|what\s+we\s+are\s+looking\s+for|"
     r"what\s+you(?:'|’)?ll\s+(?:bring|need)|who\s+you\s+are|about\s+you|nice\s+to\s+haves?|must\s+haves?|"
     r"bonus\s+points|candidate\s+(?:profile|requirements?)|(?:the\s+)?ideal\s+candidate|"
     r"(?:required\s+|preferred\s+|desir(?:ed|able)\s+)?skills?(?:\s*(?:&|and)\s*experiences?)?|"
     r"(?:work\s+|relevant\s+)?experiences?"),
    ("JOB_DUTIES",
     r"(?:key\s+|job\s+|main\s+|primary\s+|roles?\s*(?:&|and|/)?\s*)?(?:responsibilities|duties|accountabilities)|"
     r"what\s+(?:this|the)\s+(?:job|role|position)\s+involves|"
     r"(?:job|role|position)\s+(?:description|summary|overview)|objectives?\s+of\s+(?:this|the)\s+role|"
     r"what\s+you(?:'|’)?ll\s+do|what\s+you\s+will\s+do|about\s+(?:(?:the|this)\s+)?(?:role|job|position|opportunity)|"
     r"(?:your|the)\s+role"),
    ("GENERAL", r"overview|summary"),
]
for _sec_type, _titles in _EN_SECTION_TITLES:
    _RE_SECTION_HEADERS.append((_sec_type, re.compile(
        rf"(?:【\s*(?:{_titles})\s*】|\[\s*(?:{_titles})\s*\]|"
        rf"(?:^|(?<=[\n\r。．.!！?？;；:：■●★◆▶►•*#|\-—–)）\u4e00-\u9fff])|(?-i:(?<=[a-z0-9])(?=[A-Z])))"
        rf"[ \t]*(?:{_titles})(?:(?:\s*/\s*[A-Za-z][A-Za-z ]{{0,25}})?\s*[：:]|(?=\s*1[.．、)]\s*\S)|(?=\s*(?:[•●■◆▶►➤・]|[*\-]\s))|(?-i:(?<=[a-z])(?=[A-Z][a-z]))))",
        re.IGNORECASE | re.MULTILINE,
    )))

_RE_WELFARE_LIST_HEAD = re.compile(r"獎金|獎勵|勞健保|勞保|健保|勞退|尾牙|年終|津貼|補助|特休|休假|旅遊|聚餐|禮金|分紅|員工餐|宿舍")
_RE_ANY_BRACKET_HEADER = re.compile(r"【[^】]{1,25}】|\[[^\]\n]{1,25}\]")
_RE_LEADING_TAG_RUN = re.compile(r"\s*(?:【[^】]{1,20}】\s*){2,}")
_RE_BARE_LIST_ITEM_1 = re.compile(r"(?<!\d)1[.\．、](?!\d)(?=\s{0,2}[\u4e00-\u9fffA-Za-z])")
_INTRO_PHRASE_RE = re.compile(
    r"(?:集團旗下|本公司|我們是|成立於|致力於|創立於|旗下品牌|為全台|是全台|第一品牌|專業品牌|是一間|深耕|隸屬於[^。，,；;]{0,15}事業(?:群|部))"
)


def _find_bare_duty_list_start(text: str) -> Optional[int]:
    for m in _RE_BARE_LIST_ITEM_1.finditer(text):
        pos = m.start()
        if pos > 0 and text[pos - 1] in "（(「『\"'":
            continue
        if re.search(r"2[.\．、]\s{0,2}[\u4e00-\u9fffA-Za-z]", text[pos:pos + 200]):
            return pos
    return None


def parse_text_sections(text: str) -> List[Dict[str, Any]]:
    if not isinstance(text, str) or not text.strip():
        return [{"type": "GENERAL", "start": 0, "end": 0, "header": ""}]

    leading_run_end = 0
    m_run = _RE_LEADING_TAG_RUN.match(text)
    if m_run:
        leading_run_end = m_run.end()

    headers: List[Tuple[int, int, str, str]] = []
    for sec_type, pattern in _RE_SECTION_HEADERS:
        for m in pattern.finditer(text):
            if m.start() < leading_run_end and sec_type in ("COMPANY_INTRO", "WELFARE"):
                continue
            headers.append((m.start(), m.end(), sec_type, m.group(0)))

    headers.sort(key=lambda x: x[0])

    filtered_headers: List[Tuple[int, int, str, str]] = []
    for h in headers:
        if not filtered_headers or h[0] >= filtered_headers[-1][1]:
            filtered_headers.append(h)

    if not filtered_headers:
        bare_list_start = _find_bare_duty_list_start(text)
        if bare_list_start is not None:
            out: List[Dict[str, Any]] = []
            if bare_list_start > 0:
                intro_part = text[:bare_list_start].strip()
                sec_type = "COMPANY_INTRO" if _INTRO_PHRASE_RE.search(intro_part) else "GENERAL"
                out.append({"type": sec_type, "start": 0, "end": bare_list_start, "header": "[開頭前言]"})
            out.append({"type": "JOB_DUTIES", "start": bare_list_start, "end": len(text), "header": "[裸編號清單]"})
            return out
        sec_type = "COMPANY_INTRO" if _INTRO_PHRASE_RE.search(text.strip()) else "GENERAL"
        return [{"type": sec_type, "start": 0, "end": len(text), "header": "[開頭前言]"}]

    expanded_headers: List[Tuple[int, int, str, str]] = []
    for idx, (h_start, h_end, h_type, h_str) in enumerate(filtered_headers):
        expanded_headers.append((h_start, h_end, h_type, h_str))
        if h_type == "COMPANY_INTRO":
            next_start = filtered_headers[idx + 1][0] if idx + 1 < len(filtered_headers) else len(text)
            seg = text[h_end:next_start]
            m_other = _RE_ANY_BRACKET_HEADER.search(seg)
            if m_other:
                abs_pos = h_end + m_other.start()
                expanded_headers.append((abs_pos, h_end + m_other.end(), "GENERAL", m_other.group(0)))

    expanded_headers.sort(key=lambda x: x[0])

    sections: List[Dict[str, Any]] = []
    first_start = expanded_headers[0][0]
    if first_start > 0:
        leading_text = text[:first_start].strip()
        sec_type = "COMPANY_INTRO" if _INTRO_PHRASE_RE.search(leading_text) else "GENERAL"
        sections.append({"type": sec_type, "start": 0, "end": first_start, "header": "[開頭前言]"})

    for i, (h_start, h_end, h_type, h_str) in enumerate(expanded_headers):
        next_start = expanded_headers[i + 1][0] if i + 1 < len(expanded_headers) else len(text)
        sections.append({
            "type": h_type,
            "start": h_start,
            "end": next_start,
            "header": h_str,
            "header_end": h_end,
        })

    # 公司介紹段落（含開頭前言）裡接著「1. … 2. …」編號清單時，清單起點之後當工作內容（福利清單除外）
    # 福利段落不套用（福利常寫成「1.年終獎金 2.勞健保」），與 104_single_city_merged_20261111.py 一致
    split_sections: List[Dict[str, Any]] = []
    for sec in sections:
        if sec["type"] == "COMPANY_INTRO":
            body_start = sec.get("header_end", sec["start"])
            list_start = _find_bare_duty_list_start(text[body_start:sec["end"]])
            if list_start is not None:
                cut = body_start + list_start
                is_welfare = bool(_RE_WELFARE_LIST_HEAD.search(text[cut:cut + 40])) or (
                    "福利" in text[max(body_start, cut - 15):cut]
                )
                list_type = "WELFARE" if is_welfare else "JOB_DUTIES"
                split_sections.append(dict(sec, end=cut))
                split_sections.append({
                    "type": list_type,
                    "header": "[公司介紹後的編號清單]",
                    "start": cut,
                    "end": sec["end"],
                })
                continue
        split_sections.append(sec)

    return split_sections


def get_section_for_offset(sections: List[Dict[str, Any]], offset: int) -> Dict[str, Any]:
    for sec in sections:
        if sec["start"] <= offset < sec["end"]:
            return sec
    return sections[-1] if sections else {"type": "GENERAL", "start": 0, "end": 0, "header": ""}


def extract_context_snippet(raw_text: str, start: int, end: int, window: int = 50) -> str:
    if not raw_text:
        return ""
    s_idx = max(0, start - window)
    e_idx = min(len(raw_text), end + window + 1)
    return raw_text[s_idx:e_idx].replace("\n", " ").replace("\r", " ").strip()


def is_marketing_target_or_domain_modifier(snippet: str, matched_term: str) -> bool:
    if not snippet or not matched_term:
        return False
    term_esc = re.escape(matched_term)
    p1 = re.compile(
        rf"(?:為|替|針對|負責|推廣|行銷|宣傳|拍攝|剪輯|撰寫|製作|經營).{{0,8}}{term_esc}.{{0,8}}"
        r"(?:品牌|門市|分店|粉專|社群|文案|廣告|短影片|短影音|素材|影片|企劃|官網|自媒體)"
    )
    if p1.search(snippet):
        return True
    p2 = re.compile(
        rf"{term_esc}(?:相關|旗下|之)?(?:品牌|門市|分店|廠商|專案|產品|業務|產業|領域|客戶).{{0,10}}"
        r"(?:行銷|宣傳|推廣|文案|企劃|短影音|影片|設計|拍攝|剪輯|經營)"
    )
    if p2.search(snippet):
        return True
    p3 = re.compile(
        rf"為{term_esc}(?:品牌)?.{{0,6}}(?:製作|撰寫|企劃|拍攝|剪輯|宣傳|設計)(?:文案|影片|影音|素材|內容)?"
    )
    if p3.search(snippet):
        return True
    return False


_CONTEXT_EXCLUSION_RULES: Dict[str, List[str]] = {
    "KS1234J655K2L8W48Y6J": [r"採購單.{0,8}(?:對帳|核對|核銷|請款|結帳|歸檔|建檔)|(?:對帳|核對|核銷|請款).{0,8}採購單"],
    "KS4429T75Y20S1H409T2": [r"對帳單"],
    "KS4411S68TJXPT4G69P1": [r"營業所"],
    "ESAD033D8B6087100FC2": [r"專案負責人|專案進度|專案管理|專案執行|專案溝通|專案協調|專案開發|專案時程|專案報告|專案規劃|專案追蹤"],
    "KS126026W7HQ4KHY9D9X": [r"客戶(?:的)?需求|使用者需求|產品需求|業務需求|專案需求|系統需求|市場需求|功能需求|收集需求|需求訪談|需求分析|需求確認|需求評估|規格需求"],
    "KS440C86P8B0FGYH6D80": [r"人員調度|人員派遣|人力調度|人力資源|派工"],
    "KS1236W6Q4S5Z0P1053G": [r"作業員|產線人員|現場人員|技術員|品保人員|品管人員|作業人員|工作內容|作業流程|作業時間|作業標準|作業規範|標準作業|現場作業|清潔作業|包裝作業|加工作業|組裝作業|輪班作業|夜間作業|高空作業|吊掛作業"],
    "KS1263F6770C1F1Y1Q22": [r"工作環境|工作場所|環境整潔|環境衛生|環境清潔|環境維護|環境安全|環境單純|舒適環境|辦公環境|職場環境|環境保護|環境永續|友善環境|工作氛圍|氣氛環境"],
    "KS1205R67Y8B3L2T8L3V": [r"環境安全|安全衛生|安全第一|安全作業|安全規範|安全帽|安全鞋|安全帶|安全門|安全設施|行車安全|交通安全|食品安全|資訊安全|網路安全|居家安全|環境整潔|安全舒適"],
    "KS4419M6X7Y8323L4L11": [r"服務人員|門市人員|客服人員|服務業|服務態度|服務熱忱|顧客服務|客戶服務|優質服務|專業服務|售後服務|餐飲服務|飯店服務|外場服務|內場服務|為您服務|服務品質|服務精神"],
    "KS440266V0Q9W5S70G12": [r"主動積極|積極主動|認真負責|細心負責|團隊精神|團隊合作|學習能力|抗壓性|抗壓力|溝通能力|配合度高|工作熱忱|有責任感|責任心"],
    "BGSED41BF182E7A55A17": [
        r"(?<![a-z])rtl(?![a-z])", r"(?<![a-z])lint(?![a-z])", r"verilog", r"clock",
        r"(?<![a-z])sta(?![a-z])", r"(?<![a-z])dft(?![a-z])", r"synthesis", r"時脈", r"(?<![a-z])lec(?![a-z])",
    ],
    "KS1239Z71LLXDMTGRJ5S": [r"氣候", r"生態", r"永續", r"(?<![a-z])esg(?![a-z])"],
    "ES92A402F893456D877B": [
        r"福利", r"禮[金品券]", r"獎金", r"團(體)?保", r"勞健保", r"保險", r"津貼", r"補助",
        r"聚餐", r"尾牙", r"旅遊", r"制服", r"優惠", r"折扣", r"特約", r"寵物",
    ],
    "BGS423420828D2785973": [r"勞健保", r"獎金", r"福利", r"禮[品金券]", r"員工", r"年終", r"健康檢查", r"制服", r"休假", r"週休"],
    "ES93F8B89DCFEB3D8E20": [r"客戶", r"保險", r"人力"],
    "KS43I7T7CU4Q66EGVQLU": [r"指導書", r"供應商", r"協力廠", r"廠商"],
    "KS127MC6FMH3R4C3N5PZ": [
        r"pci[\s\-]?dss", r"支付", r"payment", r"信用卡", r"資安", r"資訊安全", r"資料安全", r"security", r"27001",
    ],
}

_W = r"(?<![a-z])"
_CLINICAL = [
    r"臨床", r"clinical", r"trial", r"試驗", _W + r"ich(?![a-z])", _W + r"glp(?![a-z])",
    _W + r"gmp(?![a-z])", _W + r"irb(?![a-z])", _W + r"cr[aco](?![a-z])",
    r"藥", r"pharma", r"受試", r"sponsor", r"醫",
]
_CLOUD = [
    r"雲", r"cloud", _W + r"aws(?![a-z])", r"azure", r"docker", r"kubernetes", _W + r"k8s",
    r"bigquery", r"devops", r"ci/cd", r"linux", r"deploy", r"部署", _W + r"gke(?![a-z])",
    r"vertex", r"terraform", r"容器", r"container", r"微服務", r"阿里", r"server", r"伺服器",
    _W + r"api(?![a-z])", _W + r"sql(?![a-z])", r"python", r"java", r"平台",
]
_NEAR = 60
_CLINICAL_NEAR = [
    r"臨床", r"clinical", r"trial", r"試驗", _W + r"ich(?![a-z])", _W + r"glp(?![a-z])",
    _W + r"gmp(?![a-z])", r"受試", r"sponsor",
]
_CLOUD_NEAR = [
    r"雲", r"cloud", _W + r"aws(?![a-z])", r"azure", r"docker", r"kubernetes", _W + r"k8s",
    r"bigquery", r"devops", r"部署", r"deploy", r"阿里",
    r"network", r"網路", r"data center", r"資料中心",
]
_ACRONYM_CONTEXT_REQUIRED = {
    "KS124ZQ6RS1V188JSCTX": ("GCP", 300, _CLINICAL, _CLOUD_NEAR),
    "ESC7869CF7378283E0AA": ("GCP", 300, _CLOUD, _CLINICAL_NEAR),
    "KS1220H6CP1BQGH9STNK": ("GCP", 300, _CLOUD, _CLINICAL_NEAR),
    "ES63C92B9AE0C7FC326A": ("GDP", 300, [
        r"藥", r"pharma", r"醫", r"運銷", r"distribution", _W + r"gmp(?![a-z])", _W + r"gsp(?![a-z])",
        r"冷鏈", r"cold chain", r"溫[溼濕]度", r"倉", r"物流", r"logistic", r"品質", r"quality",
        _W + r"iso(?![a-z])", r"healthcare", _W + r"cmo(?![a-z])", r"compliance", r"法規", r"稽核", r"疫苗",
        r"庫存", r"進貨", r"出貨", r"調撥",
    ], []),
    "ESA5839C44D0970CF79F": ("GO", 150, [
        r"python", r"java", r"c\+\+", r"(?<![a-z])c#", r"rust", r"golang", r"node", r"php", r"ruby",
        r"kotlin", r"swift", r"scala", r"typescript", r"程式", r"後端", r"backend", r"語言", r"language",
        r"programming", r"docker", r"kubernetes", r"microservice", r"微服務", r"grpc", r"(?<![a-z])api(?![a-z])",
        r"開發", r"develop", r"software", r"軟體",
    ], [
        r"go[\s\-]*green", r"go[\s\-]*getter", r"extra mile", r"go[\s\-]*live", r"go[\s\-]*to[\s\-]*market",
        r"let'?s go", r"go[\s\-]*go",
    ]),
    "KS127MD73WL7RSVDW53X": ("PCI", 300, [
        _W + r"dss(?![a-z])", r"支付", r"payment", r"信用卡", r"credit card", r"刷卡", r"金流", r"收單",
        r"資安", r"資訊安全", r"security", r"27001", r"compliance", r"法遵",
    ], []),
}

_TITLE_DISAMBIGUATION = {
    "開發": [
        (["軟體", "韌體", "程式", "資訊", "app", "APP", "IT"], "KS120L96KMYTDJ48NRSH"),
        (["業務", "銷售"], "KS1212B6QR5SK1LSD4S4"),
        (["產品經理", "產品企劃", "研發"], "KS1270P6SLFCFT476Y3R"),
    ],
    "設計": [
        (["機構"], "KS1269J6YQG4J3V5YGGW"),
        (["電子", "電機", "硬體", "ic", "IC", "韌體", "類比"], "KS121X369RKT17LSJNZX"),
        (["室內", "裝潢"], "KS122SP76CJCX9T70P6B"),
        (["美編", "平面", "視覺", "ui", "UI", "ux", "UX", "廣告"], "KS124H46Q2PP8YC1WQ06"),
    ],
    "操作": [
        (["作業員", "技術員", "機台", "生產", "製造", "產線"], "TW_MFG_001"),
    ],
    "管控": [
        (["品管", "品保", "QA", "QC", "稽核", "檢驗"], "KS1289C6QS0TSSB4PNGG"),
        (["生產", "製造", "產線", "製程"], "KS1282X64QGHTFWQ8J2Y"),
    ],
}

_LOCAL_CONTEXT_RULES = {
    "開發": [(r"產品[之的]?開發", "KS1270P6SLFCFT476Y3R")],
    "教授": [(r"教授.{0,6}英文", "KS4418W709S96G1PP7DS")],
}


def is_context_excluded(skill_id: str, snippet: str) -> bool:
    rules = _CONTEXT_EXCLUSION_RULES.get(skill_id)
    if not rules:
        return False
    return any(re.search(p, snippet, re.IGNORECASE) for p in rules)


def lacks_required_context(skill_id: str, matched_term: str, raw_text: str, start: int, end: int) -> bool:
    rule = _ACRONYM_CONTEXT_REQUIRED.get(skill_id)
    if not rule:
        return False
    acronym, window, patterns, near_deny = rule
    if matched_term.strip().upper() != acronym:
        return False
    near = raw_text[max(0, start - _NEAR): end + _NEAR + 1]
    if any(re.search(p, near, re.IGNORECASE) for p in near_deny):
        return True
    ctx = raw_text[max(0, start - window): end + window + 1]
    return not any(re.search(p, ctx, re.IGNORECASE) for p in patterns)


def _suppress_shorter_matches(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not candidates:
        return []
    candidates_sorted = sorted(candidates, key=lambda x: (x["start"], -x["term_len"]))
    kept: List[Dict[str, Any]] = []
    for cand in candidates_sorted:
        c_start, c_end = cand["start"], cand["end"]
        c_skill = cand["skill"].get("SKILL_ID") or cand["skill"].get("SKILL_NAME")
        covered = False
        for k in kept:
            if k["start"] <= c_start and k["end"] >= c_end:
                if k["term_len"] > cand["term_len"]:
                    covered = True
                    break
                if k["term_len"] == cand["term_len"] and (k["skill"].get("SKILL_ID") or k["skill"].get("SKILL_NAME")) == c_skill:
                    covered = True
                    break
        if not covered:
            kept.append(cand)
    return kept


# =============================================================================
# Web Engine 單例類別
# =============================================================================

class WebSkillEngine:
    """封裝 11/11 AC + Rules 擷取引擎，供 FastAPI 啟動時載入並跨請求快取。"""

    def __init__(self, bundle_path: Optional[str] = None):
        self.bundle_path = self._resolve_bundle_path(bundle_path)
        self.ready = False
        self.load_error: Optional[str] = None
        self.metadata: Dict[str, Any] = {}
        self.automaton = ahocorasick.Automaton()
        self.skill_index: Dict[str, Dict[str, Any]] = {}
        self.case_sensitive_terms: Dict[str, Set[str]] = {}
        self.structured_exact_tags: Dict[str, List[Dict[str, Any]]] = {}
        self.ai_skill_ids: Set[str] = set()

        if self.bundle_path and self.bundle_path.is_file():
            try:
                self._load_bundle(self.bundle_path)
                self.ready = True
            except Exception as exc:
                self.load_error = f"載入詞庫失敗：{exc}"
        else:
            self.load_error = (
                "尚未建置 11/11 Web 詞庫檔（web_data/lexicon_bundle.json.gz）。"
                "請在本機執行 python scripts/prepare_web_lexicon.py 從 11/11 正式 Excel 轉換。"
            )

    @staticmethod
    def _resolve_bundle_path(explicit: Optional[str]) -> Optional[Path]:
        if explicit:
            return Path(explicit)
        env_path = os.environ.get("LEXICON_BUNDLE_PATH", "").strip()
        if env_path:
            return Path(env_path)
        root = Path(__file__).resolve().parent.parent
        for rel in ("web_data/lexicon_bundle.json.gz", "web_data/lexicon_bundle.json"):
            cand = root / rel
            if cand.is_file():
                return cand
        return root / "web_data/lexicon_bundle.json.gz"

    def _load_bundle(self, path: Path) -> None:
        if path.suffix == ".gz":
            with gzip.open(path, "rt", encoding="utf-8") as f:
                bundle = json.load(f)
        else:
            with path.open("r", encoding="utf-8") as f:
                bundle = json.load(f)

        self.metadata = bundle.get("metadata", {})
        skills_list = bundle.get("skills", [])

        for w in _JIEBA_2CHAR_WHITELIST:
            jieba.add_word(w, freq=1000)
        for w in _COORD_TAIL_LIST:
            jieba.add_word(w, freq=2000)

        term_to_entries: Dict[str, List[Tuple[int, Dict[str, Any], bool]]] = {}

        for raw in skills_list:
            sid = str(raw.get("SKILL_ID") or "").strip()
            sname = str(raw.get("SKILL_NAME") or "").strip()
            sname_zh = str(raw.get("SKILL_NAME_ZH") or "").strip()
            cat_code = raw.get("Category_Code")
            is_sw = (cat_code in SOFTWARE_CATEGORIES) if isinstance(cat_code, int) else False

            g_code = raw.get("Skill_group10_code")
            g_name = str(raw.get("Skill_group10") or "").strip()
            if g_code in EXPECTED_GROUP10 and (not g_name or g_name == "待分類"):
                g_name = EXPECTED_GROUP10[g_code]
            if not g_name or g_code is None:
                g_name = g_name or "待分類"

            skill = {
                "Category_Name": str(raw.get("Category_Name") or "").strip(),
                "Subcategory_Name": str(raw.get("Subcategory_Name") or "").strip(),
                "SKILL_ID": sid,
                "SKILL_NAME": sname,
                "SKILL_NAME_ZH": sname_zh,
                "SKILL_TYPE": str(raw.get("SKILL_TYPE") or "").strip(),
                "Category_Code": cat_code,
                "Subcategory_Code": raw.get("Subcategory_Code"),
                "Skill_group10_code": g_code,
                "Skill_group10": g_name,
                "Grouping_rule": str(raw.get("Grouping_rule") or "").strip(),
                "Grouping_status": str(raw.get("Grouping_status") or "").strip() or ("已對應" if g_code is not None else "待分類"),
                "Allowed_group_codes": str(raw.get("Allowed_group_codes") or "").strip(),
                "Ambiguity_note": str(raw.get("Ambiguity_note") or "").strip(),
                "Is_AI_Skill": bool(raw.get("Is_AI_Skill", False)),
                "IS_SOFTWARE": is_sw,
            }

            if sid:
                self.skill_index[sid] = skill
                if skill["Is_AI_Skill"]:
                    self.ai_skill_ids.add(sid)

            allow_str = str(raw.get("Allow_Bare_2Char_Keywords") or "").strip()
            row_bare_allow = set(allow_str.split("｜")) if allow_str else set()

            exact_str = str(raw.get("Structured_Field_Exact_Tags") or "").strip()
            if exact_str:
                for tag in exact_str.split("｜"):
                    t = tag.strip().lower()
                    if t:
                        self.structured_exact_tags.setdefault(t, []).append(skill)

            case_str = str(raw.get("Case_Sensitive_Keywords") or "").strip()
            if case_str:
                owner = sid or sname
                for ck in case_str.split("｜"):
                    ck_norm = _normalize_ascii_hyphen(_normalize_fullwidth_alnum(ck.strip().lower()))
                    if ck_norm and owner:
                        self.case_sensitive_terms.setdefault(ck_norm, set()).add(owner)

            terms: List[Tuple[str, bool]] = []
            en_case: Dict[str, str] = {}

            if sname_zh and has_chinese(sname_zh) and (len(sname_zh) >= 3 or sname_zh in row_bare_allow):
                zh_lower = sname_zh.lower()
                terms.append((zh_lower, True))
                jieba.add_word(zh_lower, freq=1000)
            elif not has_chinese(sname_zh):
                en = sname.lower()
                if len(en) >= 2:
                    terms.append((en, False))
                    en_case[en] = sname

            kw_str = str(raw.get("Keywords") or "").strip()
            if kw_str:
                for kw in kw_str.split("｜"):
                    kw = kw.strip()
                    if not kw:
                        continue
                    if has_chinese(kw):
                        if len(kw) < 2 or (len(kw) == 2 and kw not in row_bare_allow):
                            continue
                        kw_lower = kw.lower()
                        terms.append((kw_lower, True))
                        jieba.add_word(kw_lower, freq=1000)
                    else:
                        if len(kw) < 2:
                            continue
                        kw_lower = kw.lower()
                        terms.append((kw_lower, False))
                        en_case.setdefault(kw_lower, kw)

            extra_syn: List[Tuple[str, bool]] = []
            for term, is_zh in terms:
                if not is_zh:
                    continue
                for variant in expand_synonyms(term):
                    if len(variant) >= 3 or variant in row_bare_allow:
                        extra_syn.append((variant, True))
                        jieba.add_word(variant, freq=1000)
            terms.extend(extra_syn)

            extra_stem: List[Tuple[str, bool]] = []
            for term, is_zh in terms:
                if not is_zh:
                    stemmed = _stem_english_text_with_map(term, en_case.get(term))[0]
                    if stemmed != term and len(stemmed) >= 4:
                        extra_stem.append((stemmed, False))
            terms.extend(extra_stem)

            seen_terms: Set[str] = set()
            dedup_identity = sid if sid else sname
            for term, is_zh in terms:
                term_norm = _normalize_ascii_hyphen(_normalize_fullwidth_alnum(term))
                if term_norm in seen_terms:
                    continue
                seen_terms.add(term_norm)
                bucket = term_to_entries.setdefault(term_norm, [])
                if not any((e[1]["SKILL_ID"] if e[1]["SKILL_ID"] else e[1]["SKILL_NAME"]) == dedup_identity for e in bucket):
                    bucket.append((len(term_norm), skill, is_zh))

        nospace_variants: Dict[str, List[Tuple[int, Dict[str, Any], bool]]] = {}
        for term, entries in term_to_entries.items():
            if " " not in term or has_chinese(term):
                continue
            variant = term.replace(" ", "")
            if len(variant) < 5 or variant in term_to_entries:
                continue
            bucket = nospace_variants.setdefault(variant, [])
            for e in entries:
                if not any(x[1] is e[1] for x in bucket):
                    bucket.append((len(variant), e[1], e[2]))
        term_to_entries.update(nospace_variants)

        for key, entries in term_to_entries.items():
            self.automaton.add_word(key, entries)
        self.automaton.make_automaton()

    def health_info(self) -> Dict[str, Any]:
        return {
            "status": "ok" if self.ready else "lexicon_missing",
            "ready": self.ready,
            "code_version": CODE_VERSION,
            "rule_version": RULE_VERSION,
            "llm_enabled": False,
            "engine": "Aho-Corasick + 11/11 Rule-based Evidence Review",
            "lexicon_version": self.metadata.get("base_lexicon_filename", "未載入"),
            "lexicon_sha256": self.metadata.get("base_lexicon_sha256", ""),
            "grouped_version": self.metadata.get("grouped_lexicon_filename", "未載入"),
            "grouped_sha256": self.metadata.get("grouped_lexicon_sha256", ""),
            "skill_count": self.metadata.get("skill_count", 0),
            "ai_skill_count": self.metadata.get("ai_skill_count", 0),
            "error": self.load_error,
        }

    def _scan_raw_field_matches(
        self, raw_text: str, field_label: str, sections: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        if not isinstance(raw_text, str) or not raw_text.strip():
            return []

        raw_len = len(raw_text)
        expanded_text = expand_enumeration(raw_text)
        text_case = _normalize_fullwidth_alnum(expanded_text)
        text_lower = _normalize_ascii_hyphen(text_case.lower())
        text_stemmed, stem_start_map, stem_end_map = _stem_english_text_with_map(text_lower, text_case)

        scan_texts = [text_lower] if text_lower == text_stemmed else [text_lower, text_stemmed]
        zh_boundaries = _get_zh_boundaries(text_lower[:raw_len])

        candidates: List[Dict[str, Any]] = []
        for scan_text in scan_texts:
            is_stem_pass = scan_text is not text_lower
            for scan_end_idx, entries in self.automaton.iter(scan_text):
                for term_len, skill, is_zh in entries:
                    if is_zh and is_stem_pass:
                        continue
                    end_idx = scan_end_idx
                    start_idx = end_idx - term_len + 1
                    term_key = scan_text[start_idx:end_idx + 1]

                    if is_zh:
                        if start_idx < raw_len:
                            if start_idx not in zh_boundaries or (end_idx + 1) not in zh_boundaries:
                                continue
                            if term_len in (2, 3) and (
                                scan_text[max(0, start_idx - 1):start_idx + 1] in _ZH_CROSS_WORD_GUARD
                                or scan_text[end_idx:end_idx + 2] in _ZH_CROSS_WORD_GUARD
                            ):
                                continue
                    else:
                        if not _is_word_boundary(scan_text, start_idx, end_idx + 1):
                            continue

                    if is_stem_pass:
                        start_idx = stem_start_map[start_idx]
                        end_idx = stem_end_map[end_idx]

                    if not is_zh and field_label == "職位描述" and self.case_sensitive_terms:
                        owners = self.case_sensitive_terms.get(term_key)
                        if (
                            owners
                            and (skill["SKILL_ID"] or skill["SKILL_NAME"]) in owners
                            and _is_lowercased_word_in_english(text_case, start_idx, end_idx)
                        ):
                            continue

                    if start_idx < raw_len:
                        orig_start = start_idx
                        orig_end = min(end_idx, raw_len - 1)
                        is_mappable = True
                        matched_term = raw_text[orig_start:orig_end + 1]
                    else:
                        orig_start = -1
                        orig_end = -1
                        is_mappable = False
                        matched_term = text_lower[start_idx:end_idx + 1]

                    candidates.append({
                        "start": start_idx,
                        "end": end_idx,
                        "orig_start": orig_start,
                        "orig_end": orig_end,
                        "term_len": term_len,
                        "skill": skill,
                        "is_zh": is_zh,
                        "is_mappable": is_mappable,
                        "is_stem_pass": is_stem_pass,
                        "matched_term": matched_term,
                    })

        kept_candidates = _suppress_shorter_matches(candidates)
        results: List[Dict[str, Any]] = []

        for cand in kept_candidates:
            orig_s = cand["orig_start"]
            orig_e = cand["orig_end"]
            matched_str = cand["matched_term"]

            if field_label == "職位描述" and orig_s >= 0:
                sec = get_section_for_offset(sections, orig_s)
                if orig_s < sec.get("header_end", -1) and not has_chinese(sec.get("header", "")):
                    continue
                snippet = extract_context_snippet(raw_text, orig_s, orig_e)
                is_mod = is_marketing_target_or_domain_modifier(snippet, matched_str)
                sec_type = sec["type"]
            else:
                sec_type = "JOB_DUTIES" if field_label in ("工作技能", "工具欄") else "GENERAL"
                snippet = extract_context_snippet(raw_text, max(0, orig_s), max(0, orig_e))
                is_mod = False

            sid = cand["skill"].get("SKILL_ID", "")
            is_ctx_excl = is_context_excluded(sid, snippet) or lacks_required_context(
                sid, matched_str, raw_text, max(0, orig_s), max(0, orig_e)
            )

            results.append({
                "skill": cand["skill"],
                "matched_term": matched_str,
                "source_field": field_label,
                "start": orig_s,
                "end": orig_e,
                "raw_snippet": snippet,
                "section_type": sec_type,
                "is_domain_modifier": is_mod,
                "is_context_excluded": is_ctx_excl,
                "is_mappable": cand["is_mappable"],
                "match_type": "單複數歸一" if cand["is_stem_pass"] else "原文",
                "MATCHED_FROM": field_label,
            })

        if field_label in _STRUCTURED_FIELD_LABELS and self.structured_exact_tags:
            for m in _STRUCTURED_TAG_PATTERN.finditer(raw_text):
                tag = m.group().strip()
                if not tag:
                    continue
                tag_start = m.start() + m.group().index(tag)
                tag_end = tag_start + len(tag) - 1
                for skill in self.structured_exact_tags.get(tag.lower(), []):
                    snippet = extract_context_snippet(raw_text, tag_start, tag_end)
                    results.append({
                        "skill": skill,
                        "matched_term": tag,
                        "source_field": field_label,
                        "start": tag_start,
                        "end": tag_end,
                        "raw_snippet": snippet,
                        "section_type": "JOB_DUTIES",
                        "is_domain_modifier": False,
                        "is_context_excluded": is_context_excluded(skill.get("SKILL_ID", ""), snippet),
                        "is_mappable": True,
                        "match_type": "結構化欄位精確對照",
                        "MATCHED_FROM": field_label,
                    })

        return results

    def _resolve_ambiguous_by_title(self, texts: List[str], job_title: str) -> List[Dict[str, Any]]:
        combined = "".join(t for t in texts if isinstance(t, str))
        title = job_title if isinstance(job_title, str) else ""
        resolved: List[Dict[str, Any]] = []
        seen_ids: Set[str] = set()
        resolved_words: Set[str] = set()

        for word, rules in _LOCAL_CONTEXT_RULES.items():
            if word not in combined:
                continue
            for pattern, skill_id in rules:
                if skill_id not in self.skill_index or not re.search(pattern, combined):
                    continue
                if skill_id not in seen_ids:
                    seen_ids.add(skill_id)
                    pos = combined.find(word)
                    resolved.append({
                        "skill": self.skill_index[skill_id],
                        "matched_term": word,
                        "source_field": "職位描述",
                        "start": pos,
                        "end": pos + len(word) - 1,
                        "raw_snippet": extract_context_snippet(combined, pos, pos + len(word) - 1),
                        "section_type": "JOB_DUTIES",
                        "is_domain_modifier": False,
                        "is_context_excluded": False,
                        "match_type": "就近文意",
                        "MATCHED_FROM": "就近文意",
                    })
                resolved_words.add(word)

        for word, rules in _TITLE_DISAMBIGUATION.items():
            if word not in combined or word in resolved_words:
                continue
            for title_keywords, skill_id in rules:
                if not skill_id or skill_id not in self.skill_index:
                    continue
                if any(kw in title for kw in title_keywords):
                    if skill_id in seen_ids:
                        continue
                    seen_ids.add(skill_id)
                    pos = combined.find(word)
                    resolved.append({
                        "skill": self.skill_index[skill_id],
                        "matched_term": word,
                        "source_field": "職位描述",
                        "start": pos,
                        "end": pos + len(word) - 1,
                        "raw_snippet": extract_context_snippet(combined, pos, pos + len(word) - 1),
                        "section_type": "JOB_DUTIES",
                        "is_domain_modifier": False,
                        "is_context_excluded": False,
                        "match_type": "職稱消歧",
                        "MATCHED_FROM": "職稱消歧",
                    })
                    break
        return resolved

    @staticmethod
    def _review_skill_evidence(hits: List[Dict[str, Any]]) -> Tuple[str, str, Dict[str, Any]]:
        for h in hits:
            if h["source_field"] in ("工作技能", "工具欄") and not h.get("is_context_excluded", False):
                return "keep", f"明確列於來源欄位 [{h['source_field']}]", h

        duty_hits: List[Dict[str, Any]] = []
        exclude_reasons: List[str] = []

        for h in hits:
            sec = h.get("section_type", "GENERAL")
            if h.get("is_domain_modifier", False):
                exclude_reasons.append(f"命中詞「{h['matched_term']}」為行銷/影音/社群之對象或品牌修飾詞")
                continue
            if h.get("is_context_excluded", False):
                exclude_reasons.append(f"命中詞「{h['matched_term']}」緊鄰或領域脈絡不符（上下文規則排除）")
                continue
            if sec == "COMPANY_INTRO":
                exclude_reasons.append(f"命中詞「{h['matched_term']}」位於公司/品牌介紹段落")
                continue
            if sec == "WELFARE":
                exclude_reasons.append(f"命中詞「{h['matched_term']}」位於員工福利/活動段落")
                continue
            duty_hits.append(h)

        if duty_hits:
            rep = duty_hits[0]
            return "keep", f"工作任務/任職條件段落命中「{rep['matched_term']}」", rep
        if exclude_reasons:
            return "exclude", "；".join(dict.fromkeys(exclude_reasons)), hits[0]
        return "review", "缺乏明確工作任務證據，列為待人工查核", hits[0]

    def extract_single_job(self, job: Dict[str, Any], default_index: int = 1) -> Dict[str, Any]:
        if not self.ready:
            raise RuntimeError(self.load_error or "詞庫尚未就緒")

        job_id = str(job.get("job_id") or job.get("ID") or f"WEB_JOB_{default_index:03d}").strip()
        data_month = str(job.get("data_month") or job.get("資料月份") or datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y%m")).strip()
        job_title = str(job.get("job_title") or job.get("104職位名稱") or "").strip()
        job_desc = str(job.get("job_description") or job.get("職位描述") or "")
        job_skills = str(job.get("job_skills") or job.get("工作技能") or "")
        computer_tools = str(job.get("computer_tools") or job.get("tools") or job.get("電腦工具") or "")

        texts = [job_desc, job_skills, computer_tools]
        sections = parse_text_sections(job_desc)
        field_labels = ["職位描述", "工作技能", "工具欄"]

        all_hits: List[Dict[str, Any]] = []
        for label, raw_txt in zip(field_labels, texts):
            if raw_txt.strip():
                all_hits.extend(self._scan_raw_field_matches(raw_txt, label, sections))

        if not all_hits:
            all_hits.extend(self._resolve_ambiguous_by_title(texts, job_title))

        grouped_hits: Dict[str, List[Dict[str, Any]]] = {}
        for h in all_hits:
            sk = h["skill"].get("SKILL_ID") or h["skill"].get("SKILL_NAME")
            if sk:
                grouped_hits.setdefault(sk, []).append(h)

        retained_skills: List[Dict[str, Any]] = []
        excluded_candidates: List[Dict[str, Any]] = []
        audit_records: List[Dict[str, Any]] = []

        for sk_id, hits in grouped_hits.items():
            decision, reason, rep = self._review_skill_evidence(hits)
            sk_meta = rep["skill"]
            g_code = sk_meta.get("Skill_group10_code")
            g_name = sk_meta.get("Skill_group10") or "待分類"
            if g_code is None:
                g_name = "待分類"

            if decision in ("keep", "review"):
                item = {
                    "SKILL_ID": sk_meta.get("SKILL_ID", ""),
                    "SKILL_NAME": sk_meta.get("SKILL_NAME", ""),
                    "SKILL_NAME_ZH": sk_meta.get("SKILL_NAME_ZH", ""),
                    "SKILL_TYPE": sk_meta.get("SKILL_TYPE", ""),
                    "Category": sk_meta.get("Category_Name", ""),
                    "Subcategory": sk_meta.get("Subcategory_Name", ""),
                    "Category_Code": sk_meta.get("Category_Code"),
                    "Subcategory_Code": sk_meta.get("Subcategory_Code"),
                    "Skill_group10_code": g_code,
                    "Skill_group10": g_name,
                    "Grouping_rule": sk_meta.get("Grouping_rule", ""),
                    "Grouping_status": sk_meta.get("Grouping_status", "待分類"),
                    "Allowed_group_codes": sk_meta.get("Allowed_group_codes", ""),
                    "Ambiguity_note": sk_meta.get("Ambiguity_note", ""),
                    "Is_AI_Skill": bool(sk_meta.get("Is_AI_Skill", False)),
                    "MATCHED_FROM": rep.get("MATCHED_FROM", "職位描述"),
                    "matched_term": rep.get("matched_term", ""),
                    "match_type": rep.get("match_type", "原文"),
                    "evidence_snippet": rep.get("raw_snippet", ""),
                    "section_type": rep.get("section_type", "GENERAL"),
                    "review_status": decision,
                    "decision_reason": reason,
                }
                retained_skills.append(item)

                if decision == "review" or g_code is None or item["Ambiguity_note"]:
                    audit_records.append({
                        "ID": job_id,
                        "資料月份": data_month,
                        "104職位名稱": job_title,
                        "SKILL_ID": item["SKILL_ID"],
                        "SKILL_NAME_ZH": item["SKILL_NAME_ZH"] or item["SKILL_NAME"],
                        "matched_term": item["matched_term"],
                        "source_field": rep.get("source_field", ""),
                        "match_type": item["match_type"],
                        "evidence_snippet": item["evidence_snippet"],
                        "decision": decision,
                        "reason": item["Ambiguity_note"] or reason,
                        "分類狀態": item["Grouping_status"] if g_code is not None else "待分類",
                    })
            else:
                excl = {
                    "ID": job_id,
                    "資料月份": data_month,
                    "104職位名稱": job_title,
                    "SKILL_ID": sk_meta.get("SKILL_ID", ""),
                    "SKILL_NAME_ZH": sk_meta.get("SKILL_NAME_ZH", "") or sk_meta.get("SKILL_NAME", ""),
                    "matched_term": rep.get("matched_term", ""),
                    "source_field": rep.get("source_field", ""),
                    "match_type": rep.get("match_type", "原文"),
                    "evidence_snippet": rep.get("raw_snippet", ""),
                    "decision": "exclude",
                    "reason": reason,
                    "分類狀態": sk_meta.get("Grouping_status", "待分類") if g_code is not None else "待分類",
                }
                excluded_candidates.append(excl)
                audit_records.append(excl)

        group_summary = self._summarize_job_groups(job_id, data_month, job_title, retained_skills)
        ai_count = sum(1 for s in retained_skills if s["Is_AI_Skill"])

        return {
            "job": {
                "ID": job_id,
                "資料月份": data_month,
                "104職位名稱": job_title,
                "職位描述": job_desc,
                "工作技能": job_skills,
                "電腦工具": computer_tools,
                "技能數": len(retained_skills),
                "AI技能數": ai_count,
                "是否命中技能": len(retained_skills) > 0,
            },
            "skills": retained_skills,
            "group10_summary": group_summary,
            "excluded_candidates": excluded_candidates,
            "audit_records": audit_records,
            "stats": {
                "total_skills": len(retained_skills),
                "matched_group_count": len([g for g in group_summary if g["Skill_group10_code"] is not None]),
                "ai_skill_count": ai_count,
                "excluded_count": len(excluded_candidates),
            },
            "metadata": {
                "code_version": CODE_VERSION,
                "rule_version": RULE_VERSION,
                "lexicon_version": self.metadata.get("base_lexicon_filename", ""),
                "grouped_version": self.metadata.get("grouped_lexicon_filename", ""),
                "llm_enabled": False,
            },
        }

    @staticmethod
    def _display_skill_name(skill: Dict[str, Any]) -> str:
        name = str(skill.get("SKILL_NAME_ZH") or "").strip() or str(skill.get("SKILL_NAME") or "").strip()
        return name.split(" | ")[0].strip()

    def _summarize_job_groups(
        self, job_id: str, data_month: str, job_title: str, skills: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        buckets: Dict[Tuple[Optional[int], str], List[Dict[str, Any]]] = {}
        for sk in skills:
            g_code = sk.get("Skill_group10_code")
            g_name = sk.get("Skill_group10") or "待分類"
            if g_code is None:
                g_name = "待分類"
            buckets.setdefault((g_code, g_name), []).append(sk)

        rows: List[Dict[str, Any]] = []
        sorted_keys = sorted(buckets.keys(), key=lambda k: (k[0] is None, k[0] if k[0] is not None else 999, k[1]))
        for g_code, g_name in sorted_keys:
            items = buckets[(g_code, g_name)]
            rows.append({
                "ID": job_id,
                "資料月份": data_month,
                "104職位名稱": job_title,
                "Skill_group10_code": g_code,
                "Skill_group10": g_name,
                "技能清單": GROUP10_SKILL_SEPARATOR.join(self._display_skill_name(x) for x in items),
                "技能數": len(items),
                "AI技能數": sum(1 for x in items if x.get("Is_AI_Skill")),
                "技能ID清單": GROUP10_SKILL_SEPARATOR.join(x.get("SKILL_ID", "") for x in items),
            })
        return rows

    def extract_batch_jobs(
        self,
        jobs: List[Dict[str, Any]],
        dataset_meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self.ready:
            raise RuntimeError(self.load_error or "詞庫尚未就緒")
        if len(jobs) > MAX_BATCH_JOBS:
            raise ValueError(f"單次最多支援 {MAX_BATCH_JOBS} 筆職缺，目前收到 {len(jobs)} 筆。")

        ds_city = str((dataset_meta or {}).get("city") or "")
        ds_sample_version = str((dataset_meta or {}).get("sample_version") or "manual_or_upload")
        ds_id = str((dataset_meta or {}).get("dataset_id") or "")
        lex_ver = self.metadata.get("base_lexicon_filename", "")

        all_jobs: List[Dict[str, Any]] = []
        all_skills_long: List[Dict[str, Any]] = []
        all_group_summary: List[Dict[str, Any]] = []
        all_audit: List[Dict[str, Any]] = []

        for idx, job in enumerate(jobs, start=1):
            res = self.extract_single_job(job, default_index=idx)
            j_info = {
                **res["job"],
                "縣市": str(job.get("縣市") or job.get("city") or ds_city),
                "抽樣版本": ds_sample_version,
                "程式版本": CODE_VERSION,
                "詞庫版本": lex_ver,
            }
            all_jobs.append(j_info)

            for sk in res["skills"]:
                all_skills_long.append({
                    "ID": j_info["ID"],
                    "資料月份": j_info["資料月份"],
                    "縣市": j_info["縣市"],
                    "104職位名稱": j_info["104職位名稱"],
                    **sk,
                    "抽樣版本": ds_sample_version,
                    "程式版本": CODE_VERSION,
                    "詞庫版本": lex_ver,
                })
            for gs in res["group10_summary"]:
                all_group_summary.append({
                    **gs,
                    "縣市": j_info["縣市"],
                })
            all_audit.extend(res["audit_records"])

        return {
            "jobs": all_jobs,
            "skills_long": all_skills_long,
            "group10_summary": all_group_summary,
            "audit_records": all_audit,
            "dataset": {
                "dataset_id": ds_id,
                "city": ds_city,
                "year_month": str((dataset_meta or {}).get("year_month") or ""),
                "sample_version": ds_sample_version,
                "access_level": str((dataset_meta or {}).get("access_level") or ""),
            } if dataset_meta else None,
            "stats": {
                "job_count": len(all_jobs),
                "jobs_with_skills": sum(1 for j in all_jobs if j["是否命中技能"]),
                "zero_skill_jobs": sum(1 for j in all_jobs if not j["是否命中技能"]),
                "total_skill_records": len(all_skills_long),
                "total_ai_skill_records": sum(1 for s in all_skills_long if s["Is_AI_Skill"]),
                "total_excluded_or_audit": len(all_audit),
            },
            "metadata": {
                "code_version": CODE_VERSION,
                "rule_version": RULE_VERSION,
                "lexicon_version": lex_ver,
                "grouped_version": self.metadata.get("grouped_lexicon_filename", ""),
                "sample_version": ds_sample_version,
                "llm_enabled": False,
            },
        }


# =============================================================================
# Dataset Manifest 與安全抽樣 / XLSX 上傳解析
# =============================================================================

EXCLUDED_ROLE = "兼職"


def _clean_cell_str(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    s = str(val).strip()
    return "" if s.lower() == "nan" else s


def parse_uploaded_xlsx(xlsx_bytes: bytes, max_jobs: int = MAX_BATCH_JOBS) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    解析教授上傳的 .xlsx（最多 100 個不重複 (ID/工作編號, 資料月份) 職缺），
    同步套用 11/11 正式版工作角色篩選規則（僅排除「兼職」）。
    """
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        headers_raw = next(rows_iter)
    except StopIteration:
        wb.close()
        raise ValueError("上傳的 Excel 檔案為空。")

    headers = [_clean_cell_str(h) for h in headers_raw]
    seen_keys: Set[Tuple[str, str]] = set()
    jobs: List[Dict[str, Any]] = []
    raw_rows = 0
    excluded_pt = 0
    duplicate_rows = 0

    for row_idx, row in enumerate(rows_iter, start=2):
        if row is None or all(v is None or str(v).strip() == "" for v in row):
            continue
        raw_rows += 1
        rec = {headers[i]: (row[i] if i < len(row) else None) for i in range(len(headers)) if headers[i]}

        role = _clean_cell_str(rec.get("工作角色"))
        if role == EXCLUDED_ROLE:
            excluded_pt += 1
            continue

        job_id = _clean_cell_str(rec.get("ID") or rec.get("工作編號")) or f"UPLOAD_{row_idx}"
        data_month = _clean_cell_str(rec.get("資料月份")) or datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y%m")
        key = (job_id, data_month)
        if key in seen_keys:
            duplicate_rows += 1
            continue
        seen_keys.add(key)

        if len(jobs) >= max_jobs:
            wb.close()
            raise ValueError(f"上傳檔案超過單次上限 {max_jobs} 個不重複職缺，請先分批後再上傳。")

        jobs.append({
            "job_id": job_id,
            "data_month": data_month,
            "job_title": _clean_cell_str(rec.get("104職位名稱") or rec.get("職位名稱") or rec.get("職稱") or rec.get("job_title")),
            "job_description": _clean_cell_str(rec.get("職位描述") or rec.get("job_description") or rec.get("job_desc")),
            "job_skills": _clean_cell_str(rec.get("工作技能") or rec.get("job_skills")),
            "computer_tools": _clean_cell_str(rec.get("電腦工具") or rec.get("tools") or rec.get("computer_tools")),
        })

    wb.close()
    if not jobs:
        raise ValueError("上傳的 Excel 沒有可分析的職缺資料（可能全部為空或均為兼職）。")

    return jobs, {
        "raw_rows": raw_rows,
        "excluded_part_time": excluded_pt,
        "duplicate_rows_skipped": duplicate_rows,
        "accepted_unique_jobs": len(jobs),
    }


class DatasetStore:
    """讀取 dataset_manifest.json 並安全提供已授權／脫敏固定樣本。"""

    def __init__(self, manifest_path: Optional[str] = None):
        self.manifest_path = self._resolve_manifest_path(manifest_path)
        self.ready = False
        self.manifest_version = ""
        self.generated_at = ""
        self.datasets: Dict[str, Dict[str, Any]] = {}
        self.error: Optional[str] = None
        if self.manifest_path and self.manifest_path.is_file():
            try:
                data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
                self.manifest_version = str(data.get("manifest_version") or "1.0.0")
                self.generated_at = str(data.get("generated_at") or "")
                for ds in data.get("datasets", []):
                    did = str(ds.get("dataset_id") or "").strip()
                    if did:
                        self.datasets[did] = ds
                self.ready = True
            except Exception as exc:
                self.error = f"讀取 dataset_manifest.json 失敗：{exc}"
        else:
            self.error = "尚未建立 dataset_manifest.json，請先執行 scripts/prepare_web_datasets.py。"

    @staticmethod
    def _resolve_manifest_path(explicit: Optional[str]) -> Optional[Path]:
        if explicit:
            return Path(explicit)
        env_p = os.environ.get("DATASET_MANIFEST_PATH", "").strip()
        if env_p:
            return Path(env_p)
        root = Path(__file__).resolve().parent.parent
        return root / "web_data/datasets/dataset_manifest.json"

    def list_datasets_payload(self) -> Dict[str, Any]:
        cities: Dict[str, List[Dict[str, Any]]] = {}
        safe_items: List[Dict[str, Any]] = []
        for ds in self.datasets.values():
            item = {
                "dataset_id": ds["dataset_id"],
                "city": ds["city"],
                "year_month": ds["year_month"],
                "source_filename": ds.get("source_filename", ""),
                "source_sha256": ds.get("source_sha256", ""),
                "raw_job_count": ds.get("raw_job_count", ds.get("available_job_count", 0)),
                "filtered_job_count": ds.get("filtered_job_count", ds.get("available_job_count", 0)),
                "available_job_count": ds.get("available_job_count", 0),
                "sample_size": ds.get("sample_size", 0),
                "sample_seed": ds.get("sample_seed", 42),
                "sample_version": ds.get("sample_version", ""),
                "role_filter_rule": ds.get("role_filter_rule", ""),
                "access_level": ds.get("access_level", ""),
                "sampling_modes_supported": ds.get("sampling_modes_supported", ["fixed"]),
            }
            safe_items.append(item)
            cities.setdefault(item["city"], []).append(item)

        return {
            "ready": self.ready,
            "manifest_version": self.manifest_version,
            "generated_at": self.generated_at,
            "cities": {c: sorted(v, key=lambda x: x["year_month"]) for c, v in sorted(cities.items())},
            "datasets": safe_items,
            "error": self.error,
        }

    def load_sample(self, dataset_id: str, mode: str = "fixed", count: int = MAX_BATCH_JOBS) -> Dict[str, Any]:
        if dataset_id not in self.datasets:
            raise KeyError(f"找不到資料集：{dataset_id}")
        ds = self.datasets[dataset_id]
        supported = ds.get("sampling_modes_supported", ["fixed"])
        if mode not in supported:
            raise ValueError(
                f"資料集 {dataset_id} 目前僅支援 {supported} 抽樣模式（不支援 '{mode}'，避免以重排同一批樣本偽裝隨機抽樣）。"
            )
        sample_rel = ds.get("sample_file")
        if not sample_rel or not self.manifest_path:
            raise FileNotFoundError(f"資料集 {dataset_id} 缺少樣本檔設定。")
        sample_path = (self.manifest_path.parent / sample_rel).resolve()
        if sample_path.parent != self.manifest_path.parent.resolve() or not sample_path.is_file():
            raise FileNotFoundError(f"找不到樣本檔：{sample_rel}")

        if sample_path.suffix == ".gz":
            with gzip.open(sample_path, "rt", encoding="utf-8") as f:
                payload = json.load(f)
        else:
            payload = json.loads(sample_path.read_text(encoding="utf-8"))

        jobs_raw = payload.get("jobs", [])
        target_count = max(1, min(int(count), MAX_BATCH_JOBS))

        seen: Set[Tuple[str, str]] = set()
        dedup_jobs: List[Dict[str, Any]] = []
        for j in jobs_raw:
            jid = _clean_cell_str(j.get("ID") or j.get("工作編號"))
            ym = _clean_cell_str(j.get("資料月份"))
            if not jid:
                continue
            key = (jid, ym)
            if key in seen:
                continue
            seen.add(key)
            dedup_jobs.append({
                "job_id": jid,
                "data_month": ym,
                "縣市": ds["city"],
                "job_title": _clean_cell_str(j.get("104職位名稱") or j.get("職位名稱")),
                "job_description": _clean_cell_str(j.get("職位描述")),
                "job_skills": _clean_cell_str(j.get("工作技能")),
                "computer_tools": _clean_cell_str(j.get("電腦工具")),
            })
            if len(dedup_jobs) >= target_count:
                break

        notice = None
        if len(dedup_jobs) < target_count:
            notice = f"此資料集實際可用不重複職缺為 {len(dedup_jobs)} 筆（少於 {target_count} 筆），已全數載入。"

        return {
            "dataset": {
                "dataset_id": ds["dataset_id"],
                "city": ds["city"],
                "year_month": ds["year_month"],
                "source_filename": ds.get("source_filename", ""),
                "source_sha256": ds.get("source_sha256", ""),
                "raw_job_count": ds.get("raw_job_count", 0),
                "available_job_count": ds.get("available_job_count", len(dedup_jobs)),
                "sample_size": len(dedup_jobs),
                "sample_seed": ds.get("sample_seed", 42),
                "sample_version": ds.get("sample_version", ""),
                "role_filter_rule": ds.get("role_filter_rule", ""),
                "access_level": ds.get("access_level", ""),
            },
            "notice": notice,
            "jobs": dedup_jobs,
        }


_DATASET_LOCK = Lock()
_DATASET_INSTANCE: Optional[DatasetStore] = None


def get_dataset_store(manifest_path: Optional[str] = None, force_reload: bool = False) -> DatasetStore:
    global _DATASET_INSTANCE
    with _DATASET_LOCK:
        if _DATASET_INSTANCE is None or force_reload or manifest_path is not None:
            _DATASET_INSTANCE = DatasetStore(manifest_path=manifest_path)
        return _DATASET_INSTANCE


# =============================================================================
# Excel (.xlsx) 4 工作表產生器
# =============================================================================

_TEXT_COLS = {"ID", "資料月份", "SKILL_ID", "技能ID清單", "Allowed_group_codes"}


def _write_sheet(
    ws: openpyxl.worksheet.worksheet.Worksheet,
    columns: List[str],
    rows: List[Dict[str, Any]],
    col_widths: Dict[str, int],
) -> None:
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E3A5F", end_color="1E3A5F", fill_type="solid")
    header_align = Alignment(vertical="center", horizontal="left", wrap_text=True)
    cell_align = Alignment(vertical="top", horizontal="left", wrap_text=True)

    ws.append(columns)
    for col_idx, col_name in enumerate(columns, start=1):
        c = ws.cell(row=1, column=col_idx)
        c.font = header_font
        c.fill = header_fill
        c.alignment = header_align
        ws.column_dimensions[get_column_letter(col_idx)].width = col_widths.get(col_name, 18)

    for row_idx, rec in enumerate(rows, start=2):
        for col_idx, col_name in enumerate(columns, start=1):
            val = rec.get(col_name)
            cell = ws.cell(row=row_idx, column=col_idx)
            if val is None:
                cell.value = ""
            elif col_name in _TEXT_COLS:
                cell.value = str(val)
                cell.data_type = "s"
                cell.number_format = "@"
            elif isinstance(val, bool):
                cell.value = "Y" if val else "N"
            else:
                cell.value = val
                if isinstance(val, str):
                    cell.data_type = "s"
            cell.alignment = cell_align

    ws.freeze_panes = "A2"
    last_col = get_column_letter(len(columns))
    last_row = max(1, len(rows) + 1)
    ws.auto_filter.ref = f"A1:{last_col}{last_row}"


def generate_excel_workbook(batch_result: Dict[str, Any]) -> bytes:
    """
    於記憶體產生標準 4 工作表 Excel (.xlsx)：
    1. Skills_Long
    2. Group10_Summary
    3. Jobs
    4. Audit
    """
    wb = openpyxl.Workbook()

    # 1. Skills_Long
    ws_long = wb.active
    ws_long.title = "Skills_Long"
    long_cols = [
        "ID", "資料月份", "縣市", "104職位名稱",
        "SKILL_ID", "SKILL_NAME", "SKILL_NAME_ZH",
        "Category", "Subcategory",
        "Skill_group10_code", "Skill_group10",
        "MATCHED_FROM", "Is_AI_Skill",
        "Grouping_status", "Allowed_group_codes", "Ambiguity_note",
        "matched_term", "match_type", "evidence_snippet",
        "抽樣版本", "程式版本", "詞庫版本",
    ]
    _write_sheet(ws_long, long_cols, batch_result.get("skills_long", []), {
        "ID": 16, "資料月份": 12, "縣市": 14, "104職位名稱": 26,
        "SKILL_ID": 24, "SKILL_NAME": 28, "SKILL_NAME_ZH": 24,
        "Category": 22, "Subcategory": 24,
        "Skill_group10_code": 18, "Skill_group10": 32,
        "MATCHED_FROM": 14, "Is_AI_Skill": 12,
        "Grouping_status": 14, "Allowed_group_codes": 18, "Ambiguity_note": 34,
        "matched_term": 18, "match_type": 18, "evidence_snippet": 48,
        "抽樣版本": 18, "程式版本": 22, "詞庫版本": 34,
    })

    # 2. Group10_Summary
    ws_g10 = wb.create_sheet("Group10_Summary")
    g10_cols = [
        "ID", "資料月份", "縣市", "104職位名稱",
        "Skill_group10_code", "Skill_group10",
        "技能清單", "技能數", "AI技能數", "技能ID清單",
    ]
    _write_sheet(ws_g10, g10_cols, batch_result.get("group10_summary", []), {
        "ID": 16, "資料月份": 12, "縣市": 14, "104職位名稱": 26,
        "Skill_group10_code": 18, "Skill_group10": 34,
        "技能清單": 48, "技能數": 10, "AI技能數": 10, "技能ID清單": 40,
    })

    # 3. Jobs (保留所有輸入職缺，包含零技能職缺)
    ws_jobs = wb.create_sheet("Jobs")
    jobs_cols = [
        "ID", "資料月份", "縣市", "104職位名稱", "職位描述", "工作技能", "電腦工具",
        "技能數", "AI技能數", "是否命中技能", "抽樣版本", "程式版本", "詞庫版本",
    ]
    _write_sheet(ws_jobs, jobs_cols, batch_result.get("jobs", []), {
        "ID": 16, "資料月份": 12, "縣市": 14, "104職位名稱": 26,
        "職位描述": 60, "工作技能": 28, "電腦工具": 28,
        "技能數": 10, "AI技能數": 10, "是否命中技能": 14,
        "抽樣版本": 18, "程式版本": 22, "詞庫版本": 34,
    })

    # 4. Audit (僅寫入真實取得的排除/待查核/歧義紀錄)
    ws_audit = wb.create_sheet("Audit")
    audit_cols = [
        "ID", "資料月份", "104職位名稱", "SKILL_ID", "SKILL_NAME_ZH",
        "matched_term", "source_field", "match_type", "evidence_snippet",
        "decision", "reason", "分類狀態",
    ]
    _write_sheet(ws_audit, audit_cols, batch_result.get("audit_records", []), {
        "ID": 16, "資料月份": 12, "104職位名稱": 26, "SKILL_ID": 24, "SKILL_NAME_ZH": 22,
        "matched_term": 18, "source_field": 14, "match_type": 18, "evidence_snippet": 48,
        "decision": 12, "reason": 42, "分類狀態": 14,
    })

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


_ENGINE_LOCK = Lock()
_ENGINE_INSTANCE: Optional[WebSkillEngine] = None


def get_web_engine(bundle_path: Optional[str] = None, force_reload: bool = False) -> WebSkillEngine:
    global _ENGINE_INSTANCE
    with _ENGINE_LOCK:
        if _ENGINE_INSTANCE is None or force_reload or bundle_path is not None:
            _ENGINE_INSTANCE = WebSkillEngine(bundle_path=bundle_path)
        return _ENGINE_INSTANCE
