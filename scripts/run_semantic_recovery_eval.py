#!/usr/bin/env python3
"""雙語上下文感知驗證與殘差語意召回評估及消融測試腳本 (Bilingual Semantic Recovery Evaluation & Ablation Study)。

涵蓋：
1. 5 大消融實驗 (Ablation Experiments):
   - Exp A: Aho-Corasick Baseline (純 AC 匹配)
   - Exp B: AC + Stage B Context Verification (上下文驗證過濾 FP)
   - Exp C: AC + Stage B + Stage C Residual Segmentation (殘差單元切割，不檢索)
   - Exp D: AC + Stage B + Stage C + Stage D Hybrid Retrieval (無 Stage E 驗證之混合檢索)
   - Exp E: Full Redesigned System (Stage A -> E 完整重構架構)

2. 5 大細分群體切片分析 (Subgroup Analysis):
   - skill_count == 0 (AC 零命中職缺)
   - skill_count == 1 (AC 僅命中單一偶發關鍵字職缺)
   - English-heavy 職缺 (英文專業術語主導)
   - Chinese-heavy 職缺 (中文語境與隱性活動主導)
   - Mixed bilingual 職缺 (中英夾雜與模組化代碼)

3. 零成本與延遲審計 (Cost & Latency Tracking):
   - $0.00 付費 API 消耗、Token 統計、每千筆成本估算

4. 產出檔案：
   - outputs/bilingual_semantic_recovery_eval.json
   - outputs/human_review_table.csv
   - outputs/keyword_candidates.csv
"""

import os
import sys
import json
import time
import re
import logging
from typing import List, Dict, Any, Set, Tuple
import pandas as pd

# 加入專案根目錄至 sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.hybrid_pipeline import HybridJobSkillPipeline
from src.pipeline import JobSkillPipeline
from src.grounding.schemas import DecisionType, FNRecoveryResult
from src.grounding.review_table import format_markdown_review_table
from src.monitoring.cost_tracker import CostTracker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("bilingual_semantic_eval")


def classify_language(text: str) -> str:
    """分類職缺語言型態：English-heavy, Chinese-heavy, Mixed bilingual。"""
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    english_words = len(re.findall(r"[a-zA-Z]{2,}", text))
    if english_words >= 8 and chinese_chars < 15:
        return "English-heavy"
    elif chinese_chars > 0 and english_words >= 3:
        return "Mixed bilingual"
    else:
        return "Chinese-heavy"


