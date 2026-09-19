"""Okapi BM25 詞庫檢索器 (Lexicon BM25 Retriever)。

實作純 Python / NumPy 之 Okapi BM25 演算法，針對詞庫建構多欄位文本索引，
支援中英雙語斷詞、縮寫精確比對與詞頻-逆文檔頻率 (TF-IDF) 加權評分。
"""

import math
import re
import logging
from typing import List, Dict, Any, Tuple, Optional
import jieba

logger = logging.getLogger(__name__)


def tokenize_text(text: str) -> List[str]:
    """中英文雙語斷詞函數：混合 Jieba 斷詞與英文/數字/縮寫 Token 化。"""
    if not text:
        return []
    text_clean = text.lower().strip()
    
    # 英文與專業名詞/縮寫抽取 (如 spc, bom, python, c++, ci/cd)
    en_tokens = re.findall(r"[a-z0-9\+\#\.\-]+", text_clean)
    
    # 中文文字部分使用 jieba 斷詞
    zh_tokens = [w for w in jieba.cut(text_clean) if len(w.strip()) > 0 and not re.match(r"^[a-z0-9\+\#\.\-]+$", w)]
    
    return en_tokens + zh_tokens


class BM25Retriever:
    """以 Okapi BM25 演算法檢索既有技能詞庫之檢索器。"""

    def __init__(
        self,
        skill_id_index: Dict[str, Dict[str, Any]],
        k1: float = 1.5,
        b: float = 0.75,
    ):
        """
        Args:
            skill_id_index: 由 Skill_ID 映射至技能中英文資訊與分類字典
            k1: BM25 詞頻飽和參數 (預設 1.5)
            b: BM25 文檔長度懲罰參數 (預設 0.75)
        """
        self.skill_id_index = skill_id_index
        self.k1 = k1
        self.b = b
        
        self.skill_ids: List[str] = []
        self.corpus: List[List[str]] = []
        self.doc_lengths: List[int] = []
        self.avgdl: float = 0.0
        self.df: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}
        self.doc_term_freqs: List[Dict[str, int]] = []
        
        self._build_index()

    def _build_index(self):
        """將詞庫中每個 Skill_ID 轉換為可檢索文檔並建立倒排索引。"""
        self.skill_ids = list(self.skill_id_index.keys())
        total_len = 0

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

            # 組裝富語意文檔 (加權：名稱與關鍵字重複出現以增加權重)
            doc_str = f"{name_zh} {name_zh} {name_en} {name_en} {keywords_clean} {cat_name} {subcat_name}"
            tokens = tokenize_text(doc_str)
            self.corpus.append(tokens)
            doc_len = len(tokens)
            self.doc_lengths.append(doc_len)
            total_len += doc_len

            # 詞頻統計
            tf_dict: Dict[str, int] = {}
            for t in tokens:
                tf_dict[t] = tf_dict.get(t, 0) + 1
            self.doc_term_freqs.append(tf_dict)

            # 文檔頻率 (DF)
            for t in tf_dict.keys():
                self.df[t] = self.df.get(t, 0) + 1

        n_docs = len(self.skill_ids)
        self.avgdl = (total_len / n_docs) if n_docs > 0 else 1.0

        # 計算 IDF (加 0.5 平滑處理)
        for term, freq in self.df.items():
            self.idf[term] = math.log(((n_docs - freq + 0.5) / (freq + 0.5)) + 1.0)

        logger.info(f"BM25 索引建立完成：共索引 {n_docs} 筆詞庫項目，詞表大小 {len(self.df)}。")

    def retrieve(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """檢索與 query 最相關的 Top-K 技能項目。
        
        Args:
            query: 查詢文字（如職缺短語 "Documents creation"、"Board debug"）
            top_k: 回傳候選數量 (預設 5)
            
        Returns:
            [(skill_id, normalized_score), ...] 依照分數由高至低排序
        """
        query_tokens = tokenize_text(query)
        if not query_tokens or not self.skill_ids:
            return []

        scores: List[float] = [0.0] * len(self.skill_ids)

        for q in query_tokens:
            if q not in self.idf:
                continue
            idf_val = self.idf[q]

            for i, tf_dict in enumerate(self.doc_term_freqs):
                tf = tf_dict.get(q, 0)
                if tf == 0:
                    continue
                d_len = self.doc_lengths[i]
                numerator = tf * (self.k1 + 1.0)
                denominator = tf + self.k1 * (1.0 - self.b + self.b * (d_len / self.avgdl))
                scores[i] += idf_val * (numerator / denominator)

        # 排序並取 Top-K
        ranked_indices = sorted(range(len(scores)), key=lambda idx: scores[idx], reverse=True)
        results: List[Tuple[str, float]] = []

        max_score = scores[ranked_indices[0]] if ranked_indices and scores[ranked_indices[0]] > 0 else 1.0
        for idx in ranked_indices[:top_k]:
            raw_score = scores[idx]
            if raw_score <= 0.0:
                continue
            norm_score = min(1.0, raw_score / max_score)
            results.append((self.skill_ids[idx], round(norm_score, 4)))

        return results
