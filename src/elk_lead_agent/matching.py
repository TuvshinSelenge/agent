"""Keyword matching and categorization helpers."""

from __future__ import annotations

from .config import Config


def _normalize(text: str) -> str:
    return text.casefold()


def matched_terms(text: str, terms: tuple[str, ...] | list[str]) -> list[str]:
    """Return every term (case-insensitive) that appears as a substring in ``text``."""
    haystack = _normalize(text)
    return [t for t in terms if _normalize(t) in haystack]


def find_categories(text: str, config: Config) -> tuple[list[str], list[str]]:
    """Return ``(keys, labels)`` for every category whose keywords appear in ``text``."""
    keys: list[str] = []
    labels: list[str] = []
    for key, category in config.categories.items():
        if matched_terms(text, category.keywords):
            keys.append(key)
            labels.append(category.label)
    return keys, labels


def mentions_timber_or_modular(text: str, config: Config) -> bool:
    return bool(matched_terms(text, config.timber_keywords))


def submission_imminent(text: str, config: Config) -> bool:
    return bool(matched_terms(text, config.submission_keywords))


def matches_search_terms(text: str, config: Config) -> bool:
    return bool(matched_terms(text, config.search_terms))
