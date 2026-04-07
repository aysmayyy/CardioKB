"""
Utility functions for CardioKB.

Includes helpers for loading disease term ontologies, filtering data,
disease cache management, and common operations.
"""

import functools
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Set

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


# ---------------------------------------------------------------------------
# Disease Cache — tracks which disease filters have been loaded into Neo4j
# ---------------------------------------------------------------------------

def _get_neo4j_driver():
    """Create a Neo4j driver from env vars. Returns None if password unset."""
    from neo4j import GraphDatabase
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    username = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', '')
    if not password:
        return None
    return GraphDatabase.driver(uri, auth=(username, password))


def check_disease_cache(disease_name: str) -> Optional[Dict]:
    """
    Check if a disease filter has already been loaded into Neo4j.

    Searches by disease_name (exact) first, then checks aliases.

    Args:
        disease_name: Short key like 'cvd', 'alzheimers', etc.

    Returns:
        Dict with cache properties if found, None otherwise.
    """
    driver = _get_neo4j_driver()
    if not driver:
        return None

    try:
        with driver.session() as session:
            # Try exact match on disease_name first
            rec = session.run(
                "MATCH (c:DiseaseCache {disease_name: $name}) "
                "RETURN c.disease_name AS disease_name, "
                "       c.canonical_name AS canonical_name, "
                "       c.aliases AS aliases, "
                "       c.filter_file AS filter_file, "
                "       c.disgenet_rows AS disgenet_rows, "
                "       c.date_loaded AS date_loaded, "
                "       c.sources_loaded AS sources_loaded",
                name=disease_name,
            ).single()
            if rec is not None:
                return dict(rec)

            # Try alias match (case-insensitive)
            rec = session.run(
                "MATCH (c:DiseaseCache) "
                "WHERE any(a IN c.aliases WHERE toLower(a) = toLower($name)) "
                "RETURN c.disease_name AS disease_name, "
                "       c.canonical_name AS canonical_name, "
                "       c.aliases AS aliases, "
                "       c.filter_file AS filter_file, "
                "       c.disgenet_rows AS disgenet_rows, "
                "       c.date_loaded AS date_loaded, "
                "       c.sources_loaded AS sources_loaded",
                name=disease_name,
            ).single()
            if rec is not None:
                return dict(rec)

            return None
    finally:
        driver.close()


def add_to_disease_cache(disease_name: str, stats: Dict) -> Dict:
    """
    Create or update a DiseaseCache node in Neo4j.

    Args:
        disease_name: Short key like 'cvd', 'alzheimers', etc.
        stats: Dict with optional keys:
            - filter_file (str): path to the disease filter file
            - disgenet_rows (int): number of DisGeNET edges loaded
            - sources_loaded (list[str]): list of source names loaded
            - canonical_name (str): standardized disease name
            - aliases (list[str]): user inputs that resolve to this entry

    Returns:
        Dict with the stored cache properties.
    """
    driver = _get_neo4j_driver()
    if not driver:
        raise RuntimeError("NEO4J_PASSWORD not set — cannot write cache")

    try:
        with driver.session() as session:
            # Ensure uniqueness constraint exists (idempotent in Memgraph)
            try:
                session.run(
                    "CREATE CONSTRAINT ON (c:DiseaseCache) "
                    "ASSERT c.disease_name IS UNIQUE"
                )
            except Exception:
                pass  # Constraint already exists

            rec = session.run(
                "MERGE (c:DiseaseCache {disease_name: $name}) "
                "SET c.canonical_name = $canonical_name, "
                "    c.filter_file    = $filter_file, "
                "    c.disgenet_rows  = $disgenet_rows, "
                "    c.date_loaded    = $date_loaded, "
                "    c.sources_loaded = $sources_loaded "
                "RETURN c.disease_name AS disease_name, "
                "       c.canonical_name AS canonical_name, "
                "       c.aliases AS aliases, "
                "       c.filter_file AS filter_file, "
                "       c.disgenet_rows AS disgenet_rows, "
                "       c.date_loaded AS date_loaded, "
                "       c.sources_loaded AS sources_loaded",
                name=disease_name,
                canonical_name=stats.get('canonical_name', disease_name),
                filter_file=stats.get('filter_file', ''),
                disgenet_rows=stats.get('disgenet_rows', 0),
                date_loaded=datetime.now().isoformat(),
                sources_loaded=stats.get('sources_loaded', []),
            ).single()

            # Append aliases (additive, deduplicated via plain Cypher)
            new_aliases = [a.lower() for a in stats.get('aliases', []) if a]
            if new_aliases:
                for alias in new_aliases:
                    session.run(
                        "MATCH (c:DiseaseCache {disease_name: $name}) "
                        "WHERE NOT toLower($alias) IN "
                        "  [x IN coalesce(c.aliases, []) | toLower(x)] "
                        "SET c.aliases = coalesce(c.aliases, []) + [$alias]",
                        name=disease_name,
                        alias=alias,
                    )
                # Re-read to get updated aliases
                rec = session.run(
                    "MATCH (c:DiseaseCache {disease_name: $name}) "
                    "RETURN c.disease_name AS disease_name, "
                    "       c.canonical_name AS canonical_name, "
                    "       c.aliases AS aliases, "
                    "       c.filter_file AS filter_file, "
                    "       c.disgenet_rows AS disgenet_rows, "
                    "       c.date_loaded AS date_loaded, "
                    "       c.sources_loaded AS sources_loaded",
                    name=disease_name,
                ).single()

            return dict(rec)
    finally:
        driver.close()


def delete_disease_cache(disease_name: str) -> bool:
    """
    Delete a DiseaseCache node by disease_name.

    Returns True if a node was deleted, False otherwise.
    """
    driver = _get_neo4j_driver()
    if not driver:
        return False

    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (c:DiseaseCache {disease_name: $name}) "
                "DELETE c RETURN count(*) AS deleted",
                name=disease_name,
            )
            rec = result.single()
            return (rec['deleted'] > 0) if rec else False
    finally:
        driver.close()


def add_alias_to_disease_cache(disease_name: str, alias: str) -> None:
    """
    Append an alias to an existing DiseaseCache node.

    Uses plain Cypher list operations (no APOC dependency).
    """
    driver = _get_neo4j_driver()
    if not driver:
        return

    try:
        with driver.session() as session:
            session.run(
                "MATCH (c:DiseaseCache {disease_name: $name}) "
                "WHERE NOT toLower($alias) IN "
                "  [x IN coalesce(c.aliases, []) | toLower(x)] "
                "SET c.aliases = coalesce(c.aliases, []) + [toLower($alias)]",
                name=disease_name,
                alias=alias,
            )
    finally:
        driver.close()
