#!/usr/bin/env python3
"""單檔職缺技能擷取 CLI 腳本。

用法：
    python scripts/run_single_file.py --input dataset/cleaned_彰化縣_202608.xlsx
    python scripts/run_single_file.py --input data/sample/sample_jobs.jsonl --lexicon lexicon/sample/mini_skill_lexicon.csv
"""

import os
import sys
import time
import argparse
import logging
import yaml

from src.pipeline import JobSkillPipeline
from src.preprocessing.normalizer import extract_county, extract_month

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_single_file")


def parse_args():
    parser = argparse.ArgumentParser(
        description="執行單一檔案職缺之 Aho-Corasick 技能比對並匯出寬表格。"
    )
    parser.add_argument(
        "-i",
        "--input",
        type=str,
        default="data/sample/sample_jobs.jsonl",
        help="輸入職缺資料路徑 (.xlsx, .csv 或 .jsonl)",
    )
    parser.add_argument(
        "-l",
        "--lexicon",
        type=str,
        default=None,
        help="技能詞庫路徑 (預設依 settings.yaml 設定)",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=str,
        default="outputs",
        help="輸出目錄 (預設為 outputs/)",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default="configs/settings.yaml",
        help="全域設定檔路徑",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # 讀取設定檔
    settings = {}
    if os.path.exists(args.config):
        with open(args.config, "r", encoding="utf-8") as f:
            settings = yaml.safe_load(f)

    # 決定詞庫路徑
    lexicon_path = args.lexicon
    if not lexicon_path:
        default_lex = settings.get("paths", {}).get("full_lexicon", "詞庫skill_lexicon_v13_20260915.xlsx")
        if os.path.exists(default_lex):
            lexicon_path = default_lex
        else:
            sample_lex = settings.get("paths", {}).get("sample_lexicon", "lexicon/sample/mini_skill_lexicon.csv")
            lexicon_path = sample_lex
            logger.info(f"未找到完整詞庫，切換至公開樣本詞庫：{lexicon_path}")

    if not os.path.exists(args.input):
        logger.error(f"輸入檔案不存在：{args.input}")
        sys.exit(1)

    county = extract_county(args.input)
    month = extract_month(args.input)
    os.makedirs(args.output_dir, exist_ok=True)

    t0 = time.time()
    pipeline = JobSkillPipeline(lexicon_path=lexicon_path)
    init_time = time.time() - t0

    t1 = time.time()
    out_name = f"skills_{county}_{month}_wide.xlsx"
    out_path = os.path.join(args.output_dir, out_name)

    long_df, wide_df = pipeline.process_file(args.input, output_path=out_path)
    proc_time = time.time() - t1

    logger.info("=" * 60)
    logger.info(f"比對完成！")
    logger.info(f"  職缺筆數：{len(wide_df):,} 筆")
    logger.info(f"  命中間數：{len(long_df):,} 筆")
    logger.info(f"  初始化耗時：{init_time:.2f}s | 比對耗時：{proc_time:.2f}s")
    logger.info(f"  輸出檔案：{out_path}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
