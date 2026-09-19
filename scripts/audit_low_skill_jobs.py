#!/usr/bin/env python3
"""低技能數職缺專用審計腳本 (Task 12: Low-Skill Audit CLI)。

針對 skill_count <= 1 之職缺執行殘差語意分析、詞庫約束檢索與上下文驗證，
並產出結構化審計報告 outputs/low_skill_audit.xlsx。
"""

import os
import sys
import argparse
import logging
from typing import List, Dict, Any
import pandas as pd

# 加入專案根目錄至 sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.lexicon.loader import LexiconLoader
from src.ac_matcher.engine import ACMatcher
from src.retrieval.hybrid import HybridRetriever
from src.recovery.semantic_recovery import ResidualSemanticRecoveryEngine
from src.verifier.semantic_verifier import SemanticVerifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("audit_low_skill")


def parse_args():
    parser = argparse.ArgumentParser(description="執行低技能數 (skill_count <= 1) 職缺審計。")
    parser.add_argument(
        "-i",
        "--input",
        type=str,
        default="AC 後檔案/skills_南投縣_202608_wide.xlsx",
        help="待審計之寬表格或清洗後職缺檔案",
    )
    parser.add_argument(
        "-l",
        "--lexicon",
        type=str,
        default="lexicon/sample/mini_skill_lexicon.csv",
        help="技能詞庫路徑",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="outputs/low_skill_audit.xlsx",
        help="審計輸出 Excel 檔案路徑",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="審計職缺筆數上限 (預設 50 筆，設為 0 則處理全部)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if not os.path.exists(args.input):
        logger.error(f"找不到輸入檔案：{args.input}")
        sys.exit(1)

    logger.info("=" * 70)
    logger.info(f"啟動低技能數審計模式 (輸入: {args.input}, 詞庫: {args.lexicon})")
    logger.info("=" * 70)

    # 1. 載入詞庫與建立引擎
    loader = LexiconLoader()
    term_to_entries, skill_index = loader.load_lexicon(args.lexicon)
    matcher = ACMatcher.build_from_lexicon(term_to_entries, skill_index)
    retriever = HybridRetriever(skill_id_index=skill_index)
    verifier = SemanticVerifier(skill_id_index=skill_index)
    recovery_engine = ResidualSemanticRecoveryEngine(
        skill_id_index=skill_index,
        hybrid_retriever=retriever,
        verifier=verifier,
    )

    # 2. 讀取輸入資料並篩選 skill_count <= 1
    df = pd.read_excel(args.input)
    logger.info(f"成功載入資料表，總筆數：{len(df)}")

    # 判斷技能數欄位
    count_col = "技能數" if "技能數" in df.columns else None
    if count_col:
        low_skill_df = df[df[count_col] <= 1]
    else:
        logger.info("未偵測到 '技能數' 欄位，將直接對所有資料進行殘差掃描")
        low_skill_df = df

    if args.limit > 0:
        low_skill_df = low_skill_df.head(args.limit)

    logger.info(f"本批次預計審計低技能數職缺：{len(low_skill_df)} 筆")

    audit_rows: List[Dict[str, Any]] = []

    for idx, row in low_skill_df.iterrows():
        job_id = str(row.get("ID", row.get("工作編號", f"JOB_{idx}")))
        title = str(row.get("104職位名稱", row.get("職位名稱", "")))
        desc = str(row.get("職位描述", ""))
        tools = str(row.get("電腦工具", row.get("擅長工具", "")))
        skills = str(row.get("工作技能", ""))
        orig_skills = str(row.get("技能_中文", row.get("技能", "")))
        orig_count = int(row.get("技能數", 1)) if count_col else 1

        # 執行 AC 匹配
        ac_matches = matcher.extract_job_skills([desc, skills, tools], job_title=title)

        # 執行殘差語意召回
        res_result = recovery_engine.recover_residuals(
            job_id=job_id,
            job_title=title,
            job_desc=desc,
            ac_matches=ac_matches,
            tools=tools,
            job_skills=skills,
        )

        for v_out in res_result.verification_outputs:
            audit_rows.append({
                "job_id": job_id,
                "job_title": title,
                "job_description": desc[:300] + "..." if len(desc) > 300 else desc,
                "original_skill_count": orig_count,
                "original_skills": orig_skills,
                "source_phrase": v_out.source_phrase,
                "candidate_skill_id": v_out.skill_id or "None",
                "candidate_skill_name": v_out.skill_name or "None",
                "retrieval_score": round(v_out.confidence, 4),
                "verification_confidence": round(v_out.confidence, 4),
                "decision": v_out.decision.value if hasattr(v_out.decision, "value") else str(v_out.decision),
                "evidence": v_out.evidence,
            })

    # 3. 輸出審計結果 Excel
    audit_df = pd.DataFrame(audit_rows)
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    audit_df.to_excel(args.output, index=False, engine="openpyxl")

    logger.info("=" * 70)
    logger.info(f"✅ 審計完成！共產出 {len(audit_df)} 項殘差單元分析紀錄至：{args.output}")
    if not audit_df.empty:
        logger.info(f"決策分佈：\n{audit_df['decision'].value_counts().to_string()}")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
