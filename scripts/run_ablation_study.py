"""四大消融實驗與多維度誤差切片自動化評估腳本 (Ablation Study Runner)。

對照評估 4 大系統變體：
1. Variant 1: Pure AC Baseline (無規則、無 LLM)
2. Variant 2: Refactored AC + Rule Engine (Phase 1 模組化規則，無 LLM)
3. Variant 3: AC + Risk-based LLM Verification (Phase 4 混合架構，無 FN 召回)
4. Variant 4: Full Hybrid System (Phase 5 完整系統，含 Two-Stage Concept Grounding 與 FN 召回)

輸出結構化消融矩陣至 outputs/ablation_study_results.json 並在終端印出對比表格。
"""

import os
import sys
import json
import argparse
import logging
from typing import Dict, Any, List

from src.pipeline import JobSkillPipeline
from src.hybrid_pipeline import HybridJobSkillPipeline
from src.evaluation.evaluator import PipelineEvaluator, EvaluationReport

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ablation_study")


def parse_args():
    parser = argparse.ArgumentParser(description="執行四大消融實驗與多維度切片評估")
    parser.add_argument(
        "-b",
        "--benchmark",
        type=str,
        default="data/gold_labels/sample_benchmark.jsonl",
        help="黃金標準資料集路徑",
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
        default="outputs/ablation_study_results.json",
        help="輸出 JSON 結果路徑",
    )
    return parser.parse_args()


def run_ablation_study(benchmark_path: str, lexicon_path: str) -> Dict[str, Any]:
    """依序執行四大變體並彙整指標。"""
    evaluator = PipelineEvaluator(benchmark_path=benchmark_path)

    variants = [
        {
            "id": "Variant_1",
            "name": "Pure AC Baseline (No Rules, No LLM)",
            "description": "純 Aho-Corasick 多模式匹配，關閉列舉展開、中英詞界、長詞抑制與職稱消歧",
            "pipeline": JobSkillPipeline(lexicon_path=lexicon_path, enable_rules=False),
        },
        {
            "id": "Variant_2",
            "name": "AC + Rule Engine (Phase 1 Baseline)",
            "description": "AC 配合 Phase 1 完整規則模組（列舉展開、字幹同義詞、最長匹配抑制與文意消歧）",
            "pipeline": JobSkillPipeline(lexicon_path=lexicon_path, enable_rules=True),
        },
        {
            "id": "Variant_3",
            "name": "AC + Risk-based LLM Verifier (Phase 4)",
            "description": "加入三軌風險分流與 MockLLM 上下文驗證層，專注過濾假陽性（無 FN 召回）",
            "pipeline": HybridJobSkillPipeline(
                lexicon_path=lexicon_path,
                verifier_provider="mock",
                enable_fn_recovery=False,
            ),
        },
        {
            "id": "Variant_4",
            "name": "Full Hybrid System (Phase 5 with FN Recovery)",
            "description": "完整系統：AC + 規則 + 風險分流 + LLM 驗證 + Two-Stage 概念接地與假陰性召回",
            "pipeline": HybridJobSkillPipeline(
                lexicon_path=lexicon_path,
                verifier_provider="mock",
                grounder_provider="mock",
                enable_fn_recovery=True,
            ),
        },
    ]

    reports: Dict[str, EvaluationReport] = {}
    summary_table: List[Dict[str, Any]] = []

    for v in variants:
        v_id = v["id"]
        v_name = v["name"]
        logger.info(f"\n{'='*60}\n正在評估變體：{v_id} - {v_name}\n{'='*60}")
        rep = evaluator.evaluate(pipeline=v["pipeline"], pipeline_name=v_name)
        reports[v_id] = rep

        summary_table.append({
            "variant_id": v_id,
            "variant_name": v_name,
            "description": v["description"],
            "precision": round(rep.overall.precision * 100, 2),
            "recall": round(rep.overall.recall * 100, 2),
            "micro_f1": round(rep.overall.f1 * 100, 2),
            "macro_f1": round(rep.overall.macro_f1 * 100, 2),
            "fpr": round(rep.overall.false_positive_rate * 100, 2),
            "fnr": round(rep.overall.false_negative_rate * 100, 2),
            "latency_ms": round(rep.overall.latency_ms_per_doc, 2),
            "api_cost_usd": rep.overall.estimated_api_cost_usd,
        })

    # 取得 Variant 4 的多維度切片分析
    v4_report = reports["Variant_4"]
    slicing_by_sample_type = {
        k: {
            "samples": m.total_samples,
            "precision": round(m.precision * 100, 2),
            "recall": round(m.recall * 100, 2),
            "f1": round(m.f1 * 100, 2),
        }
        for k, m in v4_report.by_sample_type.items()
    }
    slicing_by_industry = {
        k: {
            "samples": m.total_samples,
            "precision": round(m.precision * 100, 2),
            "recall": round(m.recall * 100, 2),
            "f1": round(m.f1 * 100, 2),
        }
        for k, m in v4_report.by_industry.items()
    }

    results = {
        "ablation_summary": summary_table,
        "variant_details": {
            k: json.loads(v.model_dump_json()) for k, v in reports.items()
        },
        "slicing_analysis": {
            "by_sample_type": slicing_by_sample_type,
            "by_industry": slicing_by_industry,
        },
    }

    return results


def format_markdown_table(summary: List[Dict[str, Any]]) -> str:
    """產生出版級 Markdown 消融對比表格。"""
    md = [
        "# 四大消融實驗對比矩陣 (Ablation Study Comparison)",
        "",
        "| 變體代號 | 系統變體架構 (System Variant) | Precision | Recall | Micro F1 | Macro F1 | FPR | FNR | 延遲 (ms/doc) | 成本 ($) |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for row in summary:
        md.append(
            f"| `{row['variant_id']}` | **{row['variant_name']}** | "
            f"**{row['precision']:.2f}%** | {row['recall']:.2f}% | "
            f"**{row['micro_f1']:.2f}%** | {row['macro_f1']:.2f}% | "
            f"{row['fpr']:.2f}% | {row['fnr']:.2f}% | "
            f"{row['latency_ms']:.2f} ms | ${row['api_cost_usd']:.2f} |"
        )
    return "\n".join(md)


def main():
    args = parse_args()

    if not os.path.exists(args.benchmark):
        logger.error(f"找不到 Benchmark 檔案：{args.benchmark}")
        sys.exit(1)

    if not os.path.exists(args.lexicon):
        logger.error(f"找不到詞庫檔案：{args.lexicon}")
        sys.exit(1)

    results = run_ablation_study(
        benchmark_path=args.benchmark, lexicon_path=args.lexicon
    )

    md_table = format_markdown_table(results["ablation_summary"])
    print("\n" + "=" * 80)
    print(md_table)
    print("=" * 80 + "\n")

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    logger.info(f"消融實驗結構化結果已成功儲存至：{args.output}")


if __name__ == "__main__":
    main()
