#!/usr/bin/env python3
"""Task 7: 語意假陰性召回評估與消融測試腳本 (Semantic Recovery Evaluation & Ablation)。

獨立衡量並對比：
1. AC Baseline Recall vs. AC + Semantic Recovery Recall
2. 成功召回之 AC 假陰性數量 (Recovered FNs)
3. 不確定案型數量 (Uncertain Cases)
4. 被拒絕之語意對齊數量 (Rejected Mappings / NO_MATCH)
5. Precision, Recall, Micro F1, Macro F1
6. LLM 呼叫次數、Token 消耗量、估算 API 費用 ($0.00)
7. 產出 Human Review Table 與 outputs/keyword_candidates.csv
"""

import os
import sys
import json
import logging
from typing import List, Dict, Any
import pandas as pd

# 加入專案根目錄至 sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.hybrid_pipeline import HybridJobSkillPipeline
from src.pipeline import JobSkillPipeline
from src.grounding.schemas import DecisionType, FNRecoveryResult
from src.grounding.review_table import build_review_table, format_markdown_review_table
from src.grounding.expansion import KeywordCandidateManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("semantic_recovery_eval")


def load_benchmark_jobs(benchmark_path: str) -> List[Dict[str, Any]]:
    """讀取 Benchmark 職缺並附加上使用者提出之硬體研發工程師測試案例。"""
    jobs = []
    if os.path.exists(benchmark_path):
        with open(benchmark_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    jobs.append(json.loads(line.strip()))

    # 加入 Prompt 中的典型硬體研發工程師案例
    jobs.append({
        "id": "PROMPT_HARDWARE_ENG",
        "county": "新竹市",
        "job_title": "硬體研發工程師",
        "job_desc": "【工作內容】\n1. Server Design\n2. Board debug\n3. BOM creation\n4. Documents creation\n5. Work with team for project development",
        "tools": "",
        "job_skills": "",
        "gold_skill_ids": ["KS121X369RKT17LSJNZX", "KS120000000000000005"],  # 電路設計/硬體, 溝通
        "gold_skill_names_zh": ["電路設計", "溝通"],
        "notes": "Prompt Example: BOM 命中物料清單，其餘短語進行語意對齊診斷",
    })
    return jobs


def run_evaluation(
    benchmark_path: str = "data/gold_labels/sample_benchmark.jsonl",
    lexicon_path: str = "lexicon/sample/mini_skill_lexicon.csv",
    output_json: str = "outputs/semantic_recovery_evaluation.json",
    output_review_csv: str = "outputs/human_review_table.csv",
    output_kw_csv: str = "outputs/keyword_candidates.csv",
):
    logger.info("=" * 70)
    logger.info("啟動 Task 7 語意假陰性召回評估流程")
    logger.info("=" * 70)

    jobs = load_benchmark_jobs(benchmark_path)
    logger.info(f"共載入 {len(jobs)} 筆評估職缺 (含 Gold Benchmark 與 Prompt 測試案例)")

    # 1. 初始化 AC Baseline 與 Hybrid Pipeline
    ac_pipeline = JobSkillPipeline(lexicon_path=lexicon_path)
    hybrid_pipeline = HybridJobSkillPipeline(
        lexicon_path=lexicon_path,
        verifier_provider="mock",
        grounder_provider="mock",
        enable_fn_recovery=True,
    )

    all_fn_results: List[FNRecoveryResult] = []
    ac_gold_tp = 0
    ac_gold_fp = 0
    ac_gold_fn = 0

    hybrid_gold_tp = 0
    hybrid_gold_fp = 0
    hybrid_gold_fn = 0

    total_fn_recovered = 0
    total_uncertain = 0
    total_rejected = 0

    for job in jobs:
        j_id = job.get("id", "")
        title = job.get("job_title", "")
        desc = job.get("job_desc", "")
        tools = job.get("tools", "")
        skills = job.get("job_skills", "")
        gold_ids = set(job.get("gold_skill_ids", []))

        # --- A. 執行 AC Baseline ---
        ac_cands = ac_pipeline.extract_job_skills(
            job_desc=desc, job_title=title, tools=tools, job_skills=skills
        )
        ac_pred_ids = set(c.skill_id for c in ac_cands)

        if gold_ids:
            ac_tp = len(ac_pred_ids & gold_ids)
            ac_fp = len(ac_pred_ids - gold_ids)
            ac_fn = len(gold_ids - ac_pred_ids)
            ac_gold_tp += ac_tp
            ac_gold_fp += ac_fp
            ac_gold_fn += ac_fn

        # --- B. 執行 Hybrid Pipeline (含語意召回) ---
        final_skills, routing_res, _ = hybrid_pipeline.extract_job_skills(
            job_id=j_id,
            job_title=title,
            job_desc=desc,
            tools=tools,
            job_skills=skills,
        )
        hybrid_pred_ids = set(s.skill_id for s in final_skills)

        if gold_ids:
            h_tp = len(hybrid_pred_ids & gold_ids)
            h_fp = len(hybrid_pred_ids - gold_ids)
            h_fn = len(gold_ids - hybrid_pred_ids)
            hybrid_gold_tp += h_tp
            hybrid_gold_fp += h_fp
            hybrid_gold_fn += h_fn

        # 收集語意召回診斷結果
        fn_res = routing_res.fn_recovery_result
        if not fn_res:
            # 針對評估亦執行完整診斷
            fn_res = hybrid_pipeline.diagnose_job_description(
                job_title=title, job_desc=desc, tools=tools, job_skills=skills, job_id=j_id
            )

        all_fn_results.append(fn_res)

        # 統計召回、不確定與拒絕數
        for s_item in fn_res.semantic_items:
            if s_item.decision == DecisionType.MATCH:
                total_fn_recovered += 1
            elif s_item.decision == DecisionType.UNCERTAIN:
                total_uncertain += 1
            elif s_item.decision == DecisionType.NO_MATCH:
                total_rejected += 1

    # 計算統計指標
    ac_p = (ac_gold_tp / (ac_gold_tp + ac_gold_fp)) if (ac_gold_tp + ac_gold_fp) > 0 else 0.0
    ac_r = (ac_gold_tp / (ac_gold_tp + ac_gold_fn)) if (ac_gold_tp + ac_gold_fn) > 0 else 0.0
    ac_f1 = (2 * ac_p * ac_r / (ac_p + ac_r)) if (ac_p + ac_r) > 0 else 0.0

    hy_p = (hybrid_gold_tp / (hybrid_gold_tp + hybrid_gold_fp)) if (hybrid_gold_tp + hybrid_gold_fp) > 0 else 0.0
    hy_r = (hybrid_gold_tp / (hybrid_gold_tp + hybrid_gold_fn)) if (hybrid_gold_tp + hybrid_gold_fn) > 0 else 0.0
    hy_f1 = (2 * hy_p * hy_r / (hy_p + hy_r)) if (hy_p + hy_r) > 0 else 0.0

    # 產出審核表
    review_df = hybrid_pipeline.generate_review_table(all_fn_results)
    review_df.to_csv(output_review_csv, index=False, encoding="utf-8-sig")

    # 產出關鍵字候選
    kw_df = hybrid_pipeline.export_keyword_candidates(all_fn_results, output_path=output_kw_csv)

    results_summary = {
        "ac_baseline": {
            "precision": round(ac_p, 4),
            "recall": round(ac_r, 4),
            "f1": round(ac_f1, 4),
            "tp": ac_gold_tp,
            "fp": ac_gold_fp,
            "fn": ac_gold_fn,
        },
        "ac_plus_semantic_recovery": {
            "precision": round(hy_p, 4),
            "recall": round(hy_r, 4),
            "f1": round(hy_f1, 4),
            "tp": hybrid_gold_tp,
            "fp": hybrid_gold_fp,
            "fn": hybrid_gold_fn,
        },
        "semantic_recovery_stats": {
            "recovered_fn_count": total_fn_recovered,
            "uncertain_count": total_uncertain,
            "rejected_count": total_rejected,
            "llm_calls": 0,
            "token_usage": 0,
            "estimated_api_cost_usd": 0.0,
        },
    }

    os.makedirs(os.path.dirname(output_json), exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(results_summary, f, indent=2, ensure_ascii=False)

    # 印出報告
    print("\n" + "=" * 70)
    print("📊 評估對比報告 (Task 7 Evaluation Results)")
    print("=" * 70)
    print(f"1. AC Baseline Recall:               {ac_r * 100:.2f}% (P: {ac_p * 100:.2f}%, F1: {ac_f1 * 100:.2f}%)")
    print(f"2. AC + Semantic Recovery Recall:    {hy_r * 100:.2f}% (P: {hy_p * 100:.2f}%, F1: {hy_f1 * 100:.2f}%)")
    print("-" * 70)
    print(f"• 成功召回之 AC 假陰性 (Recovered FNs):   {total_fn_recovered} 筆")
    print(f"• 標記為不確定案型 (Uncertain Cases):    {total_uncertain} 筆")
    print(f"• 安全拒絕之語意對齊 (Rejected Mappings): {total_rejected} 筆")
    print("-" * 70)
    print(f"• LLM / Verifier 調用次數:               0 次 (全本機確定性檢索)")
    print(f"• Token 消耗量:                         0 tokens")
    print(f"• 估算 API 費用:                        $0.00 USD (遵守零付費約束)")
    print("=" * 70)
    print("\n🔍 人工審核總表預覽 (Human Review Table - Top 10):")
    print(format_markdown_review_table(review_df, max_rows=10))
    print("\n✅ 檔案輸出位置：")
    print(f"- 審核總表: {output_review_csv}")
    print(f"- 關鍵字候選: {output_kw_csv}")
    print(f"- 評估 JSON: {output_json}\n")


if __name__ == "__main__":
    run_evaluation()
