"""
============================================================
獨立單檔技能擷取腳本 (Long Format + 建議十大技能分類架構)
— 不依賴 104_run_all_months.py，單獨複製這一個檔案即可執行
============================================================

【用途】
  吃一個指定的清理後 Excel 職缺檔案（通常對應一個縣市、一個月份），
  執行技能比對並輸出 Long format 與選擇性 Wide format 表格。

【輸出檔案】
  1. 主要輸出 (Long Format)：
     - skills_{縣市}_{月份}_long.xlsx
     - skills_{縣市}_{月份}_long.parquet
     粒度：同一縣市、月份、職缺 ID 下，每個實際擷取到的 Skill_ID 一列。
     未命中技能的職缺不建立假技能列；全檔零命中時輸出含完整欄位之空表。
     若資料列數超過 Excel 單一工作表上限 (1,048,575 列)，自動分頁輸出不截斷。

  2. 選擇性輸出 (Wide Format)：
     - skills_{縣市}_{月份}_wide.xlsx
     預設關閉 (EXPORT_WIDE = False)，可透過命令列參數 `--wide` 開啟。
     若開啟，同步改用 Word 建議十大主分類匯總技能欄位。

【輸出欄位順序 (固定 25 欄)】
  1.  Category_Name          (原始詞庫大類名稱，如 Information Technology)
  2.  Subcategory_Name       (原始詞庫小類名稱，如 Software Applications)
  3.  ID                     (職缺編號/工作編號，字串型別，保留前導零)
  4.  資料月份                 (輸入檔原始資料月份，保留原值不與檔名月份覆蓋)
  5.  刊登日期                 (原始職缺刊登日期)
  6.  工作角色                 (原始職缺工作角色，如 全職)
  7.  104職位名稱              (原始職缺 104職位名稱 / 職位名稱)
  8.  104職位名稱碼            (原始職缺 104職位名稱碼 / 職位名稱碼，保留前導零)
  9.  職位描述                 (原始職缺職位描述完整文字，不截斷不摘要)
  10. 工作技能                 (原始職缺工作技能完整文字)
  11. 電腦工具                 (原始職缺電腦工具/擅長工具完整文字)
  12. 縣市                   (縣市名稱，如 彰化縣)
  13. 月份                   (由檔名擷取之資料月份，如 202608)
  14. SKILL_ID               (技能唯一代碼，如 KS120L96KMYTDJ48NRSH)
  15. SKILL_NAME             (技能英文名稱，如 Software Development)
  16. SKILL_NAME_ZH          (技能中文名稱，如 軟體開發)
  17. SKILL_TYPE             (技能類型，如 Specialized Skill / Common Skill)
  18. Category_Code          (原始詞庫大類代碼，可空整數)
  19. Subcategory_Code       (原始詞庫小類代碼，可空整數)
  20. Skill_group10_code     (建議十大主分類代碼，可空整數 1～10)
  21. Skill_group10          (建議十大主分類名稱，與代碼嚴格一致)
  22. Grouping_rule          (詞庫分類規則碼，GR1～GR7)
  23. Grouping_status        (分類狀態：已對應 / 待人工分類 / 分類衝突)
  24. MATCHED_FROM           (擷取來源欄位或補救規則：職位描述/工作技能/工具欄/就近文意/職稱消歧)
  25. IS_SOFTWARE            (軟體技能布林標記：True / False)

【十大技能分類對應 (依據 Word 建議版規範)】
  1: 認知、分析與創新技能
  2: 溝通、語言與人際技能
  3: 個人特質、自我管理與身體能力
  4: 財務、會計與經濟技能
  5: 管理、商業、法遵與治理技能
  6: 行政與一般數位技能
  7: 營運、技職與第一線服務技能
  8: 資訊科技、軟體、資料與AI技能
  9: 醫療、健康與照護技能
  10: 工程、自然科學、設計、環境與能源技能

【執行方式】
  # 方式 1：指定職缺檔案路徑 (相容既有使用習慣)
  python3 104_single_file_20260930.py dataset/cleaned_彰化縣_202608.xlsx

  # 方式 2：使用預設設定執行
  python3 104_single_file_20260930.py

  # 方式 3：帶入參數並開啟寬表輸出
  python3 104_single_file_20260930.py dataset/cleaned_彰化縣_202608.xlsx --wide -o ./AC後檔案
============================================================
"""

import re
import os
import sys
import time
import warnings
import argparse
import jieba
import nltk
import ahocorasick
import pandas as pd
import numpy as np
from nltk.stem import PorterStemmer

warnings.filterwarnings("ignore")
nltk.download("wordnet", quiet=True)
nltk.download("omw-1.4", quiet=True)
jieba.setLogLevel(60)

# ============================================================
# 【使用者設定區】
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_PATH = os.path.join(BASE_DIR, "dataset/cleaned_彰化縣_202608.xlsx")
# 優先採用根目錄最新 0930 詞庫，若不存在則相容退回 outputs/temp/0918 詞庫
_DEFAULT_LEX = "詞庫skill_lexicon_v13_20260930.xlsx" if os.path.exists(os.path.join(BASE_DIR, "詞庫skill_lexicon_v13_20260930.xlsx")) else "outputs/temp/詞庫skill_lexicon_v13_20260918.xlsx"
LEXICON_PATH = os.path.join(BASE_DIR, _DEFAULT_LEX)
GROUPED_LEXICON_PATH = os.path.join(BASE_DIR, "詞庫skill_lexicon_v13_Chen_grouped_09_2026.xlsx")
OUTPUT_DIR = os.path.join(BASE_DIR, "AC 後檔案")
EXPORT_WIDE = False
# ============================================================

