"""人工審核總表產出模組 (Task 5: Human Review Output Table)。

將假陰性語意診斷結果格式化為結構化審核表：
| job_title | original_phrase | AC_result | candidate_skill | Skill_ID | evidence | confidence | decision |
"""

import logging
from typing import List, Dict, Any, Optional
import pandas as pd

from src.grounding.schemas import SemanticRecoveryItem, DecisionType

logger = logging.getLogger(__name__)


def build_review_table(
    records: List[Dict[str, Any]],
) -> pd.DataFrame:
    """從審核紀錄字典清單構建標準 DataFrame。
    
    每個紀錄包含:
    - job_title: str
    - item: SemanticRecoveryItem 或相容字典
    """
    rows = []
    for r in records:
        job_title = r.get("job_title", "")
        item = r.get("item")
        if isinstance(item, SemanticRecoveryItem):
            cand_skill = (
                item.selected_skill_name_zh
                if item.selected_skill_name_zh
                else (item.candidate_skill_names[0] if item.candidate_skill_names else "無相符候選")
            )
            skill_id = (
                item.selected_skill_id
                if item.selected_skill_id
                else (item.candidate_skill_ids[0] if item.candidate_skill_ids else "None")
            )
            rows.append({
                "job_title": job_title,
                "original_phrase": item.original_phrase,
                "AC_result": item.ac_result,
                "candidate_skill": cand_skill,
                "Skill_ID": skill_id,
                "evidence": item.evidence,
                "confidence": item.confidence,
                "decision": item.decision.value if hasattr(item.decision, "value") else str(item.decision),
            })
        elif isinstance(item, dict):
            rows.append({
                "job_title": job_title,
                "original_phrase": item.get("original_phrase", ""),
                "AC_result": item.get("AC_result", "None"),
                "candidate_skill": item.get("candidate_skill", ""),
                "Skill_ID": item.get("Skill_ID", "None"),
                "evidence": item.get("evidence", ""),
                "confidence": item.get("confidence", 0.0),
                "decision": item.get("decision", "NO_MATCH"),
            })

    columns = [
        "job_title",
        "original_phrase",
        "AC_result",
        "candidate_skill",
        "Skill_ID",
        "evidence",
        "confidence",
        "decision",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows)[columns]


def format_markdown_review_table(df: pd.DataFrame, max_rows: int = 50) -> str:
    """將審核表轉換為 GitHub Markdown 表格字串 (純 Python 實作，不依賴外部 tabulate)。"""
    if df.empty:
        return "無待審核之語意候選短語。"
    
    sub_df = df.head(max_rows)
    headers = [str(c) for c in sub_df.columns]
    
    # 建立 Markdown 表頭
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    
    # 建立每一列資料
    for _, row in sub_df.iterrows():
        row_vals = [str(row[c]).replace("\n", " ").replace("|", "\\|") for c in sub_df.columns]
        lines.append("| " + " | ".join(row_vals) + " |")
        
    return "\n".join(lines)
