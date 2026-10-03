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
    """中英文雙語斷詞函數：混合 Jieba 斷詞、2-Gram 複合詞拆解與英文/數字/縮寫 Token 化。"""
    if not text:
        return []
    text_clean = text.lower().strip()
    
    # 英文與專業名詞/縮寫抽取 (如 spc, bom, python, c++, ci/cd)
    en_tokens = re.findall(r"[a-z0-9\+\#\.\-]+", text_clean)
    
    # 中文文字部分使用 jieba 斷詞
    zh_tokens = []
    for w in jieba.cut(text_clean):
        w_clean = w.strip()
        if len(w_clean) > 0 and not re.match(r"^[a-z0-9\+\#\.\-]+$", w_clean):
            zh_tokens.append(w_clean)
            if len(w_clean) >= 4:
                # 複合中文名詞加入 2-gram 子詞 (例如 品質管理 -> 品質, 管理)
                zh_tokens.append(w_clean[:2])
                zh_tokens.append(w_clean[-2:])
    
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
        self.vocab_words: List[str] = []
        
        self._build_index()

    def _build_index(self):
        """將詞庫中每個 Skill_ID 轉換為標準規範化文檔並建立倒排索引。"""
        self.skill_ids = list(self.skill_id_index.keys())
        total_len = 0

        for skill_id in self.skill_ids:
            info = self.skill_id_index[skill_id]
            name_zh = (info.get("SKILL_NAME_ZH", "") or "").strip()
            name_en = (info.get("SKILL_NAME", "") or "").strip()
            keywords = (info.get("KEYWORDS", "") or "").strip()
            if isinstance(keywords, str):
                keywords_clean = " ".join(k.strip() for k in keywords.replace("｜", " ").split() if k.strip())
            else:
                keywords_clean = ""
            cat_name = (info.get("SKILL_CATEGORY_NAME", "") or "").strip()
            subcat_name = (info.get("SKILL_SUBCATEGORY_NAME", "") or "").strip()
            cat_full = f"{cat_name} {subcat_name}".strip()

            # 規範化檢索文檔表示 (Canonical Document Representation)
            doc_str = f"{name_en} | {name_zh} | {keywords_clean} | {cat_full}"
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

        # 收集技術英文詞庫供通用錯字校正
        self.vocab_words = [w for w in self.df.keys() if re.match(r"^[a-z]{3,}$", w)]

        # 倒排索引：token -> List[Tuple[doc_idx, tf]]
        self.inverted_index: Dict[str, List[Tuple[int, int]]] = {}
        for doc_idx, tf_dict in enumerate(self.doc_term_freqs):
            for term, tf in tf_dict.items():
                if term not in self.inverted_index:
                    self.inverted_index[term] = []
                self.inverted_index[term].append((doc_idx, tf))

        logger.info(f"BM25 索引建立完成：共索引 {n_docs} 筆詞庫項目，詞表大小 {len(self.df)}。")

    def retrieve(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """檢索與 query 最相關的 Top-K 技能項目。
        
        Args:
            query: 查詢文字（如職缺短語 "Documents creation"、"Board debug"）
            top_k: 回傳候選數量 (預設 5)
            
        Returns:
            [(skill_id, normalized_score), ...] 依照分數由高至低排序
        """
        import difflib
        query_tokens = tokenize_text(query)
        if not query_tokens or not self.skill_ids:
            return []

        # 英文專業詞彙輕量錯字校正 (General Typo Correction)
        expanded_tokens = list(query_tokens)
        for q in query_tokens:
            if re.match(r"^[a-z]{4,}$", q) and q not in self.idf:
                close_matches = difflib.get_close_matches(q, self.vocab_words, n=1, cutoff=0.82)
                if close_matches and abs(len(q) - len(close_matches[0])) <= 2 and close_matches[0] not in expanded_tokens:
                    expanded_tokens.append(close_matches[0])

        scores: Dict[int, float] = {}

        for q in expanded_tokens:
            if q not in self.idf:
                continue
            idf_val = self.idf[q]
            postings = self.inverted_index.get(q)
            if not postings:
                continue

            for doc_idx, tf in postings:
                d_len = self.doc_lengths[doc_idx]
                numerator = tf * (self.k1 + 1.0)
                denominator = tf + self.k1 * (1.0 - self.b + self.b * (d_len / self.avgdl))
                score_delta = idf_val * (numerator / denominator)
                scores[doc_idx] = scores.get(doc_idx, 0.0) + score_delta

        if not scores:
            return []

        # 排序候選文檔：依分數降序，同分依原始 doc_idx 升序（確保與原本穩定排序 100% 一致）
        ranked_candidates = sorted(scores.keys(), key=lambda idx: (-scores[idx], idx))
        max_score = scores[ranked_candidates[0]] if scores[ranked_candidates[0]] > 0 else 1.0
        n_query = len(query_tokens)

        results: List[Tuple[str, float]] = []
        for idx in ranked_candidates[:top_k]:
            raw_score = scores[idx]
            if raw_score <= 0.0:
                continue
            tf_dict = self.doc_term_freqs[idx]
            matched_q = sum(1 for q in query_tokens if tf_dict.get(q, 0) > 0)
            coverage = (matched_q / n_query) if n_query > 0 else 1.0
            # 依查詢詞覆蓋率適度衰減，避免僅單一通用詞命中卻得到 1.0 過高置信度
            norm_score = min(1.0, (raw_score / max_score) * (0.5 + 0.5 * coverage))
            results.append((self.skill_ids[idx], round(norm_score, 4)))

        return results