# 十大技能分類官方定義 (依據 Word 建議版文件與 Chen 詞庫規範)
EXPECTED_GROUP10 = {
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

# 輸出欄位順序 (固定 25 欄)
FINAL_COLUMNS = [
    "Category_Name",
    "Subcategory_Name",
    "ID",
    "資料月份",
    "刊登日期",
    "工作角色",
    "104職位名稱",
    "104職位名稱碼",
    "職位描述",
    "工作技能",
    "電腦工具",
    "縣市",
    "月份",
    "SKILL_ID",
    "SKILL_NAME",
    "SKILL_NAME_ZH",
    "SKILL_TYPE",
    "Category_Code",
    "Subcategory_Code",
    "Skill_group10_code",
    "Skill_group10",
    "Grouping_rule",
    "Grouping_status",
    "MATCHED_FROM",
    "IS_SOFTWARE",
]

# 台灣製造/品質領域重要 2 字詞，jieba 預設不認識會拆開，需強制加入
_JIEBA_2CHAR_WHITELIST = {
    "製程", "量試", "試作", "送樣", "首件", "稼働", "治具",
    "備料", "備件", "標案", "採購", "詢價", "驗收",
    "輪班", "物性", "化性", "採樣",
}

# 有意義的 2 字中文技能關鍵字白名單
# （一般規則：中文 < 3 字會被過濾；此白名單的 2 字詞例外放行）
_ZH_2CHAR_SKILL_ALLOWLIST = {
    "銷售", "行銷", "推廣", "開發",
    "研發", "設計", "開發", "繪圖", "建模",
    "生產", "製造", "組裝", "加工", "備料", "安裝",
    "品管", "稽核", "檢驗", "管控",
    "採購", "倉儲", "物流", "配送",
    "財務", "會計", "人資", "薪資",
    "維修", "保養", "操作", "校正",
    "翻譯", "口譯",
    # 餐飲外場
    "跑單", "擺盤", "送餐", "帶位", "倒水", "點餐", "收銀", "結帳",
    # 照顧服務／清潔衛生
    "消毒", "更衣", "沐浴",
    # 保全
    "巡邏",
    # 基層領班／督導
    "督導", "班長",
    # 美髮
    "剪髮", "染髮", "洗髮", "燙髮", "護髮",
    # 餐飲清潔
    "洗碗", "打掃",
    # 全面稽核補齊放行之 2 字詞
    "傳票", "立帳", "分錄", "良率", "沖帳",
    "備菜", "打餐", "舌診", "脈診", "刷手", "煎肉", "試教",
    "清潔", "洗車", "推銷",
}

# ============================================================
# 同義詞字典（2026-09-07 正式落地：「方法二」）
# ============================================================
_SYNONYM_GROUPS = [
    {"老師", "教師"},
    {"飲料", "飲品"},
    {"會客登記", "登記換證", "訪客登記"},
    {"駕駛接送", "接送任務"},
    {"車輛加油", "加油作業", "油箱加油"},
    {"打掃", "清潔"},
    {"藥品調劑", "調劑處方", "藥事調劑"},
]


def expand_synonyms(term: str) -> set:
    """回傳這個詞套用同義詞字典後，能生成的所有變體（不含自己）。"""
    variants = set()
    for group in _SYNONYM_GROUPS:
        for m in group:
            if m in term:
                for m2 in group:
                    if m2 != m:
                        variants.add(term.replace(m, m2))
    variants.discard(term)
    return variants


SOFTWARE_CATEGORIES = {17, 370, 369, 371, 372, 373, 374, 375, 376, 377, 378, 379, 380}
MAX_EXCEL_ROWS = 1048575  # Excel 最大列數上限 1,048,576 扣除表頭 1 列
_stemmer = PorterStemmer()


def has_chinese(text: str) -> bool:
    return bool(re.search(r"[一-鿿]", str(text)))


def extract_county(filename: str) -> str:
    """從各種格式的檔名中擷取縣市名稱"""
    base = os.path.basename(filename)
    m = re.search(r"([\u4e00-\u9fa5]{2,3}[縣市])", base)
    if m:
        return m.group(1)
    name = base.replace("cleaned_", "").replace(".xlsx", "").replace(".parquet", "")
    name = re.sub(r"_combined(\.csv)?(_\d{6})?$", "", name)
    name = re.sub(r"_\d{6}$", "", name)
    return name


def extract_month(filename: str) -> str:
    m = re.search(r"(\d{6})", os.path.basename(filename))
    return m.group(1) if m else "unknown"


def _stem_english_text(text: str) -> str:
    return re.sub(r"[a-z]+", lambda m: _stemmer.stem(m.group()), text)


_ENUM_SUFFIXES = ["服務", "作業", "管理", "處理", "工作", "技巧", "能力",
                  "維護", "操作", "製作", "訓練", "分析", "規劃", "執行", "經驗"]
_ENUM_SUFFIX_PATTERN = "|".join(_ENUM_SUFFIXES)
_ENUM_SEP = "、|\\."
_ENUM_PATTERN = re.compile(
    rf"([^、，,。.\s\d]{{1,2}}(?:(?:{_ENUM_SEP})[^、，,。.\s\d]{{1,2}}){{2,4}})({_ENUM_SUFFIX_PATTERN})"
)


def expand_enumeration(text: str) -> str:
    if not isinstance(text, str) or ("、" not in text and "." not in text):
        return text
    expansions = []
    for m in _ENUM_PATTERN.finditer(text):
        heads = re.split(_ENUM_SEP, m.group(1))
        suffix = m.group(2)
        for h in heads:
            if h and not h.endswith(suffix):
                expansions.append(h + suffix)

    for m in re.finditer(rf"((?:[剪染燙護洗造](?:{_ENUM_SEP})){{1,4}}[剪染燙護洗造])(?:服務|作業)?", text):
        for ch in re.split(_ENUM_SEP, m.group(1)):
            expansions.append(ch + "髮")

    if expansions:
        return text + " " + " ".join(expansions)
    return text


def _get_zh_boundaries(text: str) -> set:
    positions = {0}
    pos = 0
    for token in jieba.cut(text):
        pos += len(token)
        positions.add(pos)
    return positions


def _is_ascii_alnum(c: str) -> bool:
    return c.isascii() and c.isalnum()


def _is_word_boundary(text: str, start: int, end: int) -> bool:
    before_ok = (start == 0) or (not _is_ascii_alnum(text[start - 1]) and text[start - 1] != "_")
    after_ok = (end == len(text)) or (not _is_ascii_alnum(text[end]) and text[end] != "_")
    return before_ok and after_ok


def load_grouping_metadata(grouped_path: str):
    """
    從 Chen_grouped 詞庫 Sheet1 載入十大分類 metadata。
    進行嚴格欄位檢查、分類代碼與名稱一致性驗證、重複 ID 衝突檢測。

    回傳：
        id_lookup: dict[Skill_ID -> dict]
        name_lookup: dict[Skill_Name -> dict] (供 Skill_ID 為空者補充查找)
        conflicts: list[dict]
    """
    if not os.path.exists(grouped_path):
        raise FileNotFoundError(f"找不到十大分類詞庫檔案：{grouped_path}")

    print(f"  讀取十大分類詞庫：{grouped_path}")
    df_chen = pd.read_excel(grouped_path, sheet_name="Sheet1")
    req_cols = ["Skill_ID", "Skill_group10", "Skill_group10_code", "Grouping_rule"]
    missing_cols = [c for c in req_cols if c not in df_chen.columns]
    if missing_cols:
        raise ValueError(f"十大分類詞庫 (Chen_grouped) Sheet1 缺少必要欄位：{missing_cols}。請檢查檔案欄位名稱！")

    id_lookup = {}
    name_lookup = {}
    conflicts = []

    for _, row in df_chen.iterrows():
        raw_sid = row["Skill_ID"]
        sid = str(raw_sid).strip() if pd.notna(raw_sid) and str(raw_sid).strip().lower() != "nan" else ""
        sname = str(row.get("Skill_Name", "")).strip() if pd.notna(row.get("Skill_Name")) else ""

        # 分類代碼轉換為可空整數
        code_val = row["Skill_group10_code"]
        if pd.notna(code_val):
            try:
                code_int = int(code_val)
            except (ValueError, TypeError):
                code_int = None
        else:
            code_int = None

        group_name = str(row["Skill_group10"]).strip() if pd.notna(row["Skill_group10"]) else ""
        group_rule = str(row["Grouping_rule"]).strip() if pd.notna(row["Grouping_rule"]) else ""

        # 核對代碼與名稱是否一致
        if code_int is not None and code_int in EXPECTED_GROUP10:
            expected_name = EXPECTED_GROUP10[code_int]
            if group_name and group_name != expected_name:
                print(f"  ⚠️ 分類代碼與名稱不一致警告：ID={sid}, code={code_int}, got={group_name}, expected={expected_name}")

        meta = {
            "Skill_group10_code": code_int,
            "Skill_group10": group_name,
            "Grouping_rule": group_rule,
            "conflict": False,
        }

        if sid:
            if sid in id_lookup:
                existing = id_lookup[sid]
                # 檢查同一 Skill_ID 是否存在衝突
                if existing["Skill_group10_code"] != meta["Skill_group10_code"] or \
                   existing["Skill_group10"] != meta["Skill_group10"] or \
                   existing["Grouping_rule"] != meta["Grouping_rule"]:
                    conflicts.append({"Skill_ID": sid, "existing": existing, "new": meta})
                    existing["conflict"] = True
            else:
                id_lookup[sid] = meta
        elif sname:
            if sname not in name_lookup:
                name_lookup[sname] = meta

    print(f"  十大分類對應表載入完成：{len(id_lookup):,} 筆唯一 Skill_ID，{len(name_lookup):,} 筆無 ID 技能對應，{len(conflicts)} 筆分類衝突")
    return id_lookup, name_lookup, conflicts


def load_automaton(lexicon_path: str, grouped_lexicon_path: str = None):
    """
    載入 20260918 基底詞庫，並以 Chen_grouped Sheet1 補入建議十大分類 metadata，
    設定 jieba 自訂詞典並建立 Aho-Corasick 自動機。
    """
    if not os.path.exists(lexicon_path):
        raise FileNotFoundError(f"找不到基底詞庫檔案：{lexicon_path}")

    # 載入十大分類 metadata
    if grouped_lexicon_path and os.path.exists(grouped_lexicon_path):
        id_lookup, name_lookup, conflicts = load_grouping_metadata(grouped_lexicon_path)
    else:
        print(f"  ⚠️ 未提供或找不到十大分類詞庫：{grouped_lexicon_path}，所有技能將標記為「待人工分類」")
        id_lookup, name_lookup, conflicts = {}, {}, []

    print(f"  讀取基底詞庫：{lexicon_path}")
    lex = pd.read_csv(lexicon_path) if str(lexicon_path).lower().endswith(".csv") else pd.read_excel(lexicon_path)

    req_base_cols = ["Category_Code", "Category_Name", "Subcategory_Code", "Subcategory_Name",
                     "Skill_ID", "Skill_Name", "Skill_Name_ZH", "Skill_Type", "Keywords"]
    missing_base = [c for c in req_base_cols if c not in lex.columns]
    if missing_base:
        raise ValueError(f"基底詞庫缺少必要欄位：{missing_base}")

    for w in _JIEBA_2CHAR_WHITELIST:
        jieba.add_word(w, freq=1000)

    jcount = 0
    term_to_entries = {}

    for _, row in lex.iterrows():
        try:
            cat_code = int(row["Category_Code"])
        except (ValueError, TypeError):
            cat_code = None

        try:
            subcat_code = int(row["Subcategory_Code"])
        except (ValueError, TypeError):
            subcat_code = None

        raw_sid = row.get("Skill_ID")
        sid_str = str(raw_sid).strip() if pd.notna(raw_sid) and str(raw_sid).strip().lower() != "nan" else ""
        sname_str = str(row.get("Skill_Name", "")).strip() if pd.notna(row.get("Skill_Name")) else ""

        # 十大分類對應與狀態判定
        if sid_str:
            if sid_str in id_lookup:
                meta = id_lookup[sid_str]
                if meta.get("conflict"):
                    group10_code = pd.NA
                    group10_name = ""
                    group_rule = ""
                    group_status = "分類衝突"
                else:
                    group10_code = meta["Skill_group10_code"]
                    group10_name = meta["Skill_group10"]
                    group_rule = meta["Grouping_rule"]
                    group_status = "已對應"
            else:
                # 0918 有但 Chen 無之 ID (如 5 個已知的 TW_ 技能)
                group10_code = pd.NA
                group10_name = ""
                group_rule = ""
                group_status = "待人工分類"
        else:
            # Skill_ID 為空者，若 Skill_Name 在補充對應表中則繼承其分類
            if sname_str in name_lookup:
                meta = name_lookup[sname_str]
                if meta.get("conflict"):
                    group10_code = pd.NA
                    group10_name = ""
                    group_rule = ""
                    group_status = "分類衝突"
                else:
                    group10_code = meta["Skill_group10_code"]
                    group10_name = meta["Skill_group10"]
                    group_rule = meta["Grouping_rule"]
                    group_status = "已對應"
            else:
                group10_code = pd.NA
                group10_name = ""
                group_rule = ""
                group_status = "待人工分類"

        is_sw = (cat_code in SOFTWARE_CATEGORIES) if cat_code is not None else False

        skill = {
            "Category_Name":          str(row["Category_Name"]).strip() if pd.notna(row.get("Category_Name")) else "",
            "Subcategory_Name":       str(row["Subcategory_Name"]).strip() if pd.notna(row.get("Subcategory_Name")) else "",
            "SKILL_ID":               sid_str,
            "SKILL_NAME":             sname_str,
            "SKILL_NAME_ZH":          str(row["Skill_Name_ZH"]).strip() if pd.notna(row.get("Skill_Name_ZH")) else "",
            "SKILL_TYPE":             str(row["Skill_Type"]).strip() if pd.notna(row.get("Skill_Type")) else "",
            "Category_Code":          cat_code if cat_code is not None else pd.NA,
            "Subcategory_Code":       subcat_code if subcat_code is not None else pd.NA,
            "Skill_group10_code":     group10_code if group10_code is not None else pd.NA,
            "Skill_group10":          group10_name,
            "Grouping_rule":          group_rule,
            "Grouping_status":        group_status,
            "IS_SOFTWARE":            is_sw,
            "SKILL_CAT9":             str(row.get("Skill_Category")) if pd.notna(row.get("Skill_Category")) else "Unclassified",
        }

        terms = []
        zh = str(row.get("Skill_Name_ZH", "")).strip()
        if has_chinese(zh) and (len(zh) >= 3 or zh in _ZH_2CHAR_SKILL_ALLOWLIST):
            terms.append((zh, True))
            jieba.add_word(zh, freq=1000); jcount += 1
        elif not has_chinese(zh):
            en = str(row.get("Skill_Name", "")).strip().lower()
            if len(en) >= 2:
                terms.append((en, False))

        kw_str = str(row.get("Keywords", "")).strip()
        if kw_str and kw_str.lower() != "nan":
            for kw in kw_str.split("｜"):
                kw = kw.strip()
                if has_chinese(kw):
                    if len(kw) < 2 or (len(kw) == 2 and kw not in _ZH_2CHAR_SKILL_ALLOWLIST):
                        continue
                    terms.append((kw, True))
                    jieba.add_word(kw, freq=1000); jcount += 1
                else:
                    if len(kw) < 2:
                        continue
                    terms.append((kw.lower(), False))

        # 同義詞字典展開
        extra_syn = []
        for term, is_zh in terms:
            if not is_zh:
                continue
            for variant in expand_synonyms(term):
                if len(variant) >= 3 or variant in _ZH_2CHAR_SKILL_ALLOWLIST:
                    extra_syn.append((variant, True))
                    jieba.add_word(variant, freq=1000); jcount += 1
        terms.extend(extra_syn)

        # 英文詞加詞幹 (門檻 >= 7)
        extra = []
        for term, is_zh in terms:
            if not is_zh:
                stemmed = _stemmer.stem(term)
                if stemmed != term and len(stemmed) >= 7:
                    extra.append((stemmed, False))
        terms.extend(extra)

        seen = set()
        for term, is_zh in terms:
            if term in seen:
                continue
            seen.add(term)
            entry = (len(term), skill, is_zh)
            if term not in term_to_entries:
                term_to_entries[term] = []
            # 依 SKILL_ID (若有) 或 SKILL_NAME 避免同一詞條重複掛載同技能
            dedup_identity = skill["SKILL_ID"] if skill["SKILL_ID"] else skill["SKILL_NAME"]
            if not any((e[1]["SKILL_ID"] if e[1]["SKILL_ID"] else e[1]["SKILL_NAME"]) == dedup_identity for e in term_to_entries[term]):
                term_to_entries[term].append(entry)

    A = ahocorasick.Automaton()
    for term, entries in term_to_entries.items():
        A.add_word(term, entries)
    A.make_automaton()

    print(f"  詞條數：{len(term_to_entries):,}，jieba 自訂詞：{jcount:,}")
    return A


def _suppress_shorter_matches(candidates: list, scan_text: str):
    """最長匹配優先：若某段文字同時被短詞與完全涵蓋它的長詞命中，
    且兩者對應不同技能，捨棄短詞、只保留長詞。回傳 (保留的候選, 被抑制掉的字面文字集合)"""
    kept = []
    suppressed_texts = set()
    for i, a in enumerate(candidates):
        covered = False
        for j, b in enumerate(candidates):
            if i == j or a["skill"]["SKILL_ID"] == b["skill"]["SKILL_ID"]:
                continue
            if b["term_len"] <= a["term_len"]:
                continue
            if b["start"] <= a["start"] and b["end"] >= a["end"]:
                covered = True
                break
        if covered:
            suppressed_texts.add(scan_text[a["start"]:a["end"] + 1])
        else:
            kept.append(a)
    return kept, suppressed_texts


def build_skill_id_index(automaton) -> dict:
    """建立 Skill_ID -> 技能 dict 的查找表，供職稱消歧邏輯用。"""
    index = {}
    for term in automaton.keys():
        for term_len, skill, is_zh in automaton.get(term):
            if skill["SKILL_ID"]:
                index.setdefault(skill["SKILL_ID"], skill)
    return index


_TITLE_DISAMBIGUATION = {
    "開發": [
        (["軟體", "韌體", "程式", "資訊", "app", "APP", "IT"], "KS120L96KMYTDJ48NRSH"),  # 軟體開發
        (["業務", "銷售"], "KS1212B6QR5SK1LSD4S4"),                                        # 商業開發
        (["產品經理", "產品企劃", "研發"], "KS1270P6SLFCFT476Y3R"),                        # 新產品開發
    ],
    "設計": [
        (["機構"], "KS1269J6YQG4J3V5YGGW"),                                                # 機構設計
        (["電子", "電機", "硬體", "ic", "IC", "韌體", "類比"], "KS121X369RKT17LSJNZX"),    # 電路設計
        (["室內", "裝潢"], "KS122SP76CJCX9T70P6B"),                                        # 室內設計
        (["美編", "平面", "視覺", "ui", "UI", "ux", "UX", "廣告"], "KS124H46Q2PP8YC1WQ06"), # 平面設計
    ],
    "操作": [
        (["作業員", "技術員", "機台", "生產", "製造", "產線"], "TW_MFG_001"),  # 機台操作
    ],
    "管控": [
        (["品管", "品保", "QA", "QC", "稽核", "檢驗"], "KS1289C6QS0TSSB4PNGG"),  # 品質管理
        (["生產", "製造", "產線", "製程"], "KS1282X64QGHTFWQ8J2Y"),             # 生產管理
    ],
}

_LOCAL_CONTEXT_RULES = {
    "開發": [
        (r"產品[之的]?開發", "KS1270P6SLFCFT476Y3R"),  # 新產品開發
    ],
}


def resolve_ambiguous_by_title(texts: list, job_title: str, automaton, skill_index: dict) -> list:
    """整篇職缺比對不到任何技能時，先看籠統字附近的文字有沒有更直接的線索（就近文意），
    沒有的話才退而求其次，用「104職位名稱」判斷屬於哪個領域。"""
    combined = "".join(t for t in texts if isinstance(t, str))
    title = job_title if isinstance(job_title, str) else ""
    resolved = []
    seen_ids = set()
    resolved_words = set()

    # 第一層：就近文意
    for word, rules in _LOCAL_CONTEXT_RULES.items():
        if word not in combined:
            continue
        for pattern, skill_id in rules:
            if skill_id not in skill_index or not re.search(pattern, combined):
                continue
            if skill_id not in seen_ids:
                seen_ids.add(skill_id)
                resolved.append({**skill_index[skill_id], "MATCHED_FROM": "就近文意"})
            resolved_words.add(word)

    # 第二層：職稱消歧
    for word, rules in _TITLE_DISAMBIGUATION.items():
        if word not in combined or word in resolved_words:
            continue
        for title_keywords, skill_id in rules:
            if not skill_id or skill_id not in skill_index:
                continue
            if any(kw in title for kw in title_keywords):
                if skill_id in seen_ids:
                    continue
                seen_ids.add(skill_id)
                resolved.append({**skill_index[skill_id], "MATCHED_FROM": "職稱消歧"})
                break
    return resolved


def match_skills(texts: list, automaton) -> list:
    field_labels = ["職位描述", "工作技能", "工具欄"]
    seen_ids      = set()
    seen_zh_terms = set()
    results = []

    for label, raw_text in zip(field_labels, texts):
        if not isinstance(raw_text, str) or not raw_text.strip():
            continue
        raw_text = expand_enumeration(raw_text)
        text_lower = raw_text.lower()
        text_stemmed = _stem_english_text(text_lower)
        scan_texts = [text_lower] if text_lower == text_stemmed else [text_lower, text_stemmed]
        zh_boundaries = _get_zh_boundaries(text_lower)
        suppressed_texts = set()

        for scan_text in scan_texts:
            candidates = []
            for end_idx, entries in automaton.iter(scan_text):
                for term_len, skill, is_zh in entries:
                    start_idx = end_idx - term_len + 1
                    if is_zh:
                        if scan_text is text_lower:
                            if start_idx not in zh_boundaries or (end_idx + 1) not in zh_boundaries:
                                continue
                    else:
                        if not _is_word_boundary(scan_text, start_idx, end_idx + 1):
                            continue
                    candidates.append({
                        "start": start_idx, "end": end_idx,
                        "term_len": term_len, "skill": skill, "is_zh": is_zh,
                    })

            kept, newly_suppressed = _suppress_shorter_matches(candidates, scan_text)
            suppressed_texts |= newly_suppressed

            for cand in kept:
                matched_term = scan_text[cand["start"]:cand["end"] + 1]
                if matched_term in suppressed_texts:
                    continue
                if cand["is_zh"]:
                    if matched_term in seen_zh_terms:
                        continue
                    seen_zh_terms.add(matched_term)

                skill_id = cand["skill"]["SKILL_ID"]
                if skill_id in seen_ids:
                    continue
                seen_ids.add(skill_id)
                results.append({**cand["skill"], "MATCHED_FROM": label})
    return results


def _clean_str_preserve_leading_zero(val) -> str:
    """清理數值/字串並嚴格保留前導零，去除字面 nan/None/.0"""
    if pd.isna(val) or val is None:
        return ""
    if isinstance(val, (int, np.integer)):
        return str(val)
    if isinstance(val, (float, np.floating)):
        if val.is_integer():
            return str(int(val))
        return str(val)
    s = str(val).strip()
    if s.lower() in ("nan", "none", "<na>"):
        return ""
    if s.endswith(".0") and s[:-2].replace("-", "").isdigit():
        return s[:-2]
    return s


def _clean_str_value(val) -> str:
    """清理文字欄位，完整保留原始文字，不截斷、不摘要、去除字面 nan/None"""
    if pd.isna(val) or val is None:
        return ""
    if isinstance(val, (int, np.integer)):
        return str(val)
    if isinstance(val, (float, np.floating)):
        if val.is_integer():
            return str(int(val))
        return str(val)
    s = str(val).strip()
    if s.lower() in ("nan", "none", "<na>"):
        return ""
    if s.endswith(".0") and s[:-2].replace("-", "").isdigit():
        return s[:-2]
    return s


def normalize_job_fields(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str], list[str]]:
    """
    依規格正規化原始職缺 9 大必要欄位，並檢驗同名與替代欄位衝突。
    回傳：
        (norm_df, conflicts, warnings)
    """
    conflicts = []
    warnings_list = []

    # 1. ID / 工作編號
    if "ID" not in df.columns and "工作編號" not in df.columns:
        raise ValueError("輸入職缺資料缺少 ID 識別欄位（'ID' 與 '工作編號' 均不存在），禁止自行編造職缺 ID！")

    if "ID" in df.columns and "工作編號" in df.columns:
        s_id = df["ID"].apply(_clean_str_preserve_leading_zero)
        s_job = df["工作編號"].apply(_clean_str_preserve_leading_zero)
        diff_mask = (s_id != "") & (s_job != "") & (s_id != s_job)
        diff_count = diff_mask.sum()
        if diff_count > 0:
            conflicts.append(f"欄位衝突：'ID' 與 '工作編號' 同時存在且有 {diff_count:,} 筆內容不一致，依規格優先採用 'ID'。")
        id_series = s_id.where(s_id != "", s_job)
    elif "ID" in df.columns:
        id_series = df["ID"].apply(_clean_str_preserve_leading_zero)
    else:
        id_series = df["工作編號"].apply(_clean_str_preserve_leading_zero)

    if (id_series == "").any():
        empty_indices = id_series[id_series == ""].index.tolist()
        raise ValueError(f"職缺資料第 {empty_indices[:5]} 列缺少 ID（'ID' 與 '工作編號' 均為空），禁止自行編造職缺 ID！")

    # 2. 104職位名稱 / 職位名稱
    if "104職位名稱" in df.columns and "職位名稱" in df.columns:
        s_p = df["104職位名稱"].apply(_clean_str_value)
        s_f = df["職位名稱"].apply(_clean_str_value)
        diff_mask = (s_p != "") & (s_f != "") & (s_p != s_f)
        diff_count = diff_mask.sum()
        if diff_count > 0:
            conflicts.append(f"欄位衝突：'104職位名稱' 與 '職位名稱' 同時存在且有 {diff_count:,} 筆內容不一致，依規格優先採用 '104職位名稱'。")
        title_series = s_p.where(s_p != "", s_f)
    elif "104職位名稱" in df.columns:
        title_series = df["104職位名稱"].apply(_clean_str_value)
    elif "職位名稱" in df.columns:
        title_series = df["職位名稱"].apply(_clean_str_value)
    else:
        warnings_list.append("非識別欄位缺少：缺少 '104職位名稱' 與 '職位名稱'，輸出欄位已填入空值。")
        title_series = pd.Series("", index=df.index, dtype=str)

    # 3. 104職位名稱碼 / 職位名稱碼 (保留前導零)
    if "104職位名稱碼" in df.columns and "職位名稱碼" in df.columns:
        s_p = df["104職位名稱碼"].apply(_clean_str_preserve_leading_zero)
        s_f = df["職位名稱碼"].apply(_clean_str_preserve_leading_zero)
        diff_mask = (s_p != "") & (s_f != "") & (s_p != s_f)
        diff_count = diff_mask.sum()
        if diff_count > 0:
            conflicts.append(f"欄位衝突：'104職位名稱碼' 與 '職位名稱碼' 同時存在且有 {diff_count:,} 筆內容不一致，依規格優先採用 '104職位名稱碼'。")
        title_code_series = s_p.where(s_p != "", s_f)
    elif "104職位名稱碼" in df.columns:
        title_code_series = df["104職位名稱碼"].apply(_clean_str_preserve_leading_zero)
    elif "職位名稱碼" in df.columns:
        title_code_series = df["職位名稱碼"].apply(_clean_str_preserve_leading_zero)
    else:
        warnings_list.append("非識別欄位缺少：缺少 '104職位名稱碼' 與 '職位名稱碼'，輸出欄位已填入空值。")
        title_code_series = pd.Series("", index=df.index, dtype=str)

    # 4. 電腦工具 / 擅長工具
    if "電腦工具" in df.columns and "擅長工具" in df.columns:
        s_p = df["電腦工具"].apply(_clean_str_value)
        s_f = df["擅長工具"].apply(_clean_str_value)
        diff_mask = (s_p != "") & (s_f != "") & (s_p != s_f)
        diff_count = diff_mask.sum()
        if diff_count > 0:
            conflicts.append(f"欄位衝突：'電腦工具' 與 '擅長工具' 同時存在且有 {diff_count:,} 筆內容不一致，依規格優先採用 '電腦工具'。")
        tool_series = s_p.where(s_p != "", s_f)
    elif "電腦工具" in df.columns:
        tool_series = df["電腦工具"].apply(_clean_str_value)
    elif "擅長工具" in df.columns:
        tool_series = df["擅長工具"].apply(_clean_str_value)
    else:
        warnings_list.append("非識別欄位缺少：缺少 '電腦工具' 與 '擅長工具'，輸出欄位已填入空值。")
        tool_series = pd.Series("", index=df.index, dtype=str)

    # 5. 其餘 5 個同名來源欄位 (資料月份, 刊登日期, 工作角色, 職位描述, 工作技能)
    def _extract_named(c):
        if c in df.columns:
            return df[c].apply(_clean_str_value)
        else:
            warnings_list.append(f"非識別欄位缺少：缺少 '{c}' 欄位，輸出欄位已填入空值。")
            return pd.Series("", index=df.index, dtype=str)

    month_series = _extract_named("資料月份")
    date_series = _extract_named("刊登日期")
    role_series = _extract_named("工作角色")
    desc_series = _extract_named("職位描述")
    skills_series = _extract_named("工作技能")

    norm_df = pd.DataFrame({
        "ID": id_series,
        "資料月份": month_series,
        "刊登日期": date_series,
        "工作角色": role_series,
        "104職位名稱": title_series,
        "104職位名稱碼": title_code_series,
        "職位描述": desc_series,
        "工作技能": skills_series,
        "電腦工具": tool_series,
    }, index=df.index)

    return norm_df, conflicts, warnings_list


