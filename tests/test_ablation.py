"""四大消融實驗與多維度誤差切片單元測試 (Ablation Study Tests)。"""

import pytest
from scripts.run_ablation_study import run_ablation_study, format_markdown_table
from src.pipeline import JobSkillPipeline
from src.hybrid_pipeline import HybridJobSkillPipeline


def test_ablation_variants_instantiation():
    """驗證四大變體均能正常實例化並處理單一職缺。"""
    lexicon_path = "lexicon/sample/mini_skill_lexicon.csv"

    v1 = JobSkillPipeline(lexicon_path=lexicon_path, enable_rules=False)
    v2 = JobSkillPipeline(lexicon_path=lexicon_path, enable_rules=True)
    v3 = HybridJobSkillPipeline(lexicon_path=lexicon_path, verifier_provider="mock", enable_fn_recovery=False)
    v4 = HybridJobSkillPipeline(lexicon_path=lexicon_path, verifier_provider="mock", enable_fn_recovery=True)

    job_title = "Python 後端工程師"
    job_desc = "負責後端 API 開發，需熟悉 Python 與 SQL。"

    res1 = v1.extract_job_skills(job_title=job_title, job_desc=job_desc)
    res2 = v2.extract_job_skills(job_title=job_title, job_desc=job_desc)
    res3, _, _ = v3.extract_job_skills(job_id="TEST_1", job_title=job_title, job_desc=job_desc)
    res4, _, _ = v4.extract_job_skills(job_id="TEST_1", job_title=job_title, job_desc=job_desc)

    assert len(res1) > 0
    assert len(res2) > 0
    assert len(res3) > 0
    assert len(res4) > 0


def test_ablation_study_full_execution():
    """執行消融實驗並驗證指標的漸進改善特性。"""
    benchmark_path = "data/gold_labels/sample_benchmark.jsonl"
    lexicon_path = "lexicon/sample/mini_skill_lexicon.csv"

    results = run_ablation_study(benchmark_path, lexicon_path)

    assert "ablation_summary" in results
    assert "slicing_analysis" in results
    assert len(results["ablation_summary"]) == 4

    summary = {row["variant_id"]: row for row in results["ablation_summary"]}

    v1 = summary["Variant_1"]
    v2 = summary["Variant_2"]
    v3 = summary["Variant_3"]
    v4 = summary["Variant_4"]

    # 1. Variant 3 (LLM Verifier) 消除假陽性，Precision 達到 100% 且 FPR 歸零
    assert v3["precision"] == 100.0
    assert v3["fpr"] == 0.0

    # 2. Variant 4 (FN Recovery) 召回漏抓，Recall 顯著高於 Variant 3
    assert v4["recall"] >= v3["recall"]
    assert v4["micro_f1"] >= v3["micro_f1"]
    assert v4["precision"] == 100.0

    # 3. 驗證 Markdown 表格生成功能
    md_table = format_markdown_table(results["ablation_summary"])
    assert "| `Variant_1` |" in md_table
    assert "| `Variant_4` |" in md_table
