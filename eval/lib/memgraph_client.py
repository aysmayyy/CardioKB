"""Memgraph client for evaluation scripts."""

import os
from contextlib import contextmanager
from typing import Any, Generator

from neo4j import GraphDatabase, Driver


def get_connection_params() -> tuple[str, str, str]:
    """Get Memgraph connection parameters from environment."""
    uri = os.environ.get("MEMGRAPH_URI", "bolt://localhost:7687")
    username = os.environ.get("MEMGRAPH_USERNAME", "")
    password = os.environ.get("MEMGRAPH_PASSWORD", "")
    return uri, username, password


@contextmanager
def memgraph_driver() -> Generator[Driver, None, None]:
    """Context manager for Memgraph driver connection."""
    uri, username, password = get_connection_params()
    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        driver.verify_connectivity()
        yield driver
    finally:
        driver.close()


def run_query(driver: Driver, query: str, params: dict | None = None) -> list[dict[str, Any]]:
    """Execute a Cypher query and return results as list of dicts."""
    with driver.session() as session:
        result = session.run(query, params or {})
        return [dict(record) for record in result]


def run_query_single(driver: Driver, query: str, params: dict | None = None) -> Any:
    """Execute a query expected to return a single value."""
    results = run_query(driver, query, params)
    if results and len(results) == 1:
        values = list(results[0].values())
        if len(values) == 1:
            return values[0]
    return results[0] if results else None