def process_county(df: pd.DataFrame, automaton, county: str, month: str) -> pd.DataFrame:
    """
    處理單一縣市之職缺資料，回傳標準 25 欄位之 long_df。
    每列代表「一筆原始職缺 × 一個擷取到的技能」。
    直接於逐列處理時將原始 9 欄與 matched skill 組合，避免 merge 造成之多對多膨脹或錯配。
    """
    norm_df, conflicts, warns = normalize_job_fields(df)
    for c in conflicts:
        print(f"  ⚠️ {c}")
    for w in sorted(set(warns)):
        print(f"  ℹ️ {w}")

    skill_index = build_skill_id_index(automaton)
    records = []

    for i, (_, raw_row) in enumerate(norm_df.iterrows()):
        job_desc = raw_row["職位描述"]
        job_skills = raw_row["工作技能"]
        job_tools = raw_row["電腦工具"]
        job_title = raw_row["104職位名稱"]

        texts = [job_desc, job_skills, job_tools]
        matched = match_skills(texts, automaton)
        if not matched:
            matched = resolve_ambiguous_by_title(texts, job_title, automaton, skill_index)

        for s in matched:
            records.append({
                "_row_uid":           i,
                "Category_Name":      s.get("Category_Name", ""),
                "Subcategory_Name":   s.get("Subcategory_Name", ""),
                "ID":                 raw_row["ID"],
                "資料月份":             raw_row["資料月份"],
                "刊登日期":             raw_row["刊登日期"],
                "工作角色":             raw_row["工作角色"],
                "104職位名稱":          raw_row["104職位名稱"],
                "104職位名稱碼":         raw_row["104職位名稱碼"],
                "職位描述":             raw_row["職位描述"],
                "工作技能":             raw_row["工作技能"],
                "電腦工具":             raw_row["電腦工具"],
                "縣市":                 county,
                "月份":                 month,
                "SKILL_ID":           s.get("SKILL_ID", ""),
                "SKILL_NAME":         s.get("SKILL_NAME", ""),
                "SKILL_NAME_ZH":      s.get("SKILL_NAME_ZH", ""),
                "SKILL_TYPE":         s.get("SKILL_TYPE", ""),
                "Category_Code":      s.get("Category_Code", pd.NA),
                "Subcategory_Code":   s.get("Subcategory_Code", pd.NA),
                "Skill_group10_code": s.get("Skill_group10_code", pd.NA),
                "Skill_group10":      s.get("Skill_group10", ""),
                "Grouping_rule":      s.get("Grouping_rule", ""),
                "Grouping_status":    s.get("Grouping_status", ""),
                "MATCHED_FROM":       s.get("MATCHED_FROM", ""),
                "IS_SOFTWARE":        s.get("IS_SOFTWARE", False),
            })

        if (i + 1) % 5000 == 0:
            print(f"    {i+1:,} / {len(df):,} 筆...")

    if not records:
        empty_df = pd.DataFrame(columns=FINAL_COLUMNS)
        int_cols = ["Category_Code", "Subcategory_Code", "Skill_group10_code"]
        for c in int_cols:
            empty_df[c] = empty_df[c].astype("Int64")
        empty_df["IS_SOFTWARE"] = empty_df["IS_SOFTWARE"].astype(bool)
        for c in [c for c in FINAL_COLUMNS if c not in int_cols and c != "IS_SOFTWARE"]:
            empty_df[c] = empty_df[c].astype(str)
        return empty_df

    long_df = pd.DataFrame(records)

    # 確保 25 欄位完整齊全
    for col in FINAL_COLUMNS:
        if col not in long_df.columns:
            long_df[col] = pd.NA

    # 欄位型別與空值規範化：不得輸出字面 "nan" 或 "None"
    int_cols = ["Category_Code", "Subcategory_Code", "Skill_group10_code"]
    for c in int_cols:
        long_df[c] = pd.to_numeric(long_df[c], errors="coerce").astype("Int64")

    long_df["IS_SOFTWARE"] = long_df["IS_SOFTWARE"].fillna(False).astype(bool)

    str_cols = [c for c in FINAL_COLUMNS if c not in int_cols and c != "IS_SOFTWARE"]
    for c in str_cols:
        long_df[c] = long_df[c].fillna("").astype(str)
        long_df[c] = long_df[c].replace({"nan": "", "None": "", "<NA>": ""})

    return long_df[FINAL_COLUMNS]


