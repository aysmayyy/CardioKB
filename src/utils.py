"""
Utility functions for CardioKB.

Includes helpers for loading disease term ontologies, filtering data,
and common operations.
"""

import functools
import os
from pathlib import Path
from typing import FrozenSet, List, Set

# Default disease filter: CVD
_DEFAULT_DISEASE_FILTER = "ontology/disease_filter.txt"


def _resolve_disease_filter(disease_filter: str = None) -> str:
    """Resolve a disease filter path to an absolute path."""
    if disease_filter is None:
        disease_filter = _DEFAULT_DISEASE_FILTER
    path = Path(disease_filter)
    if not path.is_absolute():
        project_root = Path(__file__).parent.parent
        path = project_root / disease_filter
    return str(path)


def load_disease_terms(disease_filter: str = None) -> FrozenSet[str]:
    """
    Load disease terms from a filter file.

    Results are cached per unique file path.

    Args:
        disease_filter: Path to the disease terms file (absolute or relative
            to project root). Defaults to ontology/diseases/cvd.txt.

    Returns:
        FrozenSet of lowercase disease terms for case-insensitive matching.
    """
    resolved = _resolve_disease_filter(disease_filter)
    return _load_terms_cached(resolved)


@functools.lru_cache(maxsize=8)
def _load_terms_cached(terms_file: str) -> FrozenSet[str]:
    """Cached implementation of disease term loading."""
    terms = set()

    with open(terms_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                terms.add(line.lower())

    if not terms:
        raise ValueError(f"No disease terms found in {terms_file}")

    return frozenset(terms)


def get_disease_search_pattern(disease_filter: str = None) -> str:
    """
    Get a regex search pattern for all terms in a disease filter file.

    Args:
        disease_filter: Path to the disease terms file. Defaults to CVD.

    Returns:
        String pattern suitable for pandas str.contains() or regex matching.
    """
    terms = load_disease_terms(disease_filter)
    escaped_terms = [term.replace(' ', r'\s+') for term in terms]
    return '|'.join(escaped_terms)


def is_disease_related(text: str, disease_filter: str = None,
                       terms: Set[str] = None) -> bool:
    """
    Check if text contains any term from a disease filter file.

    Args:
        text: Text to check
        disease_filter: Path to disease terms file. Defaults to CVD.
        terms: Pre-loaded set of terms (skips file loading if provided).

    Returns:
        True if text contains any disease term, False otherwise.
    """
    if terms is None:
        terms = load_disease_terms(disease_filter)

    text_lower = text.lower()
    return any(term in text_lower for term in terms)


# Backward-compatible aliases — existing code can keep calling these
load_cvd_terms = load_disease_terms
get_cvd_search_pattern = get_disease_search_pattern
is_cardiovascular_related = is_disease_related
