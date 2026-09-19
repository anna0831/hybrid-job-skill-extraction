"""AC Matcher package exports."""

from src.ac_matcher.engine import ACMatcher
from src.ac_matcher.suppression import suppress_shorter_matches

__all__ = ["ACMatcher", "suppress_shorter_matches"]
