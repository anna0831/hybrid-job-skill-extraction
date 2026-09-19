"""核心評估管線模組：自動化評估管線在 Benchmark 上的表現並產出多維度報告。"""

import time
import json
import logging
from typing import List, Dict, Any, Set, Optional
from pydantic import BaseModel, Field

from src.evaluation.metrics import EvaluationMetrics, compute_metrics
from src.evaluation.slicer import slice_metrics_by_field, slice_metrics_by_skill_category
from src.preprocessing.normalizer import clean_text

logger = logging.getLogger(__name__)


class ErrorSample(BaseModel):
    """錯誤樣本紀錄模型：紀錄 False Positive 與 False Negative 之詳細案例。"""
    job_id: str
    job_title: str
    sample_type: str
    false_positives: List[str] = Field(default_factory=list, description="多抓/誤抓的技能")
    false_negatives: List[str] = Field(default_factory=list, description="漏抓的技能")
    notes: Optional[str] = None


class EvaluationReport(BaseModel):
    """完整評估報告資料模型。"""
    pipeline_name: str
    timestamp: str
    overall: EvaluationMetrics
    by_sample_type: Dict[str, EvaluationMetrics]
    by_county: Dict[str, EvaluationMetrics]
    by_industry: Dict[str, EvaluationMetrics]
    by_job_role: Dict[str, EvaluationMetrics]
    by_skill_category: Dict[str, EvaluationMetrics]
    error_samples: List[ErrorSample]

    def to_markdown(self) -> str:
        """產生 Markdown 格式的評估報告摘要。"""
        md = []
        md.append(f"# Benchmark 評估報告: {self.pipeline_name}")
        md.append(f"**評估時間**: {self.timestamp} | **樣本總數**: {self.overall.total_samples}\n")
        
        md.append("## 1. 整體指標 (Overall Performance)")
        md.append("| 指標 | 數值 | 說明 |")
        md.append("| :--- | :--- | :--- |")
        md.append(f"| **Precision** | **{self.overall.precision * 100:.2f}%** | 預測技能的精確度 (TP / TP+FP) |")
        md.append(f"| **Recall** | **{self.overall.recall * 100:.2f}%** | 標準技能的召回率 (TP / TP+FN) |")
        md.append(f"| **F1-Score** | **{self.overall.f1 * 100:.2f}%** | 微觀調和平均 (Micro F1) |")
        md.append(f"| **Macro F1** | {self.overall.macro_f1 * 100:.2f}% | 篇章宏觀平均 F1 |")
        md.append(f"| **False Positive Rate (FPR)** | **{self.overall.false_positive_rate * 100:.2f}%** | 誤判比例 (FP / TP+FP) |")
        md.append(f"| **False Negative Rate (FNR)** | **{self.overall.false_negative_rate * 100:.2f}%** | 漏判比例 (FN / TP+FN) |")
        md.append(f"| **平均延遲 (Latency)** | **{self.overall.latency_ms_per_doc:.2f} ms/doc** | 每篇職缺處理耗時 |")
        md.append(f"| **API 總成本** | ${self.overall.estimated_api_cost_usd:.6f} USD | 預估 LLM 費用 |\n")

        md.append("## 2. 樣本類型切片 (Performance by Sample Type)")
        md.append("| 樣本類型 | 樣本數 | Precision | Recall | F1-Score | FPR | FNR |")
        md.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for stype, m in self.by_sample_type.items():
            md.append(
                f"| `{stype}` | {m.total_samples} | {m.precision*100:.1f}% | "
                f"{m.recall*100:.1f}% | **{m.f1*100:.1f}%** | {m.false_positive_rate*100:.1f}% | {m.false_negative_rate*100:.1f}% |"
            )
        md.append("")

        md.append("## 3. 產業類別切片 (Performance by Industry)")
        md.append("| 產業別 | 樣本數 | Precision | Recall | F1-Score |")
        md.append("| :--- | :--- | :--- | :--- | :--- |")
        for ind, m in self.by_industry.items():
            md.append(f"| {ind} | {m.total_samples} | {m.precision*100:.1f}% | {m.recall*100:.1f}% | **{m.f1*100:.1f}%** |")
        md.append("")

        if self.error_samples:
            md.append("## 4. 經典錯誤案例檢視 (Error Analysis Samples)")
            md.append("| 職缺 ID | 職位名稱 | 樣本類型 | 誤抓 (False Positive) | 漏抓 (False Negative) | 備註說明 |")
            md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
            for err in self.error_samples[:8]:
                fp_str = "、".join(err.false_positives) if err.false_positives else "-"
                fn_str = "、".join(err.false_negatives) if err.false_negatives else "-"
                md.append(f"| `{err.job_id}` | {err.job_title} | `{err.sample_type}` | <span style='color:red'>{fp_str}</span> | <span style='color:blue'>{fn_str}</span> | {err.notes or ''} |")
            md.append("")

        return "\n".join(md)


