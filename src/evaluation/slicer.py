"""多維度誤差切片分析模組 (Error Slicing)：支援依縣市、產業、角色、樣本類型進行指標切片。"""

from collections import defaultdict
from typing import List, Dict, Any, Set
from src.evaluation.metrics import compute_metrics, EvaluationMetrics


def slice_metrics_by_field(
    dataset: List[Dict[str, Any]],
    y_true: List[Set[str]],
    y_pred: List[Set[str]],
    slice_field: str,
) -> Dict[str, EvaluationMetrics]:
    """依指定欄位對評估指標進行分群切片計算。
    
    支援欄位：county, industry, job_role, sample_type 等。
    """
    grouped_true: Dict[str, List[Set[str]]] = defaultdict(list)
    grouped_pred: Dict[str, List[Set[str]]] = defaultdict(list)

    for item, gt, pred in zip(dataset, y_true, y_pred):
        key = str(item.get(slice_field, "Unknown"))
        grouped_true[key].append(gt)
        grouped_pred[key].append(pred)

    results: Dict[str, EvaluationMetrics] = {}
    for key in sorted(grouped_true.keys()):
        results[key] = compute_metrics(grouped_true[key], grouped_pred[key])

    return results


def slice_metrics_by_skill_category(
    y_true: List[Set[str]],
    y_pred: List[Set[str]],
    skill_to_category: Dict[str, str],
) -> Dict[str, EvaluationMetrics]:
    """依 9 大技能分類計算個別分類下的技能擷取指標。
    
    參數：
        skill_to_category: skill_id 或 skill_name 到 9 大類名稱的對照字典
    """
    all_categories = set(skill_to_category.values())
    cat_true: Dict[str, List[Set[str]]] = {cat: [] for cat in all_categories}
    cat_pred: Dict[str, List[Set[str]]] = {cat: [] for cat in all_categories}

    for gt, pred in zip(y_true, y_pred):
        for cat in all_categories:
            sub_gt = {s for s in gt if skill_to_category.get(s) == cat}
            sub_pred = {s for s in pred if skill_to_category.get(s) == cat}
            cat_true[cat].append(sub_gt)
            cat_pred[cat].append(sub_pred)

    results: Dict[str, EvaluationMetrics] = {}
    for cat in sorted(all_categories):
        # 僅計算有出現過技能的分類
        total_items = sum(len(s) for s in cat_true[cat]) + sum(len(s) for s in cat_pred[cat])
        if total_items > 0:
            results[cat] = compute_metrics(cat_true[cat], cat_pred[cat])

    return results
