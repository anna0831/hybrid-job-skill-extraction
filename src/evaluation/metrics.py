"""評估指標計算模組：支援 Precision, Recall, F1, FPR, FNR, Latency 與成本統計。"""

from typing import List, Set, Dict, Any, Optional
from pydantic import BaseModel, Field


class EvaluationMetrics(BaseModel):
    """標準評估指標資料模型。"""
    total_samples: int = Field(..., description="評估樣本總數")
    tp: int = Field(..., description="True Positives (預測正確的技能數)")
    fp: int = Field(..., description="False Positives (多抓/誤抓的技能數)")
    fn: int = Field(..., description="False Negatives (漏抓的技能數)")
    precision: float = Field(..., description="精確率 (Micro Precision): TP / (TP + FP)")
    recall: float = Field(..., description="召回率 (Micro Recall): TP / (TP + FN)")
    f1: float = Field(..., description="F1 分數 (Micro F1)")
    macro_precision: float = Field(..., description="宏觀平均精確率 (Macro Precision)")
    macro_recall: float = Field(..., description="宏觀平均召回率 (Macro Recall)")
    macro_f1: float = Field(..., description="宏觀平均 F1 (Macro F1)")
    false_positive_rate: float = Field(
        ..., description="誤判比例 (FPR / FDR): FP / (TP + FP) = 1 - Precision"
    )
    false_negative_rate: float = Field(
        ..., description="漏判比例 (FNR): FN / (TP + FN) = 1 - Recall"
    )
    latency_ms_per_doc: float = Field(
        default=0.0, description="平均每篇職缺耗時 (毫秒)"
    )
    estimated_api_cost_usd: float = Field(
        default=0.0, description="預估 LLM API 總花費 (美元)"
    )

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()


def compute_metrics(
    y_true: List[Set[str]],
    y_pred: List[Set[str]],
    total_time_ms: float = 0.0,
    api_cost_usd: float = 0.0,
) -> EvaluationMetrics:
    """計算整組預測集與標準答案集的完整指標。
    
    參數：
        y_true: 每個職缺的標準技能集合列表 (可以是 Skill_ID 或 Skill_Name)
        y_pred: 每個職缺的預測技能集合列表
        total_time_ms: 總處理耗時 (毫秒)
        api_cost_usd: 總 API 成本 (美元)
    """
    assert len(y_true) == len(y_pred), "y_true 與 y_pred 長度必須一致"
    n_samples = len(y_true)
    if n_samples == 0:
        return EvaluationMetrics(
            total_samples=0,
            tp=0,
            fp=0,
            fn=0,
            precision=0.0,
            recall=0.0,
            f1=0.0,
            macro_precision=0.0,
            macro_recall=0.0,
            macro_f1=0.0,
            false_positive_rate=0.0,
            false_negative_rate=0.0,
            latency_ms_per_doc=0.0,
            estimated_api_cost_usd=0.0,
        )

    total_tp = 0
    total_fp = 0
    total_fn = 0

    precisions: List[float] = []
    recalls: List[float] = []
    f1s: List[float] = []

    for gt, pred in zip(y_true, y_pred):
        tp = len(gt & pred)
        fp = len(pred - gt)
        fn = len(gt - pred)

        total_tp += tp
        total_fp += fp
        total_fn += fn

        p = tp / (tp + fp) if (tp + fp) > 0 else (1.0 if len(gt) == 0 else 0.0)
        r = tp / (tp + fn) if (tp + fn) > 0 else (1.0 if len(pred) == 0 else 0.0)
        f1_val = 2 * p * r / (p + r) if (p + r) > 0 else 0.0

        precisions.append(p)
        recalls.append(r)
        f1s.append(f1_val)

    # Micro 指標
    micro_p = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    micro_r = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    micro_f1 = (
        (2 * micro_p * micro_r / (micro_p + micro_r))
        if (micro_p + micro_r) > 0
        else 0.0
    )

    # Macro 指標
    macro_p = sum(precisions) / n_samples
    macro_r = sum(recalls) / n_samples
    macro_f1 = sum(f1s) / n_samples

    fpr = total_fp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    fnr = total_fn / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    latency_per_doc = total_time_ms / n_samples if n_samples > 0 else 0.0

    return EvaluationMetrics(
        total_samples=n_samples,
        tp=total_tp,
        fp=total_fp,
        fn=total_fn,
        precision=round(micro_p, 4),
        recall=round(micro_r, 4),
        f1=round(micro_f1, 4),
        macro_precision=round(macro_p, 4),
        macro_recall=round(macro_r, 4),
        macro_f1=round(macro_f1, 4),
        false_positive_rate=round(fpr, 4),
        false_negative_rate=round(fnr, 4),
        latency_ms_per_doc=round(latency_per_doc, 2),
        estimated_api_cost_usd=round(api_cost_usd, 6),
    )