class PipelineEvaluator:
    """管線評估器類別。"""

    def __init__(self, benchmark_path: str = "data/gold_labels/sample_benchmark.jsonl"):
        self.benchmark_path = benchmark_path
        self.dataset = self._load_benchmark(benchmark_path)

    def _load_benchmark(self, path: str) -> List[Dict[str, Any]]:
        records = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        logger.info(f"載入 Gold Label Benchmark：共 {len(records)} 筆樣本")
        return records

    def evaluate(
        self,
        pipeline: Any,
        pipeline_name: str = "Baseline AC Matcher",
        api_cost_usd: float = 0.0,
    ) -> EvaluationReport:
        """對傳入的 pipeline 物件進行標準 Benchmark 評估。"""
        logger.info(f"開始評估管線：{pipeline_name}...")
        y_true_ids: List[Set[str]] = []
        y_pred_ids: List[Set[str]] = []
        y_pred_names: List[Set[str]] = []
        error_samples: List[ErrorSample] = []

        skill_to_cat: Dict[str, str] = {}
        id_to_name: Dict[str, str] = {}

        t0 = time.time()
        for item in self.dataset:
            job_id = item["id"]
            job_title = clean_text(item.get("job_title", ""))
            texts = [
                clean_text(item.get("job_desc", "")),
                clean_text(item.get("job_skills", "")),
                clean_text(item.get("tools", "")),
            ]
            gt_ids = set(item.get("gold_skill_ids", []))
            y_true_ids.append(gt_ids)

            # 調用 pipeline 比對 (支援 AC 與 Hybrid 管線)
            if hasattr(pipeline, "extract_job_skills") and not hasattr(pipeline, "term_to_entries"):
                res = pipeline.extract_job_skills(
                    job_id=job_id,
                    job_title=job_title,
                    job_desc=texts[0],
                    job_skills=texts[1],
                    tools=texts[2],
                )
                matched = res[0] if isinstance(res, tuple) else res
            else:
                matched = pipeline.matcher.extract_job_skills(texts, job_title=job_title)

            pred_ids = {c.skill_id for c in matched}
            pred_names = {c.skill_name_zh for c in matched}

            for c in matched:
                skill_to_cat[c.skill_id] = c.skill_cat9
                id_to_name[c.skill_id] = c.skill_name_zh

            y_pred_ids.append(pred_ids)
            y_pred_names.append(pred_names)

            # 收集錯誤樣本
            fp_ids = pred_ids - gt_ids
            fn_ids = gt_ids - pred_ids
            if fp_ids or fn_ids:
                # 建立 id -> 舊名稱對應
                gt_name_dict = dict(
                    zip(item.get("gold_skill_ids", []), item.get("gold_skill_names_zh", []))
                )
                fp_names = [id_to_name.get(sid, sid) for sid in fp_ids]
                fn_names = [gt_name_dict.get(sid, id_to_name.get(sid, sid)) for sid in fn_ids]
                error_samples.append(
                    ErrorSample(
                        job_id=job_id,
                        job_title=job_title,
                        sample_type=item.get("sample_type", "unknown"),
                        false_positives=fp_names,
                        false_negatives=fn_names,
                        notes=item.get("notes"),
                    )
                )

        total_elapsed_ms = (time.time() - t0) * 1000

        # 計算整體指標
        overall = compute_metrics(
            y_true=y_true_ids,
            y_pred=y_pred_ids,
            total_time_ms=total_elapsed_ms,
            api_cost_usd=api_cost_usd,
        )

        # 計算多維度切片
        by_sample_type = slice_metrics_by_field(self.dataset, y_true_ids, y_pred_ids, "sample_type")
        by_county = slice_metrics_by_field(self.dataset, y_true_ids, y_pred_ids, "county")
        by_industry = slice_metrics_by_field(self.dataset, y_true_ids, y_pred_ids, "industry")
        by_job_role = slice_metrics_by_field(self.dataset, y_true_ids, y_pred_ids, "job_role")
        by_category = slice_metrics_by_skill_category(y_true_ids, y_pred_ids, skill_to_cat)

        report = EvaluationReport(
            pipeline_name=pipeline_name,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            overall=overall,
            by_sample_type=by_sample_type,
            by_county=by_county,
            by_industry=by_industry,
            by_job_role=by_job_role,
            by_skill_category=by_category,
            error_samples=error_samples,
        )

        logger.info(
            f"評估完成！Precision: {overall.precision*100:.2f}%, Recall: {overall.recall*100:.2f}%, F1: {overall.f1*100:.2f}%"
        )
        return report
