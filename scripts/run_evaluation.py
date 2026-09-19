#!/usr/bin/env python3
"""自動化 Benchmark 評估 CLI 腳本。

用法：
    python scripts/run_evaluation.py
    python scripts/run_evaluation.py --benchmark data/gold_labels/sample_benchmark.jsonl --output outputs/benchmark_baseline_ac.json
"""

import os
import sys
import argparse
import logging

from src.pipeline import JobSkillPipeline
from src.evaluation.evaluator import PipelineEvaluator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_evaluation")


def parse_args():
    parser = argparse.ArgumentParser(
        description="執行 Gold Label Benchmark 自動化評估並產出報告。"
    )
    parser.add_argument(
        "-b",
        "--benchmark",
        type=str,
        default="data/gold_labels/sample_benchmark.jsonl",
        help="Gold Label Benchmark 資料路徑 (.jsonl)",
    )
    parser.add_argument(
        "-l",
        "--lexicon",
        type=str,
        default="lexicon/sample/mini_skill_lexicon.csv",
        help="技能詞庫路徑",
    )
    parser.add_argument(
        "-p",
        "--pipeline-type",
        type=str,
        default="ac",
        choices=["ac", "hybrid"],
        help="評估管線類型: 'ac' (純 AC Baseline) 或 'hybrid' (AC + Risk Router + LLM Verifier + FN Recovery)",
    )
    parser.add_argument(
        "--disable-fn-recovery",
        action="store_true",
        help="關閉 Phase 5 兩階段概念接地與假陰性召回",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="outputs/benchmark_evaluation.json",
        help="輸出 JSON 報告路徑",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if not os.path.exists(args.benchmark):
        logger.error(f"找不到 Benchmark 資料：{args.benchmark}")
        sys.exit(1)

    if not os.path.exists(args.lexicon):
        logger.error(f"找不到詞庫檔案：{args.lexicon}")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info(f"啟動 Gold Label 自動化評估流程 (管線: {args.pipeline_type.upper()})")
    logger.info("=" * 60)

    # 1. 初始化 Pipeline 與 Evaluator
    if args.pipeline_type == "hybrid":
        from src.hybrid_pipeline import HybridJobSkillPipeline
        enable_fn = not args.disable_fn_recovery
        pipeline = HybridJobSkillPipeline(
            lexicon_path=args.lexicon,
            verifier_provider="mock",
            grounder_provider="mock",
            enable_fn_recovery=enable_fn,
        )
        pipeline_name = (
            "Phase 5 Full Hybrid (AC + Router + Verifier + FN Recovery)"
            if enable_fn
            else "Phase 4 Hybrid (AC + Router + Verifier)"
        )
    else:
        pipeline = JobSkillPipeline(lexicon_path=args.lexicon)
        pipeline_name = "Phase 1 Baseline Aho-Corasick"

    evaluator = PipelineEvaluator(benchmark_path=args.benchmark)

    # 2. 執行評估
    report = evaluator.evaluate(
        pipeline=pipeline,
        pipeline_name=pipeline_name,
        api_cost_usd=0.0,
    )

    # 3. 輸出 Markdown 報告至終端機
    md_content = report.to_markdown()
    print("\n" + "=" * 60)
    print(md_content)
    print("=" * 60 + "\n")

    # 4. 儲存 JSON 結構化報告
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(report.model_dump_json(indent=2))

    logger.info(f"結構化報告已儲存至：{args.output}")


if __name__ == "__main__":
    main()
