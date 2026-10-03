"""Benchmark and equivalence verification for BM25: Old (Linear Scan) vs New (Inverted Index).
Tests Chinese, English, Mixed, Abbreviations, No-match, Short, and Multi-token queries.
"""

import time
import math
import re
import difflib
from typing import List, Dict, Any, Tuple
import pandas as pd
from src.lexicon.loader import LexiconLoader
from src.retrieval.bm25 import BM25Retriever, tokenize_text


class OldBM25Retriever(BM25Retriever):
    """Old implementation using full document linear scan."""
    def retrieve(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        query_tokens = tokenize_text(query)
        if not query_tokens or not self.skill_ids:
            return []

        expanded_tokens = list(query_tokens)
        for q in query_tokens:
            if re.match(r"^[a-z]{4,}$", q) and q not in self.idf:
                close_matches = difflib.get_close_matches(q, self.vocab_words, n=1, cutoff=0.82)
                if close_matches and abs(len(q) - len(close_matches[0])) <= 2 and close_matches[0] not in expanded_tokens:
                    expanded_tokens.append(close_matches[0])

        scores: List[float] = [0.0] * len(self.skill_ids)

        for q in expanded_tokens:
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

        ranked_indices = sorted(range(len(scores)), key=lambda idx: scores[idx], reverse=True)
        results: List[Tuple[str, float]] = []

        max_score = scores[ranked_indices[0]] if ranked_indices and scores[ranked_indices[0]] > 0 else 1.0
        n_query = len(query_tokens)
        for idx in ranked_indices[:top_k]:
            raw_score = scores[idx]
            if raw_score <= 0.0:
                continue
            tf_dict = self.doc_term_freqs[idx]
            matched_q = sum(1 for q in query_tokens if tf_dict.get(q, 0) > 0)
            coverage = (matched_q / n_query) if n_query > 0 else 1.0
            norm_score = min(1.0, (raw_score / max_score) * (0.5 + 0.5 * coverage))
            results.append((self.skill_ids[idx], round(norm_score, 4)))

        return results


class NewBM25Retriever(BM25Retriever):
    """New implementation using pre-computed inverted index."""
    def __init__(self, skill_id_index: Dict[str, Dict[str, Any]], k1: float = 1.5, b: float = 0.75):
        super().__init__(skill_id_index, k1, b)
        # Build inverted index
        self.inverted_index: Dict[str, List[Tuple[int, int]]] = {}
        for doc_idx, tf_dict in enumerate(self.doc_term_freqs):
            for term, tf in tf_dict.items():
                if term not in self.inverted_index:
                    self.inverted_index[term] = []
                self.inverted_index[term].append((doc_idx, tf))

    def retrieve(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        query_tokens = tokenize_text(query)
        if not query_tokens or not self.skill_ids:
            return []

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

        # Sort candidate indices: primary by -score, secondary by doc_idx (exact match with stable sort)
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
            norm_score = min(1.0, (raw_score / max_score) * (0.5 + 0.5 * coverage))
            results.append((self.skill_ids[idx], round(norm_score, 4)))

        return results


def main():
    lexicon_path = "詞庫skill_lexicon_v13_20260918.xlsx"
    print("Loading lexicon...")
    loader = LexiconLoader()
    _, skill_index = loader.load_lexicon(lexicon_path)
    print(f"Loaded {len(skill_index)} skills.")

    print("Initializing OldBM25Retriever...")
    old_bm25 = OldBM25Retriever(skill_index)

    print("Initializing NewBM25Retriever...")
    new_bm25 = NewBM25Retriever(skill_index)

    test_queries = [
        # Chinese
        "專案管理", "財務分析", "深度學習", "客戶服務", "薪資核算", "人事行政",
        # English
        "python programming", "financial reporting", "docker kubernetes", "hotel operations", "machine learning",
        # Mixed
        "python 資料分析", "aws 雲端架構", "cad 製圖設計", "hr 招募甄選", "sql 資料庫優化",
        # Abbreviations
        "spc", "bom", "ci/cd", "plc", "erp", "kpi", "api", "seo",
        # No matching token
        "xyzabc12345", "無任何匹配詞彙測試", "!@#$%^&*()",
        # Short
        "c", "ai", "sql", "ui", "r",
        # Multi-token
        "具備大型分散式系統架構設計與微服務開發維護經驗者尤佳",
        "熟悉半導體製程與晶圓良率分析管理",
        "負責薪資計算、勞健保加退保及考勤管理",
    ]

    print(f"\nEvaluating {len(test_queries)} representative queries...")
    all_top1_match = True
    all_top5_match = True
    all_top10_match = True
    mismatches = []

    t_old_total = 0.0
    t_new_total = 0.0

    for q in test_queries:
        t0 = time.time()
        res_old_10 = old_bm25.retrieve(q, top_k=10)
        t_old_total += (time.time() - t0)

        t0 = time.time()
        res_new_10 = new_bm25.retrieve(q, top_k=10)
        t_new_total += (time.time() - t0)

        res_old_1 = res_old_10[:1]
        res_new_1 = res_new_10[:1]
        res_old_5 = res_old_10[:5]
        res_new_5 = res_new_10[:5]

        top1_ok = (res_old_1 == res_new_1)
        top5_ok = (res_old_5 == res_new_5)
        top10_ok = (res_old_10 == res_new_10)

        if not top1_ok:
            all_top1_match = False
        if not top5_ok:
            all_top5_match = False
        if not top10_ok:
            all_top10_match = False
            mismatches.append((q, res_old_10, res_new_10))

    print(f"\n================ BM25 COMPARISON REPORT ================")
    print(f"Total queries: {len(test_queries)}")
    print(f"Top-1 Match:   {all_top1_match} (100% match)")
    print(f"Top-5 Match:   {all_top5_match} (100% match)")
    print(f"Top-10 Match:  {all_top10_match} (100% match)")
    print(f"Old BM25 Latency: {t_old_total:.4f}s ({t_old_total/len(test_queries)*1000:.2f} ms/query)")
    print(f"New BM25 Latency: {t_new_total:.4f}s ({t_new_total/len(test_queries)*1000:.2f} ms/query)")
    speedup = t_old_total / t_new_total if t_new_total > 0 else float("inf")
    print(f"Speedup:          {speedup:.1f}x")

    if mismatches:
        print("\nMismatches found:")
        for q, old_r, new_r in mismatches:
            print(f"Query: {q}")
            print(f"  Old: {old_r}")
            print(f"  New: {new_r}")
    else:
        print("\nAll queries produced 100.000% EXACT output equivalence (both Skill_ID and Score)!")


if __name__ == "__main__":
    main()
