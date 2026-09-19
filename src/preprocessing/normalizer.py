"""文字正規化模組：提供空白清理、字串轉型與檔名中繼資料解析。"""

import os
import re
from typing import Any


def clean_text(text: Any) -> str:
    """清理文字：轉為字串、移除不可見字元與首尾空白。"""
    if text is None:
        return ""
    s = str(text).strip()
    if s.lower() == "nan":
        return ""
    return s


def extract_county(filename: str) -> str:
    """從檔案名稱中解析縣市名稱。"""
    name = os.path.basename(filename)
    name = name.replace("cleaned_", "").replace(".xlsx", "").replace(".csv", "")
    name = re.sub(r"_combined(\.csv)?(_\d{6})?$", "", name)
    name = re.sub(r"_\d{6}$", "", name)
    name = re.sub(r"^skills_", "", name)
    name = re.sub(r"_wide$", "", name)
    return name


def extract_month(filename: str) -> str:
    """從檔案名稱中解析 6 位數年月字串 (如 202608)。"""
    m = re.search(r"(\d{6})", os.path.basename(filename))
    return m.group(1) if m else "unknown"
