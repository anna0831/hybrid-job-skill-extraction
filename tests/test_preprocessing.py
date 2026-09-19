"""Tests for text preprocessing and boundary checking."""

import pytest
from src.preprocessing.boundary import (
    has_chinese,
    get_zh_boundaries,
    is_word_boundary,
)
from src.preprocessing.enumerator import expand_enumeration
from src.lexicon.expander import expand_synonyms, get_stemmed_term


def test_has_chinese():
    assert has_chinese("Python工程師") is True
    assert has_chinese("Python Engineer") is False
    assert has_chinese("12345!@#") is False


def test_get_zh_boundaries():
    text = "軟體開發與資料庫"
    boundaries = get_zh_boundaries(text)
    assert 0 in boundaries
    assert len(text) in boundaries


def test_is_word_boundary():
    text = "expert in python backend"
    # "python" is at index 10 to 16
    start = text.index("python")
    end = start + len("python")
    assert is_word_boundary(text, start, end) is True

    # Embedded word (e.g. "cpython") should fail
    text2 = "cpython"
    start2 = text2.index("python")
    end2 = start2 + len("python")
    assert is_word_boundary(text2, start2, end2) is False


def test_expand_enumeration_shared_suffix():
    text = "日常業務包括車輛加油.洗車.清潔等工作"
    expanded = expand_enumeration(text)
    assert "加油作業" in expanded or "清潔" in expanded


def test_expand_enumeration_hair_salon():
    text = "本店誠徵美髮師，提供剪、染、洗服務"
    expanded = expand_enumeration(text)
    assert "剪髮" in expanded
    assert "染髮" in expanded
    assert "洗髮" in expanded


def test_expand_synonyms():
    groups = [{"老師", "教師"}, {"打掃", "清潔"}]
    variants = expand_synonyms("環境打掃", groups)
    assert "環境清潔" in variants


def test_stem_english_text():
    assert get_stemmed_term("developer", min_len=7) == "develop"
    # Short words below threshold should not be stemmed
    assert get_stemmed_term("act", min_len=7) == "act"