def export_long_to_excel(df: pd.DataFrame, output_path: str):
    """
    匯出 long_df 至 Excel。
    若資料筆數超過 Excel 單一工作表上限 (1,048,575 筆)，
    自動分頁寫入 (skills_long_part1, skills_long_part2, ...)，不得截斷資料。
    """
    total_rows = len(df)
    if total_rows <= MAX_EXCEL_ROWS:
        df.to_excel(output_path, sheet_name="skills_long", index=False)
    else:
        num_sheets = (total_rows + MAX_EXCEL_ROWS - 1) // MAX_EXCEL_ROWS
        print(f"  ⚠️ 資料筆數 ({total_rows:,}) 超過 Excel 單工作表上限 ({MAX_EXCEL_ROWS:,})，分 {num_sheets} 頁輸出...")
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            for part_idx in range(num_sheets):
                start_i = part_idx * MAX_EXCEL_ROWS
                end_i = min(start_i + MAX_EXCEL_ROWS, total_rows)
                chunk = df.iloc[start_i:end_i]
                sheet_name = f"skills_long_part{part_idx + 1}"
                chunk.to_excel(writer, sheet_name=sheet_name, index=False)


def export_long_to_parquet(df: pd.DataFrame, output_path: str):
    """
    匯出 long_df 至 Parquet，維持 index=False。
    """
    df.to_parquet(output_path, index=False)


