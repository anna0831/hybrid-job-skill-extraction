"""列舉展開模組：處理繁中職缺中常見的「共用字尾省略」與「頓號/句點列舉」。"""

import re
from typing import List, Optional

_DEFAULT_SUFFIXES = [
    "服務", "作業", "管理", "處理", "工作", "技巧", "能力",
    "維護", "操作", "製作", "訓練", "分析", "規劃", "執行", "經驗"
]
_ENUM_SEP = r"、|\."


def build_enum_pattern(suffixes: Optional[List[str]] = None) -> re.Pattern:
    """根據字尾列表編譯列舉正則表達式。"""
    sufs = suffixes if suffixes is not None else _DEFAULT_SUFFIXES
    suffix_pattern = "|".join(re.escape(s) for s in sufs)
    pattern_str = (
        rf"([^、，,。.\s\d]{{1,2}}(?:(?:{_ENUM_SEP})[^、，,。.\s\d]{{1,2}}){{2,4}})({suffix_pattern})"
    )
    return re.compile(pattern_str)


_DEFAULT_ENUM_PATTERN = build_enum_pattern(_DEFAULT_SUFFIXES)
_HAIR_SALON_PATTERN = re.compile(
    rf"((?:[剪染燙護洗造](?:{_ENUM_SEP})){{1,4}}[剪染燙護洗造])(?:服務|作業)?"
)


def expand_enumeration(text: str, suffixes: Optional[List[str]] = None) -> str:
    """展開職缺內文中的頓號/句點省略列舉。
    
    例如：
      「加油.洗車.清潔」-> 附加「加油作業 洗車作業 清潔作業」
      「剪、染、洗服務」-> 附加「剪髮 染髮 洗髮」
    展開後的完整詞附加在文字尾端，使 AC 自動機能完整抓取。
    """
    if not isinstance(text, str) or ("、" not in text and "." not in text):
        return text

    pattern = build_enum_pattern(suffixes) if suffixes is not None else _DEFAULT_ENUM_PATTERN
    expansions: List[str] = []

    # 一般共用字尾列舉展開 (例: A、B、C + 字尾)
    for m in pattern.finditer(text):
        heads = re.split(_ENUM_SEP, m.group(1))
        suffix = m.group(2)
        for h in heads:
            h_clean = h.strip()
            if h_clean and not h_clean.endswith(suffix):
                expansions.append(h_clean + suffix)

    # 美髮業特例展開：「剪、染、洗服務」省略中間「髮」字
    for m in _HAIR_SALON_PATTERN.finditer(text):
        for ch in re.split(_ENUM_SEP, m.group(1)):
            ch_clean = ch.strip()
            if ch_clean:
                expansions.append(ch_clean + "髮")

    if expansions:
        return text + " " + " ".join(expansions)
    return text
