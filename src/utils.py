"""
Utility functions for CardioKB.

Includes helpers for loading ontologies, filtering data, and common operations.
"""

import functools
import os
from pathlib import Path
from typing import FrozenSet, List, Set


def load_cvd_terms(ontology_file: str = None) -> FrozenSet[str]:
    """
    Load cardiovascular disease terms from the ontology file.

    Results are cached after the first call (when using the default ontology file).

    Args:
        ontology_file: Path to the CVD terms file. If None, uses default location.

    Returns:
        FrozenSet of lowercase CVD terms for case-insensitive matching.
    """
    if ontology_file is None:
        # Default location: ontology/cvd_disease_hierarchy.txt
        project_root = Path(__file__).parent.parent
        ontology_file = project_root / "ontology" / "cvd_disease_hierarchy.txt"

    return _load_cvd_terms_cached(str(ontology_file))


@functools.lru_cache(maxsize=4)
def _load_cvd_terms_cached(ontology_file: str) -> FrozenSet[str]:
    """Cached implementation of CVD term loading."""
    cvd_terms = set()

    try:
        with open(ontology_file, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if line and not line.startswith('#'):
                    cvd_terms.add(line.lower())

        return frozenset(cvd_terms)

    except FileNotFoundError:
        # Fallback to hardcoded terms if file not found
        return frozenset({
            'cardiovascular', 'cardiac', 'heart', 'coronary', 'myocardial',
            'atherosclerosis', 'hypertension', 'arrhythmia', 'cardiomyopathy',
            'heart failure', 'atrial fibrillation', 'stroke', 'thrombosis',
            'angina', 'ischemic heart disease', 'ventricular', 'atrial'
        })


def get_cvd_search_pattern() -> str:
    """
    Get a regex search pattern for all CVD terms.

    Returns:
        String pattern suitable for pandas str.contains() or regex matching.
    """
    cvd_terms = load_cvd_terms()
    # Escape special regex characters and join with OR
    escaped_terms = [term.replace(' ', r'\s+') for term in cvd_terms]
    return '|'.join(escaped_terms)


def is_cardiovascular_related(text: str, cvd_terms: Set[str] = None) -> bool:
    """
    Check if text contains cardiovascular-related terms.

    Args:
        text: Text to check
        cvd_terms: Set of CVD terms (loaded automatically if None)

    Returns:
        True if text contains any CVD term, False otherwise.
    """
    if cvd_terms is None:
        cvd_terms = load_cvd_terms()

    text_lower = text.lower()
    return any(term in text_lower for term in cvd_terms)
