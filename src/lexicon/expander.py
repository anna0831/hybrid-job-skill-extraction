"""詞庫擴充與正規化工具：同義詞展開與英文詞幹提取。"""

import re
from typing import List, Set, Collection
from nltk.stem import PorterStemmer

_stemmer = PorterStemmer()


def expand_synonyms(term: str, synonym_groups: List[Collection[str]]) -> Set[str]:
    """回傳輸入詞彙套用同義詞字典後，能生成的所有變體字串（不包含自身）。"""
    variants: Set[str] = set()
    for group in synonym_groups:
        for m in group:
            if m in term:
                for m2 in group:
                    if m2 != m:
                        variants.add(term.replace(m, m2))
    variants.discard(term)
    return variants


def stem_english_text(text: str) -> str:
    """將文字中的所有英文單字替換為其詞幹 (Porter Stemmer)。"""
    return re.sub(r"[a-z]+", lambda m: _stemmer.stem(m.group()), text)


def get_stemmed_term(term: str, min_len: int = 7) -> str:
    """取得英文詞條詞幹。
    
    若詞幹長度小於 min_len（例如 7）則回傳原字串，防止短詞幹過度泛化。
    """
    stemmed = _stemmer.stem(term)
    if stemmed != term and len(stemmed) >= min_len:
        return stemmed
    return term