def load_benchmark_jobs(benchmark_path: str) -> List[Dict[str, Any]]:
    """讀取 Benchmark 職缺並附加上典型雙語與殘差測試案例。"""
    jobs = []
    if os.path.exists(benchmark_path):
        with open(benchmark_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    jobs.append(json.loads(line.strip()))

    # 1. 硬體研發工程師 (Server Design, Board debug, BOM, Documents creation, Work with team)
    jobs.append({
        "id": "CASE_1_HARDWARE_ENG",
        "county": "新竹市",
        "industry": "半導體業",
        "job_role": "硬體研發工程師",
        "job_title": "硬體研發工程師",
        "job_desc": "【工作內容】\n1. Server Design\n2. Board debug\n3. BOM creation\n4. Documents creation\n5. Work with team for project development",
        "tools": "",
        "job_skills": "",
        "gold_skill_ids": ["KS120000000000000013", "KS121X369RKT17LSJNZX", "KS120000000000000005"],  # 物料清單, 電路設計, 溝通
        "gold_skill_names_zh": ["物料清單", "電路設計", "溝通"],
        "notes": "Case 1: BOM 命中物料清單，Server Design 召回電路設計，Work with team 召回溝通",
    })

    # 2. 全英文技術職缺 (Backend Software Engineer)
    jobs.append({
        "id": "CASE_2_BACKEND_ENG",
        "county": "臺北市",
        "industry": "資訊科技業",
        "job_role": "後端工程師",
        "job_title": "Backend Software Engineer",
        "job_desc": "Job Description:\n- Python backend API development and architecture planning\n- SQL database query optimization and performance tuning\n- Statistical process analysis for system metrics",
        "tools": "Python, SQL",
        "job_skills": "API Development",
        "gold_skill_ids": ["KS120000000000000007", "KS120000000000000008", "KS120L96KMYTDJ48NRSH"],  # Python, SQL, 軟體開發
        "gold_skill_names_zh": ["Python", "SQL", "軟體開發"],
        "notes": "Case 2: 英文技術描述映射至中文標準技能",
    })

    # 3. 中文隱性工作活動 (車床技術員 / 模具試樣)
    jobs.append({
        "id": "CASE_3_LATHE_TECH",
        "county": "南投縣",
        "industry": "傳統製造業",
        "job_role": "產線技術員",
        "job_title": "車床技術員",
        "job_desc": "1. 模具試樣與現場試模作業\n2. 協助產線機台操作與日常維護\n3. 配合主管交辦事項",
        "tools": "車床",
        "job_skills": "機台操作",
        "gold_skill_ids": ["TW_MFG_001", "KS120000000000000004"],  # 機台操作, 設備維護
        "gold_skill_names_zh": ["機台操作", "設備維護"],
        "notes": "Case 3: 中文隱性活動，機台操作與維護",
    })

    # 4. 中英夾雜職缺 (軟體工程師 / SAP FI/CO)
    jobs.append({
        "id": "CASE_4_ERP_ENG",
        "county": "南投縣",
        "industry": "資訊科技業",
        "job_role": "ERP工程師",
        "job_title": "SAP 系統工程師",
        "job_desc": "1. SAP FI/CO Module Implementation & Support\n2. Business Process Analysis and requirement gathering\n3. Testing & Troubleshooting for enterprise users\n4. Documentation & Training",
        "tools": "SAP",
        "job_skills": "ERP",
        "gold_skill_ids": ["KS120L96KMYTDJ48NRSH"],  # 軟體開發
        "gold_skill_names_zh": ["軟體開發"],
        "notes": "Case 4: 中英夾雜職缺語意對齊",
    })

    # 5. 欺騙性假陽性關鍵字拒絕
    jobs.append({
        "id": "CASE_5_FALSE_POSITIVE",
        "county": "新竹市",
        "industry": "半導體業",
        "job_role": "測試工程師",
        "job_title": "SSD 故障分析工程師",
        "job_desc": "負責 SSD Failure Analysis 與電氣訊號量測，需具備示波器操作能力。非財務會計人員，不涉及應收帳款與財務結算。",
        "tools": "示波器",
        "job_skills": "電子電路測試",
        "gold_skill_ids": ["KS121X369RKT17LSJNZX"],  # 電路設計/測試
        "gold_skill_names_zh": ["電路設計"],
        "notes": "Case 5: 欺騙性關鍵字過濾（拒絕應收帳款等跨領域誤判）",
    })

    return jobs


def calculate_metrics(gold_list: List[Set[str]], pred_list: List[Set[str]]) -> Dict[str, float]:
    """計算 Precision, Recall, Micro F1, Macro F1。"""
    tp = sum(len(p & g) for p, g in zip(pred_list, gold_list))
    fp = sum(len(p - g) for p, g in zip(pred_list, gold_list))
    fn = sum(len(g - p) for p, g in zip(pred_list, gold_list))

    precision = (tp / (tp + fp)) if (tp + fp) > 0 else 0.0
    recall = (tp / (tp + fn)) if (tp + fn) > 0 else 0.0
    micro_f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    # Macro F1 (平均每篇職缺之 F1)
    doc_f1s = []
    for p, g in zip(pred_list, gold_list):
        if not g and not p:
            doc_f1s.append(1.0)
            continue
        d_tp = len(p & g)
        d_fp = len(p - g)
        d_fn = len(g - p)
        d_p = d_tp / (d_tp + d_fp) if (d_tp + d_fp) > 0 else 0.0
        d_r = d_tp / (d_tp + d_fn) if (d_tp + d_fn) > 0 else 0.0
        d_f1 = (2 * d_p * d_r / (d_p + d_r)) if (d_p + d_r) > 0 else 0.0
        doc_f1s.append(d_f1)
    macro_f1 = sum(doc_f1s) / len(doc_f1s) if doc_f1s else 0.0

    return {
        "precision": round(precision * 100, 2),
        "recall": round(recall * 100, 2),
        "micro_f1": round(micro_f1 * 100, 2),
        "macro_f1": round(macro_f1 * 100, 2),
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def run_evaluation(
    benchmark_path: str = "data/gold_labels/sample_benchmark.jsonl",
    lexicon_path: str = "lexicon/sample/mini_skill_lexicon.csv",
    output_json: str = "outputs/bilingual_semantic_recovery_eval.json",
    output_review_csv: str = "outputs/human_review_table.csv",
    output_kw_csv: str = "outputs/keyword_candidates.csv",
):
    logger.info("=" * 80)
    logger.info("啟動 5 大消融實驗與雙語細分群體切片評估 (Bilingual Semantic Recovery)")
    logger.info("=" * 80)

    jobs = load_benchmark_jobs(benchmark_path)
    logger.info(f"共載入 {len(jobs)} 筆評估職缺 (含 Gold Benchmark 與 5 大典型雙語/殘差測試職缺)")

    # 初始化 5 大實驗配置
    experiments = [
        {
            "id": "Exp_A",
            "name": "Aho-Corasick Baseline",
            "desc": "純 AC 多模式匹配 (Stage A Baseline)",
            "pipeline": JobSkillPipeline(lexicon_path=lexicon_path, enable_rules=True),
            "is_hybrid": False,
        },
        {
            "id": "Exp_B",
            "name": "AC + Stage B Verification",
            "desc": "AC 候選詞 + 上下文驗證過濾 FP (Stage A + B, 無殘差召回)",
            "pipeline": HybridJobSkillPipeline(
                lexicon_path=lexicon_path,
                verifier_provider="mock",
                enable_fn_recovery=False,
            ),
            "is_hybrid": True,
        },
        {
            "id": "Exp_C",
            "name": "AC + Stage B + Stage C Residual Segmentation",
            "desc": "殘差單元切割，不執行檢索與召回 (Stage A + B + C)",
            "pipeline": HybridJobSkillPipeline(
                lexicon_path=lexicon_path,
                verifier_provider="mock",
                enable_fn_recovery=True,
                disable_retrieval=True,
            ),
            "is_hybrid": True,
        },
        {
            "id": "Exp_D",
            "name": "AC + Stage B + Stage C + Stage D Hybrid Retrieval",
            "desc": "詞庫約束雙語檢索，無 Stage E 驗證 (Stage A + B + C + D)",
            "pipeline": HybridJobSkillPipeline(
                lexicon_path=lexicon_path,
                verifier_provider="mock",
                enable_fn_recovery=True,
                bypass_verification=True,
            ),
            "is_hybrid": True,
        },
        {
            "id": "Exp_E",
            "name": "Full Redesigned System (Stage A -> E)",
            "desc": "完整系統：AC + 雙語上下文驗證 + 殘差單元切割 + 雙語檢索 + 語意決策驗證",
            "pipeline": HybridJobSkillPipeline(
                lexicon_path=lexicon_path,
                verifier_provider="mock",
                enable_fn_recovery=True,
                bypass_verification=False,
                disable_retrieval=False,
            ),
            "is_hybrid": True,
        },
    ]

    cost_tracker = CostTracker()
    exp_results: Dict[str, Any] = {}
    all_fn_results: List[FNRecoveryResult] = []

    # 預先為所有職缺標註 AC 匹配數量與語言型態
    ac_pipeline: JobSkillPipeline = experiments[0]["pipeline"]
    job_meta: List[Dict[str, Any]] = []

    for job in jobs:
        j_id = job.get("id", "")
        title = job.get("job_title", "")
        desc = job.get("job_desc", "")
        tools = job.get("tools", "")
        skills = job.get("job_skills", "")
        full_text = f"{title} {desc} {tools} {skills}"

        ac_cands = ac_pipeline.extract_job_skills(
            job_desc=desc, job_title=title, tools=tools, job_skills=skills
        )
        ac_count = len(ac_cands)
        lang_type = classify_language(full_text)

        job_meta.append({
            "id": j_id,
            "title": title,
            "desc": desc,
            "tools": tools,
            "skills": skills,
            "gold_skill_ids": set(job.get("gold_skill_ids", [])),
            "gold_skill_names_zh": job.get("gold_skill_names_zh", []),
            "ac_count": ac_count,
            "lang_type": lang_type,
        })

    # 依序執行 5 大消融實驗
    for exp in experiments:
        exp_id = exp["id"]
        exp_name = exp["name"]
        pipe = exp["pipeline"]
        is_hybrid = exp["is_hybrid"]

        logger.info(f"正在執行實驗：{exp_id} - {exp_name}...")
        t0 = time.time()

        predictions: List[Set[str]] = []
        golds: List[Set[str]] = [m["gold_skill_ids"] for m in job_meta]

        for idx, m in enumerate(job_meta):
            j_id = m["id"]
            title = m["title"]
            desc = m["desc"]
            tools = m["tools"]
            skills = m["skills"]

            if is_hybrid:
                final_skills, routing_res, _ = pipe.extract_job_skills(
                    job_id=j_id,
                    job_title=title,
                    job_desc=desc,
                    tools=tools,
                    job_skills=skills,
                )
                pred_ids = set(s.skill_id for s in final_skills)

                # 收集 Exp E 產出的完整診斷以供 Review Table 與 擴展詞導出
                if exp_id == "Exp_E":
                    fn_res = routing_res.fn_recovery_result
                    if not fn_res:
                        fn_res = pipe.diagnose_job_description(
                            job_title=title, job_desc=desc, tools=tools, job_skills=skills, job_id=j_id
                        )
                    all_fn_results.append(fn_res)
            else:
                cands = pipe.extract_job_skills(
                    job_desc=desc, job_title=title, tools=tools, job_skills=skills
                )
                pred_ids = set(c.skill_id for c in cands)

            predictions.append(pred_ids)

        elapsed_ms = (time.time() - t0) * 1000
        for _ in range(len(job_meta)):
            cost_tracker.record_job(latency_ms=elapsed_ms / len(job_meta))
        if is_hybrid:
            cost_tracker.record_llm_call(input_tokens=0, output_tokens=0, latency_ms=0.0)

        # 計算整體指標
        overall_metrics = calculate_metrics(golds, predictions)
        overall_metrics["latency_ms_per_doc"] = round(elapsed_ms / len(job_meta), 2)

        # 計算細分群體切片指標 (Subgroup Metrics)
        subgroups = {
            "skill_count == 0": [i for i, m in enumerate(job_meta) if m["ac_count"] == 0],
            "skill_count == 1": [i for i, m in enumerate(job_meta) if m["ac_count"] == 1],
            "English-heavy": [i for i, m in enumerate(job_meta) if m["lang_type"] == "English-heavy"],
            "Chinese-heavy": [i for i, m in enumerate(job_meta) if m["lang_type"] == "Chinese-heavy"],
            "Mixed bilingual": [i for i, m in enumerate(job_meta) if m["lang_type"] == "Mixed bilingual"],
        }

        subgroup_metrics = {}
        for s_name, indices in subgroups.items():
            sub_golds = [golds[i] for i in indices]
            sub_preds = [predictions[i] for i in indices]
            sub_m = calculate_metrics(sub_golds, sub_preds)
            sub_m["sample_count"] = len(indices)
            subgroup_metrics[s_name] = sub_m

        exp_results[exp_id] = {
            "name": exp_name,
            "desc": exp["desc"],
            "overall": overall_metrics,
            "subgroups": subgroup_metrics,
        }

    # 產出人工審核表與擴充關鍵字
    full_hybrid_pipe: HybridJobSkillPipeline = experiments[-1]["pipeline"]
    review_df = full_hybrid_pipe.generate_review_table(all_fn_results)
    review_df.to_csv(output_review_csv, index=False, encoding="utf-8-sig")

    kw_df = full_hybrid_pipe.export_keyword_candidates(all_fn_results, output_path=output_kw_csv)

    # 統計審核表狀態
    total_recovered = sum(1 for _, row in review_df.iterrows() if row.get("decision") == "MATCH")
    total_uncertain = sum(1 for _, row in review_df.iterrows() if row.get("decision") == "UNCERTAIN")
    total_rejected = sum(1 for _, row in review_df.iterrows() if row.get("decision") == "NO_MATCH")

    # 彙整評估結果
    audit_summary = cost_tracker.get_summary()
    final_output = {
        "experiments": exp_results,
        "cost_and_latency_audit": audit_summary,
        "semantic_recovery_summary": {
            "recovered_matches": total_recovered,
            "uncertain_cases": total_uncertain,
            "rejected_no_match": total_rejected,
            "review_table_path": output_review_csv,
            "keyword_candidates_path": output_kw_csv,
        },
    }

    os.makedirs(os.path.dirname(output_json), exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(final_output, f, indent=2, ensure_ascii=False)

    # 印出出版級 Markdown 消融矩陣與細分群體對比
    print("\n" + "=" * 90)
    print("🏆 5 大消融實驗對比矩陣 (5-Stage Ablation Study Matrix)")
    print("=" * 90)
    print(
        f"{'實驗代號':<8} | {'系統架構變體 (Variant)':<45} | {'Precision':<10} | {'Recall':<10} | {'Micro F1':<10} | {'Macro F1':<10} | {'延遲 (ms)':<10}"
    )
    print("-" * 115)
    for exp_id, data in exp_results.items():
        ov = data["overall"]
        print(
            f"{exp_id:<8} | {data['name']:<45} | {ov['precision']:>8.2f}% | {ov['recall']:>8.2f}% | {ov['micro_f1']:>8.2f}% | {ov['macro_f1']:>8.2f}% | {ov['latency_ms_per_doc']:>8.2f} ms"
        )
    print("=" * 90)

    print("\n" + "=" * 90)
    print("🎯 細分群體切片指標對比 (Subgroup Slicing: Exp A vs Exp E)")
    print("=" * 90)
    print(
        f"{'細分維度 (Subgroup)':<22} | {'樣本數':<6} | {'Exp A F1':<10} | {'Exp E F1':<10} | {'Exp A Recall':<12} | {'Exp E Recall':<12} | {'Recall 增益':<10}"
    )
    print("-" * 90)
    exp_a_sub = exp_results["Exp_A"]["subgroups"]
    exp_e_sub = exp_results["Exp_E"]["subgroups"]

    for s_name in exp_a_sub:
        a_m = exp_a_sub[s_name]
        e_m = exp_e_sub[s_name]
        gain = e_m["recall"] - a_m["recall"]
        print(
            f"{s_name:<22} | {a_m['sample_count']:<6} | {a_m['micro_f1']:>8.2f}% | {e_m['micro_f1']:>8.2f}% | {a_m['recall']:>10.2f}% | {e_m['recall']:>10.2f}% | {gain:>+8.2f}%"
        )
    print("=" * 90)

    print("\n" + "=" * 90)
    print("💰 成本與延遲審計摘要 (Cost Safety & Latency Audit)")
    print("=" * 90)
    print(f"• 總處理樣本數:     {len(job_meta)} 筆 x 5 實驗")
    print(f"• 累計 API 呼叫次數: {audit_summary['llm_calls']} 次 (全本機確定性與零付費)")
    print(f"• 累計 Token 消耗量: {audit_summary['total_tokens']} tokens")
    print(f"• 累計費用支出:     ${audit_summary['estimated_cost_usd']:.4f} USD (100% 遵守 $0 Paid API 約束)")
    print(f"• 每千筆預估費用:   ${audit_summary['cost_per_1k_jobs_usd']:.4f} USD")
    print(f"• 語意召回總計:     MATCH={total_recovered} 筆, UNCERTAIN={total_uncertain} 筆, NO_MATCH={total_rejected} 筆")
    print("=" * 90)

    print("\n🔍 人工審核總表預覽 (Human Review Table - Top 10):")
    print(format_markdown_review_table(review_df, max_rows=10))

    print("\n✅ 評估成果檔案輸出完畢：")
    print(f"1. 評估指標 JSON:   {output_json}")
    print(f"2. 人工審核總表:     {output_review_csv}")
    print(f"3. 擴充關鍵字候選:   {output_kw_csv}\n")


if __name__ == "__main__":
    run_evaluation()
