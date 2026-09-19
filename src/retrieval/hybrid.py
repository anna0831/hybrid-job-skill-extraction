"""混合式詞庫檢索器 (Hybrid BM25 + Dense Retriever)。

結合 BM25 的關鍵字/縮寫精確匹配能力，與 Dense 向量的跨語言語意泛化能力。
支援倒數排名融合 (Reciprocal Rank Fusion, RRF) 與加權分數融合，
嚴格在既有 Skill Lexicon 宇宙中檢索 Top-K 合法 Skill_ID。
"""

import logging
from typing import List, Dict, Any, Tuple, Optional
from src.retrieval.bm25 import BM25Retriever
from src.retrieval.dense import DenseRetriever

logger = logging.getLogger(__name__)


class HybridRetriever:
    """混合式技能檢索器。"""

    def __init__(
        self,
        skill_id_index: Dict[str, Dict[str, Any]],
        dense_weight: float = 0.5,
        rrf_k: int = 60,
    ):
        """
        Args:
            skill_id_index: 詞庫由 Skill_ID 映射至技能資訊字典
            dense_weight: 加權融合時 Dense 分數所佔權重 (0.0~1.0)
            rrf_k: RRF 平滑常數 (預設 60)
        """
        self.skill_id_index = skill_id_index
        self.dense_weight = dense_weight
        self.bm25_weight = 1.0 - dense_weight
        self.rrf_k = rrf_k

        self.bm25 = BM25Retriever(skill_id_index=skill_id_index)
        self.dense = DenseRetriever(skill_id_index=skill_id_index)

    def retrieve_bm25(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """單獨以 BM25 檢索 Top-K。"""
        return self.bm25.retrieve(query, top_k=top_k)

    def retrieve_dense(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """單獨以 Dense 向量檢索 Top-K。"""
        return self.dense.retrieve(query, top_k=top_k)

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        fusion_method: str = "rrf",
    ) -> List[Tuple[str, float]]:
        """執行 Hybrid 融合檢索，回傳 Top-K 候選技能。
        
        Args:
            query: 查詢短語 (如 "Documents creation")
            top_k: 回傳數量 (預設 5)
            fusion_method: "rrf" (倒數排名融合) 或 "weighted" (加權線性融合)
            
        Returns:
            [(skill_id, score), ...] 依照融合分數由高至低排序
        """
        # 各自獲取較寬的候選集合以利融合
        k_pool = max(top_k * 3, 15)
        bm25_res = self.bm25.retrieve(query, top_k=k_pool)
        dense_res = self.dense.retrieve(query, top_k=k_pool)

        if not bm25_res and not dense_res:
            return []

        all_candidate_ids = set([s_id for s_id, _ in bm25_res] + [s_id for s_id, _ in dense_res])
        combined_scores: Dict[str, float] = {}

        if fusion_method == "rrf":
            # 1. Reciprocal Rank Fusion (RRF)
            bm25_ranks = {s_id: rank + 1 for rank, (s_id, _) in enumerate(bm25_res)}
            dense_ranks = {s_id: rank + 1 for rank, (s_id, _) in enumerate(dense_res)}
            bm25_score_map = dict(bm25_res)
            dense_score_map = dict(dense_res)

            rrf_max_possible = (1.0 / (self.rrf_k + 1)) * 2.0
            for s_id in all_candidate_ids:
                rrf_score = 0.0
                if s_id in bm25_ranks:
                    rrf_score += 1.0 / (self.rrf_k + bm25_ranks[s_id])
                if s_id in dense_ranks:
                    rrf_score += 1.0 / (self.rrf_k + dense_ranks[s_id])

                rrf_norm = rrf_score / rrf_max_possible
                s_dense = dense_score_map.get(s_id, 0.0)
                s_bm25 = bm25_score_map.get(s_id, 0.0)

                # 綜合 RRF 排名與真實語意相似度計算置信分數
                if s_bm25 > 0 and s_dense > 0:
                    calibrated = 0.5 * s_dense + 0.3 * s_bm25 + 0.2 * rrf_norm
                elif s_bm25 > 0:
                    calibrated = 0.7 * s_bm25 + 0.3 * rrf_norm
                else:
                    calibrated = 0.7 * s_dense + 0.3 * rrf_norm

                combined_scores[s_id] = min(1.0, max(0.0, calibrated))

        else:
            # 2. Weighted Score Fusion
            bm25_score_map = dict(bm25_res)
            dense_score_map = dict(dense_res)

            for s_id in all_candidate_ids:
                s_bm25 = bm25_score_map.get(s_id, 0.0)
                s_dense = dense_score_map.get(s_id, 0.0)
                weighted_score = (self.bm25_weight * s_bm25) + (self.dense_weight * s_dense)
                combined_scores[s_id] = min(1.0, max(0.0, weighted_score))

        # 排序取 Top-K
        sorted_candidates = sorted(combined_scores.items(), key=lambda x: x[1], reverse=True)

        results: List[Tuple[str, float]] = []
        for s_id, score in sorted_candidates[:top_k]:
            results.append((s_id, round(score, 4)))

        return results

    def compare_retrieval(
        self, query: str, top_k: int = 5
    ) -> Dict[str, List[Tuple[str, float]]]:
        """Task 2 檢索對比：同時回傳 BM25、Dense 與 Hybrid 三種檢索結果。"""
        return {
            "bm25": self.retrieve_bm25(query, top_k=top_k),
            "dense": self.retrieve_dense(query, top_k=top_k),
            "hybrid": self.retrieve(query, top_k=top_k, fusion_method="rrf"),
        }
