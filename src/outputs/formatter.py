"""輸出格式化模組：負責將技能清單轉為 9 大類寬表格 (Wide DataFrame) 與 JSONL 格式。"""

import warnings
from typing import Dict, Optional
import pandas as pd
import yaml

_DEFAULT_CAT9_ZH = {
    "Cognitive Skills": "認知技能",
    "Social Skills": "社交技能",
    "Character Skills": "特質技能",
    "Financial Skills": "財務技能",
    "Management Skills": "管理技能",
    "General Digital Skills": "數位技能",
    "Technical Support Skills": "技術技能",
    "Advanced Computer Skills": "電腦技能",
    "AI & Big Data Skills": "AI技能",
    "Unclassified": "其他技能",
}


def load_cat9_mapping(rules_path: str = "configs/rules.yaml") -> Dict[str, str]:
    """從 rules.yaml 載入 9 大分類中文對照表。"""
    try:
        with open(rules_path, "r", encoding="utf-8") as f:
            rules = yaml.safe_load(f)
            return rules.get("cat9_zh_mapping", _DEFAULT_CAT9_ZH)
    except Exception:
        return _DEFAULT_CAT9_ZH


def skills_to_wide(
    long_df: pd.DataFrame,
    raw_df: pd.DataFrame,
    cat9_mapping: Optional[Dict[str, str]] = None,
) -> pd.DataFrame:
    """將 Long Format 的技能記錄整合回原始職缺資料，產出寬表格。"""
    mapping = cat9_mapping if cat9_mapping is not None else _DEFAULT_CAT9_ZH

    raw_df = raw_df.copy()
    def find_col(candidates, default=""):
        for c in candidates:
            if c in raw_df.columns:
                return c
        return default

    id_col = find_col(["工作編號", "ID", "id"], default="id")
    if id_col not in raw_df.columns:
        raw_df["ID"] = [f"JOB_{i}" for i in range(len(raw_df))]
    else:
        raw_df["ID"] = raw_df[id_col].astype(str)

    tool_col = find_col(["擅長工具", "電腦工具", "tools"], default="tools")
    title_col = find_col(["職位名稱", "104職位名稱", "job_title"], default="job_title")
    title_code_col = find_col(["職位名稱碼", "104職位名稱碼", "job_code"], default="job_code")
    desc_col = find_col(["職位描述", "job_desc"], default="job_desc")
    skill_col = find_col(["工作技能", "job_skills"], default="job_skills")

    if long_df.empty:
        # 空資料防呆
        empty_cols = ["ID", "技能數", "技能_中文"] + list(mapping.values())
        agg_df = pd.DataFrame(columns=empty_cols)
    else:
        # 快速字典聚合（替代原本昂貴的 groupby.apply + 巢狀 iterrows）
        grouped_skills: Dict[str, List[str]] = {}
        grouped_cat_skills: Dict[str, Dict[str, List[str]]] = {
            zh_col: {} for zh_col in mapping.values()
        }

        id_idx = long_df.columns.get_loc("ID")
        zh_idx = long_df.columns.get_loc("SKILL_NAME_ZH")
        cat_idx = long_df.columns.get_loc("SKILL_CAT9") if "SKILL_CAT9" in long_df.columns else -1

        for row in long_df.itertuples(index=False):
            jid = str(row[id_idx])
            zh = str(row[zh_idx]) if pd.notna(row[zh_idx]) else ""
            cat = str(row[cat_idx]) if cat_idx >= 0 and pd.notna(row[cat_idx]) else "Unclassified"
            zh_col = mapping.get(cat)

            if jid not in grouped_skills:
                grouped_skills[jid] = [zh]
            else:
                grouped_skills[jid].append(zh)

            if zh_col and zh_col in grouped_cat_skills:
                cat_dict = grouped_cat_skills[zh_col]
                if jid not in cat_dict:
                    cat_dict[jid] = [zh]
                else:
                    cat_dict[jid].append(zh)

        sorted_ids = sorted(grouped_skills.keys())
        agg_data: Dict[str, Any] = {
            "ID": sorted_ids,
            "技能數": [len(grouped_skills[jid]) for jid in sorted_ids],
            "技能_中文": ["｜".join(grouped_skills[jid]) for jid in sorted_ids],
        }
        for zh_col in mapping.values():
            cat_dict = grouped_cat_skills[zh_col]
            agg_data[zh_col] = ["｜".join(cat_dict.get(jid, [])) for jid in sorted_ids]

        agg_df = pd.DataFrame(agg_data)

    desc_cols = [
        "ID",
        "資料月份",
        "刊登日期",
        "工作角色",
        title_col,
        title_code_col,
        desc_col,
        skill_col,
        tool_col,
    ]
    desc_cols = [c for c in desc_cols if c in raw_df.columns]
    desc = raw_df[desc_cols]
    return desc.merge(agg_df, on="ID", how="left")
