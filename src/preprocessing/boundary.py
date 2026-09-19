"""文字邊界檢查模組：提供中英文詞界判定與字元屬性判斷。"""

import re
from typing import Set
import jieba


def has_chinese(text: str) -> bool:
    """檢查字串是否包含中文字元。"""
    return bool(re.search(r"[\u4e00-\u9fff]", str(text)))


def get_zh_boundaries(text: str) -> Set[int]:
    """使用 jieba 斷詞取得字元邊界位置集合。
    
    用於確保中文匹配必須落在斷詞邊界上，避免如「資料庫」被切分命中「庫」的錯誤。
    """
    positions = {0}
    pos = 0
    for token in jieba.cut(text):
        pos += len(token)
        positions.add(pos)
    return positions


def is_ascii_alnum(c: str) -> bool:
    """檢查字元是否為 ASCII 字母或數字。"""
    return c.isascii() and c.isalnum()


def is_word_boundary(text: str, start: int, end: int) -> bool:
    """檢查英文詞彙在指定 start 與 end 範圍是否為完整單詞邊界。
    
    前後不可緊鄰英數字或底線。
    """
    before_ok = (start == 0) or (not is_ascii_alnum(text[start - 1]) and text[start - 1] != "_")
    after_ok = (end == len(text)) or (not is_ascii_alnum(text[end]) and text[end] != "_")
    return before_ok and after_ok
