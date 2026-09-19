"""端到端比對管線：整合詞庫載入、AC 匹配與結果匯出。"""

import logging
import time
from typing import Optional, Tuple
import pandas as pd

from src.lexicon.loader import LexiconLoader
from src.ac_matcher.engine import ACMatcher
from src.preprocessing.normalizer import clean_text, extract_county, extract_month
from src.outputs.formatter import skills_to_wide, load_cat9_mapping

logger = logging.getLogger(__name__)


class JobSkillPipeline:
    """職缺技能擷取管線控制器。"""

    def __init__(
        self,
        lexicon_path: str = "lexicon/sample/mini_skill_lexicon.csv",
        rules_path: str = "configs/rules.yaml",
        synonyms_path: str = "configs/synonyms.yaml",
        enable_rules: bool = True,
    ):
        self.lexicon_path = lexicon_path
        self.rules_path = rules_path
        self.synonyms_path = synonyms_path
        self.enable_rules = enable_rules

        logger.info(f"初始化 JobSkillPipeline (詞庫: {lexicon_path}, 規則: {enable_rules})...")
        t0 = time.time()
        self.loader = LexiconLoader(rules_path=rules_path, synonyms_path=synonyms_path)
        term_to_entries, skill_index = self.loader.load_lexicon(lexicon_path)
        self.matcher = ACMatcher.build_from_lexicon(
            term_to_entries=term_to_entries,
            skill_index=skill_index,
            rules_path=rules_path,
        )
        self.cat9_mapping = load_cat9_mapping(rules_path)
        logger.info(f"Pipeline 初始化完成，耗時 {time.time() - t0:.2f}s")

    def extract_job_skills(
        self,
        job_id: str = "",
        job_title: str = "",
        job_desc: str = "",
        tools: str = "",
        job_skills: str = "",
    ):
        """對單一職缺執行候選技能比對。"""
        texts = [clean_text(job_desc), clean_text(job_skills), clean_text(tools)]
        return self.matcher.extract_job_skills(
            texts, job_title=clean_text(job_title), enable_rules=self.enable_rules
        )

    def process_dataframe(
        self, df: pd.DataFrame, county: str = "unknown", month: str = "unknown"
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """處理單一 DataFrame，回傳 (long_df, wide_df)。"""
        # 彈性支援中文欄位與英文欄位
        def find_col(candidates, default=""):
            for c in candidates:
                if c in df.columns:
                    return c
            return default

        id_col = find_col(["工作編號", "ID", "id"], default="id")
        tool_col = find_col(["擅長工具", "電腦工具", "tools"], default="tools")
        title_col = find_col(["職位名稱", "104職位名稱", "job_title"], default="job_title")
        desc_col = find_col(["職位描述", "job_desc"], default="job_desc")
        skill_col = find_col(["工作技能", "job_skills"], default="job_skills")

        records = []
        for i, row in df.iterrows():
            job_id = str(row.get(id_col, f"JOB_{i}"))
            texts = [
                clean_text(row.get(desc_col, "")),
                clean_text(row.get(skill_col, "")),
                clean_text(row.get(tool_col, "")),
            ]
            job_title = clean_text(row.get(title_col, ""))
            matched = self.matcher.extract_job_skills(texts, job_title=job_title)

            for cand in matched:
                cand_dict = cand.to_dict()
                records.append({"ID": job_id, "縣市": county, "月份": month, **cand_dict})

        long_df = pd.DataFrame(records)
        wide_df = skills_to_wide(long_df, df, cat9_mapping=self.cat9_mapping)
        return long_df, wide_df

    def process_file(
        self, input_path: str, output_path: Optional[str] = None
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """處理單一檔案 (CSV 或 Excel)，並選擇性匯出寬表格。"""
        county = extract_county(input_path)
        month = extract_month(input_path)

        logger.info(f"讀取輸入檔案：{input_path}")
        if input_path.endswith(".csv"):
            df = pd.read_csv(input_path)
        elif input_path.endswith(".jsonl"):
            df = pd.read_json(input_path, lines=True)
        else:
            df = pd.read_excel(input_path)

        long_df, wide_df = self.process_dataframe(df, county=county, month=month)

        if output_path:
            if output_path.endswith(".csv"):
                wide_df.to_csv(output_path, index=False)
            else:
                wide_df.to_excel(output_path, index=False)
            logger.info(f"寬表格已輸出至：{output_path}")

        return long_df, wide_df
