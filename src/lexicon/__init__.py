"""Lexicon package exports."""

from src.lexicon.schema import SkillEntry, CandidateSkill
from src.lexicon.loader import LexiconLoader
from src.lexicon.expander import expand_synonyms, stem_english_text, get_stemmed_term

__all__ = [
    "SkillEntry",
    "CandidateSkill",
    "LexiconLoader",
    "expand_synonyms",
    "stem_english_text",
    "get_stemmed_term",
]