def skills_to_wide(long_df: pd.DataFrame, raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    選擇性寬表轉換：同步採用十大技能主分類匯總。
    """
    norm_df, _, _ = normalize_job_fields(raw_df)
    norm_df = norm_df.copy()
    norm_df["_row_uid"] = np.arange(len(norm_df))

    if len(long_df) == 0:
        agg_cols = ["ID", "技能數", "技能_中文"] + list(EXPECTED_GROUP10.values()) + ["未分類技能"]
        agg_df = pd.DataFrame(columns=agg_cols)
    else:
        def agg(group):
            result = {
                "技能數": len(group),
                "技能_中文": "｜".join(group["SKILL_NAME_ZH"].astype(str)),
            }
            for code, col_name in EXPECTED_GROUP10.items():
                skills_in_group = [
                    str(r["SKILL_NAME_ZH"])
                    for _, r in group.iterrows()
                    if pd.notna(r.get("Skill_group10_code")) and int(r["Skill_group10_code"]) == code
                ]
                result[col_name] = "｜".join(skills_in_group) if skills_in_group else ""

            unclassified = [
                str(r["SKILL_NAME_ZH"])
                for _, r in group.iterrows()
                if pd.isna(r.get("Skill_group10_code")) or r.get("Grouping_status") == "待人工分類"
            ]
            result["未分類技能"] = "｜".join(unclassified) if unclassified else ""
            return pd.Series(result)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if "_row_uid" in long_df.columns:
                agg_df = long_df.groupby("_row_uid").apply(agg, include_groups=False).reset_index()
                merged = norm_df.merge(agg_df, on="_row_uid", how="left")
                merged.drop(columns=["_row_uid"], inplace=True)
                return merged
            else:
                agg_df = long_df.groupby("ID").apply(agg, include_groups=False).reset_index()
                merged = norm_df.merge(agg_df, on="ID", how="left")
                merged.drop(columns=["_row_uid"], inplace=True)
                return merged

    merged = norm_df.merge(agg_df, on="ID", how="left")
    merged.drop(columns=["_row_uid"], inplace=True)
    return merged


def parse_args():
    parser = argparse.ArgumentParser(description="104 單檔技能擷取系統 (Long Format + 十大主分類)")
    parser.add_argument("input_file", nargs="?", default=None, help="輸入清理後 Excel 職缺檔案路徑")
    parser.add_argument("--input", "-i", dest="input_opt", default=None, help="輸入清理後 Excel 職缺檔案路徑")
    parser.add_argument("--lexicon", "-l", dest="lexicon_path", default=LEXICON_PATH, help="基底詞庫檔案路徑")
    parser.add_argument("--grouped-lexicon", "-g", dest="grouped_path", default=GROUPED_LEXICON_PATH, help="十大分類詞庫檔案路徑")
    parser.add_argument("--output-dir", "-o", dest="output_dir", default=OUTPUT_DIR, help="輸出目錄")
    parser.add_argument("--wide", "-w", action="store_true", default=EXPORT_WIDE, help="是否額外輸出 Wide 寬表格 (預設關閉)")
    return parser.parse_args()


def main():
    args = parse_args()
    input_path = args.input_file or args.input_opt or INPUT_PATH
    lexicon_path = args.lexicon_path
    grouped_path = args.grouped_path
    output_dir = args.output_dir
    export_wide = args.wide

    if not os.path.exists(input_path):
        print(f"⚠️ 找不到職缺輸入檔案：{input_path}")
        return

    county = extract_county(input_path)
    month = extract_month(input_path)
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60)
    print("104 技能擷取系統 — 單檔執行作業")
    print(f"  職缺輸入：{input_path}")
    print(f"  基底詞庫：{lexicon_path}")
    print(f"  分類詞庫：{grouped_path}")
    print(f"  輸出目錄：{output_dir}")
    print(f"  額外寬表：{'開啟' if export_wide else '關閉'}")
    print("=" * 60)

    print("\n[步驟 1/3] 讀取詞庫並建立 Aho-Corasick 自動機...")
    t0 = time.time()
    automaton = load_automaton(lexicon_path, grouped_path)
    print(f"  自動機建立完成，耗時 {time.time()-t0:.1f}s\n")

    print(f"[步驟 2/3] 讀取職缺資料：{input_path}")
    read_dtype = {
        "ID": str,
        "工作編號": str,
        "104職位名稱碼": str,
        "職位名稱碼": str,
        "資料月份": str,
        "刊登日期": str,
    }
    if input_path.endswith(".parquet"):
        job_df = pd.read_parquet(input_path)
    else:
        job_df = pd.read_excel(input_path, dtype=read_dtype)
    total_jobs = len(job_df)
    print(f"  讀取完成：共 {total_jobs:,} 筆職缺，縣市={county}，月份={month}\n")

    print("[步驟 3/3] 執行技能比對與分類對應...")
    t0 = time.time()
    long_df = process_county(job_df, automaton, county, month)
    elapsed = time.time() - t0

    matched_jobs = long_df["ID"].nunique() if len(long_df) > 0 else 0
    unmatched_jobs = total_jobs - matched_jobs
    avg_skills = len(long_df) / total_jobs if total_jobs > 0 else 0

    print("\n" + "=" * 60)
    print("【擷取統計摘要】")
    print(f"  總職缺數：    {total_jobs:,} 筆")
    print(f"  命中職缺數：  {matched_jobs:,} 筆 ({matched_jobs/total_jobs*100:.1f}%)" if total_jobs > 0 else "0 筆")
    print(f"  未命中職缺數：{unmatched_jobs:,} 筆 ({unmatched_jobs/total_jobs*100:.1f}%)" if total_jobs > 0 else "0 筆")
    print(f"  總技能記錄數：{len(long_df):,} 筆 (平均 {avg_skills:.2f} 個技能/職缺)")
    print(f"  比對耗時：    {elapsed:.1f}s")

    if len(long_df) > 0:
        print("\n【分類狀態分佈】")
        for st, count in long_df["Grouping_status"].value_counts().items():
            print(f"  {st}: {count:,} 筆 ({count/len(long_df)*100:.1f}%)")

        print("\n【十大技能主分類分佈】")
        group_counts = long_df["Skill_group10"].replace({"": "未分類"}).value_counts()
        for grp, count in group_counts.items():
            print(f"  {grp}: {count:,} 筆")
    else:
        print("  ⚠️ 全檔無任何技能命中，已產生標準欄位之空表。")

    print("=" * 60)

    # 主要輸出：Long Format (Excel & Parquet)
    long_xlsx_path = os.path.join(output_dir, f"skills_{county}_{month}_long.xlsx")
    long_parquet_path = os.path.join(output_dir, f"skills_{county}_{month}_long.parquet")

    print(f"\n匯出主要 Long format 檔案...")
    export_long_to_excel(long_df, long_xlsx_path)
    print(f"  ✓ Excel 匯出完成：  {long_xlsx_path}")

    export_long_to_parquet(long_df, long_parquet_path)
    print(f"  ✓ Parquet 匯出完成：{long_parquet_path}")

    # 選擇性輸出：Wide Format (Excel)
    if export_wide:
        print(f"\n匯出選擇性 Wide format 檔案 (同步改用十大分類)...")
        wide_df = skills_to_wide(long_df, job_df)
        wide_xlsx_path = os.path.join(output_dir, f"skills_{county}_{month}_wide.xlsx")
        wide_df.to_excel(wide_xlsx_path, index=False)
        print(f"  ✓ Wide Excel 匯出完成：{wide_xlsx_path}")

    print("\n全部處理作業已完成！")


if __name__ == "__main__":
    main()

