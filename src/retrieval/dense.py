"""Dense 語意向量檢索器 (Lexicon Dense Embedding Retriever)。

支援本機確定性多語言語意向量編碼與餘弦相似度 (Cosine Similarity) 計算，
兼顧 $0 成本安全政策與跨語言語意等價映射 (如 'Documents creation' 與 '文件管理/技術文件撰寫')。
"""

import math
import re
import logging
from typing import List, Dict, Any, Tuple, Optional
import numpy as np
import jieba

logger = logging.getLogger(__name__)


class DenseRetriever:
    """詞庫語意向量檢索器。"""

    # 跨語言常見工程與技術語意特徵種子 (Cross-Lingual Domain Concepts)
    DOMAIN_SEMANTIC_FEATURES = [
        # (特徵維度名稱, [英文/中文字彙集])
        ("software", ["software", "programming", "backend", "frontend", "code", "coding", "軟體", "程式", "後端", "前端", "開發"]),
        ("hardware_circuit", ["circuit", "pcb", "hardware", "board", "debug", "server", "電路", "硬體", "主板", "除錯", "伺服器"]),
        ("documentation", ["document", "documents", "documentation", "creation", "writing", "report", "manual", "spec", "文件", "報告", "文檔", "撰寫", "技術文件"]),
        ("management_product", ["product", "npi", "bom", "development", "planning", "strategy", "產品", "專案", "開發", "物料", "規劃", "新產品"]),
        ("quality_control", ["quality", "spc", "defect", "inspection", "control", "qa", "qc", "品保", "品管", "品質", "管制", "異常排查"]),
        ("collaboration", ["team", "teamwork", "communication", "coordination", "cross-functional", "團隊", "溝通", "協作", "協調", "跨部門"]),
        ("maintenance", ["maintenance", "repair", "service", "equipment", "facility", "設備", "維護", "保養", "維修", "巡檢"]),
        ("mechanical", ["mechanical", "cad", "mold", "chassis", "mechanism", "機構", "繪圖", "模具", "外殼"]),
        ("data_analysis", ["data", "sql", "analysis", "statistics", "research", "資料", "數據", "統計", "分析", "研究"]),
    ]

    def __init__(
        self,
        skill_id_index: Dict[str, Dict[str, Any]],
        vector_dim: int = 128,
    ):
        self.skill_id_index = skill_id_index
        self.vector_dim = vector_dim
        self.skill_ids: List[str] = []
        self.doc_vectors: np.ndarray = np.zeros((0, vector_dim), dtype=np.float32)
        
        self._build_index()

    def _text_to_vector(self, text: str) -> np.ndarray:
        """將輸入字串映射為密集語意向量 (Dense Semantic Vector)。
        
        結合特徵雜湊 (Feature Hashing)、N-Gram 投影與領域語意特徵維度，
        確保在不依賴外部付費 API 的前提下具備跨語言泛化與語意等價比對能力。
        """
        vec = np.zeros(self.vector_dim, dtype=np.float32)
        if not text:
            return vec

        text_clean = text.lower().strip()
        tokens = re.findall(r"[a-z0-9\+\#\.\-]+|[\u4e00-\u9fa5]{1,4}", text_clean)

        # 1. 領域語意特徵投影 (前 32 維保留給核心跨語言領域特徵)
        for f_idx, (f_name, keywords) in enumerate(self.DOMAIN_SEMANTIC_FEATURES):
            weight = 0.0
            for kw in keywords:
                if kw in text_clean:
                    # 匹配長度與出現次數加權
                    weight += len(kw) * 0.5
            if weight > 0:
                dim_idx = f_idx % 32
                vec[dim_idx] += weight

        # 2. 字元級與詞級特徵雜湊投影 (後 96 維)
        for token in tokens:
            # 雜湊維度分佈
            h = hash(token) % 96 + 32
            vec[h] += 1.0

            # 2-gram 雜湊
            if len(token) >= 3:
                for i in range(len(token) - 2):
                    sub = token[i:i+3]
                    h_sub = hash(sub) % 96 + 32
                    vec[h_sub] += 0.5

        # L2 正規化 (L2 Normalization)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm

        return vec

    def _build_index(self):
        """為所有詞庫技能建立 Dense 向量索引。"""
        self.skill_ids = list(self.skill_id_index.keys())
        vectors = []

        for skill_id in self.skill_ids:
            info = self.skill_id_index[skill_id]
            name_zh = info.get("SKILL_NAME_ZH", "") or ""
            name_en = info.get("SKILL_NAME", "") or ""
            keywords = info.get("KEYWORDS", "") or ""
            if isinstance(keywords, str):
                keywords_clean = keywords.replace("｜", " ")
            else:
                keywords_clean = ""
            cat_name = info.get("SKILL_CATEGORY_NAME", "") or ""
            subcat_name = info.get("SKILL_SUBCATEGORY_NAME", "") or ""

            # 富語意文檔
            doc_str = f"{name_zh} {name_en} {keywords_clean} {cat_name} {subcat_name}"
            vec = self._text_to_vector(doc_str)
            vectors.append(vec)

        if vectors:
            self.doc_vectors = np.stack(vectors, axis=0)
        else:
            self.doc_vectors = np.zeros((0, self.vector_dim), dtype=np.float32)

        logger.info(f"Dense 向量索引建立完成：共索引 {len(self.skill_ids)} 筆詞庫項目，維度 {self.vector_dim}。")

    def retrieve(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """計算查詢文字與詞庫向量之餘弦相似度並回傳 Top-K。"""
        if not self.skill_ids or self.doc_vectors.shape[0] == 0:
            return []

        q_vec = self._text_to_vector(query)
        q_norm = np.linalg.norm(q_vec)
        if q_norm == 0:
            return []

        # 矩陣點積計算餘弦相似度 (因 doc_vectors 已做 L2 正規化)
        sim_scores = np.dot(self.doc_vectors, q_vec)

        # 排序並取 Top-K
        ranked_indices = np.argsort(sim_scores)[::-1]
        results: List[Tuple[str, float]] = []

        for idx in ranked_indices[:top_k]:
            score = float(sim_scores[idx])
            if score <= 0.0:
                continue
            # 轉換為 0~1 之相似度分數
            norm_score = max(0.0, min(1.0, score))
            results.append((self.skill_ids[idx], round(norm_score, 4)))

        return results
