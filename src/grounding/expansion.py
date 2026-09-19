"""關鍵字擴充候選輸出模組 (Task 6: Keyword Expansion Candidate Exporter)。

當語意匹配以高置信度確認 (MATCH) 時，絕不自動修改生產詞庫，
而是安全寫入 outputs/keyword_candidates.csv 供領域專家人工複核。

欄位規格：
Skill_ID,Skill_Name_ZH,new_keyword,source_phrase,job_title,confidence,discovery_method
"""

import os
import logging
from typing import List, Dict, Any, Optional
import pandas as pd

from src.grounding.schemas import SemanticRecoveryItem, DecisionType

logger = logging.getLogger(__name__)

COLUMNS = [
    "Skill_ID",
    "Skill_Name_ZH",
    "new_keyword",
    "source_phrase",
    "job_title",
    "confidence",
    "discovery_method",
]


class KeywordCandidateManager:
    """關鍵字擴充候選管理器。"""

    def __init__(self, output_path: str = "outputs/keyword_candidates.csv"):
        self.output_path = output_path
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

    def export_candidates(
        self,
        records: List[Dict[str, Any]],
        confidence_threshold: float = 0.80,
        append: bool = True,
    ) -> pd.DataFrame:
        """從診斷紀錄中篩選高置信度 MATCH 項目並輸出至 CSV。
        
        Args:
            records: 包含 job_title 與 item (SemanticRecoveryItem) 的紀錄清單
            confidence_threshold: 最低置信度門檻 (預設 0.80)
            append: 是否追加至現有檔案（若為 False 則覆寫）
            
        Returns:
            輸出的 candidate DataFrame
        """
        new_rows = []
        for r in records:
            job_title = r.get("job_title", "")
            item = r.get("item")
            method = r.get("discovery_method", "SEMANTIC_RECOVERY_HYBRID")

            if isinstance(item, SemanticRecoveryItem):
                if item.decision == DecisionType.MATCH and item.confidence >= confidence_threshold:
                    if item.selected_skill_id and item.selected_skill_name_zh:
                        new_rows.append({
                            "Skill_ID": item.selected_skill_id,
                            "Skill_Name_ZH": item.selected_skill_name_zh,
                            "new_keyword": item.original_phrase,
                            "source_phrase": item.original_phrase,
                            "job_title": job_title,
                            "confidence": item.confidence,
                            "discovery_method": method,
                        })

        df_new = pd.DataFrame(new_rows, columns=COLUMNS)

        if os.path.exists(self.output_path) and append:
            try:
                df_existing = pd.read_csv(self.output_path)
                df_combined = pd.concat([df_existing, df_new], ignore_index=True)
                # 依 (Skill_ID, new_keyword) 去重，保留最新/最高信心度
                df_combined = df_combined.drop_duplicates(
                    subset=["Skill_ID", "new_keyword"], keep="last"
                )
            except Exception as e:
                logger.warning(f"讀取既有候選檔失敗 ({e})，重新建立")
                df_combined = df_new
        else:
            df_combined = df_new.drop_duplicates(subset=["Skill_ID", "new_keyword"], keep="last")

        df_combined.to_csv(self.output_path, index=False, encoding="utf-8-sig")
        logger.info(f"關鍵字擴充候選清單已更新：共 {len(df_combined)} 筆至 {self.output_path}")
        return df_combined
