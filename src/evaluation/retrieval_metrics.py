"""檢索評估指標模組 (Research-Grade Retrieval Metrics: Recall@K, MRR)。

用於獨立評估語意檢索層 (Stage D) 在各短語上的檢索能力，
嚴格區分「檢索失敗 (Retrieval Failure)」與「驗證失敗 (Verification Failure)」。
"""

from typing import List, Set, Dict, Any, Tuple


def recall_at_k(retrieved_ids: List[str], gold_ids: Set[str], k: int = 5) -> float:
    """計算 Recall@K：前 K 個檢索結果中是否包含任一 Gold Skill_ID。
    
    Args:
        retrieved_ids: 檢索回傳之 Skill_ID 列表 (依相關度排序)
        gold_ids: 標準答案 Skill_ID 集合
        k: 評估截止位次 (Top-K)
        
    Returns:
        1.0 (命中) 或 0.0 (未命中)
    """
    if not gold_ids:
        return 1.0 if not retrieved_ids else 0.0
    top_k = set(retrieved_ids[:k])
    return 1.0 if len(top_k & gold_ids) > 0 else 0.0


def reciprocal_rank(retrieved_ids: List[str], gold_ids: Set[str]) -> float:
    """計算倒數排名 (Reciprocal Rank, RR)。
    
    Args:
        retrieved_ids: 檢索回傳之 Skill_ID 列表
        gold_ids: 標準答案 Skill_ID 集合
        
    Returns:
        1 / rank (1-indexed) 或 0.0 (未出現)
    """
    for rank, sid in enumerate(retrieved_ids, 1):
        if sid in gold_ids:
            return 1.0 / rank
    return 0.0


def evaluate_retrieval_dataset(
    queries_with_gold: List[Dict[str, Any]],
    retriever: Any,
    k_list: List[int] = [1, 5, 10],
) -> Dict[str, float]:
    """批次評估多筆查詢之平均檢索指標 (Mean Recall@K, MRR)。
    
    Args:
        queries_with_gold: 包含 "query" (str) 與 "gold_skill_ids" (List[str] / Set[str]) 的字典清單
        retriever: 具備 retrieve(query, top_k) 方法之檢索器物件
        k_list: 需評估之 K 值清單 (預設 [1, 5, 10])
        
    Returns:
        {"Recall@1": float, "Recall@5": float, "Recall@10": float, "MRR": float, "total_queries": int}
    """
    if not queries_with_gold:
        return {f"Recall@{k}": 0.0 for k in k_list} | {"MRR": 0.0, "total_queries": 0}

    max_k = max(k_list)
    recalls = {k: 0.0 for k in k_list}
    mrr_total = 0.0
    valid_queries = 0

    for item in queries_with_gold:
        query = item.get("query", "")
        gold_ids = set(item.get("gold_skill_ids", []))
        if not gold_ids:
            continue

        valid_queries += 1
        retrieved = retriever.retrieve(query, top_k=max_k)
        retrieved_ids = [sid for sid, _ in retrieved]

        for k in k_list:
            recalls[k] += recall_at_k(retrieved_ids, gold_ids, k=k)

        mrr_total += reciprocal_rank(retrieved_ids, gold_ids)

    if valid_queries == 0:
        return {f"Recall@{k}": 0.0 for k in k_list} | {"MRR": 0.0, "total_queries": 0}

    results = {f"Recall@{k}": round(recalls[k] / valid_queries, 4) for k in k_list}
    results["MRR"] = round(mrr_total / valid_queries, 4)
    results["total_queries"] = valid_queries
    return results
