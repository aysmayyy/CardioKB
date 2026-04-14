"""
Run DisGeNET for all 5 disease filters sequentially, appending edges to
Neo4j and tagging each with disease_scope.

All other parsers are already loaded — this script ONLY touches DisGeNET.

Usage:
    python scripts/run_multi_disease.py
"""

import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-7s | %(name)s | %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/cardiokb_multi_disease.log', mode='w'),
    ],
)
logger = logging.getLogger('multi_disease')

DISEASE_FILTERS = {
    'cvd': 'ontology/diseases/cvd.txt',
    'alzheimers': 'ontology/diseases/alzheimers.txt',
    'cancer': 'ontology/diseases/cancer.txt',
    'asthma': 'ontology/diseases/asthma.txt',
    'diabetes': 'ontology/diseases/diabetes.txt',
}


def run_disgenet_for_disease(disease_key: str, disease_filter_path: str):
    """Run DisGeNET for one disease filter -> parse -> load into Neo4j -> tag."""
    from src.parsers.disgenet_parser import DisGeNETParser
    from src.memgraph_loader import Neo4jLoader
    from src.ontology_configs import ONTOLOGY_CONFIGS

    api_key = os.getenv('DISGENET_API_KEY')
    if not api_key:
        logger.error("DISGENET_API_KEY not set")
        return 0

    logger.info(f"{'=' * 60}")
    logger.info(f"DisGeNET: {disease_key} ({disease_filter_path})")
    logger.info(f"{'=' * 60}")

    # Separate data dir per disease so cached files don't collide
    data_dir = f'data/raw/disgenet_{disease_key}'
    os.makedirs(data_dir, exist_ok=True)

    parser = DisGeNETParser(
        data_dir=data_dir,
        api_key=api_key,
        disease_filter=disease_filter_path,
    )

    # Download via API
    logger.info(f"[{disease_key}] Querying DisGeNET API...")
    if not parser.download_data():
        logger.error(f"[{disease_key}] Download failed")
        return 0

    # Parse
    parsed = parser.parse_data()
    if not parsed:
        logger.error(f"[{disease_key}] No data parsed")
        return 0

    gda = parsed.get('gene_disease_associations')
    diseases = parsed.get('diseases')
    gda_count = len(gda) if gda is not None else 0
    disease_count = len(diseases) if diseases is not None else 0
    logger.info(f"[{disease_key}] {gda_count} gene-disease associations, {disease_count} diseases")

    if gda_count == 0:
        logger.warning(f"[{disease_key}] No associations, skipping")
        return 0

    # Export TSVs
    out_dir = Path(f'data/processed/disgenet_{disease_key}')
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in parsed.items():
        df.to_csv(out_dir / f'{name}.tsv', sep='\t', index=False)

    # Load into Neo4j
    uri = os.getenv('MEMGRAPH_URI', 'bolt://localhost:7687')
    username = os.getenv('MEMGRAPH_USERNAME', '')
    password = os.getenv('MEMGRAPH_PASSWORD', '')
    if not password:
        logger.error("MEMGRAPH_PASSWORD not set")
        return 0

    with Neo4jLoader(uri, username, password) as loader:
        # Disease nodes (custom DOID-aware merge)
        if diseases is not None and len(diseases) > 0:
            counts = loader.load_disgenet_diseases(diseases)
            logger.info(f"[{disease_key}] Disease nodes: {counts}")

        # Gene-disease edges via ontology config
        rel_config = ONTOLOGY_CONFIGS.get('disgenet.gene_disease_associations')
        if rel_config and gda is not None and len(gda) > 0:
            loader._load_relationships(gda, rel_config,
                                       'disgenet.gene_disease_associations')

        # Tag edges with disease_scope
        _tag_edges(loader, disease_key, gda)

    return gda_count


def _tag_edges(loader, disease_key, gda_df):
    """Set disease_scope on the DisGeNET edges just loaded."""
    import pandas as pd

    if gda_df is None or len(gda_df) == 0:
        return

    # Same filter as ontology config
    if 'diseaseType' in gda_df.columns:
        gda_df = gda_df[gda_df['diseaseType'] == 'disease']

    pairs = gda_df[['geneSymbol', 'diseaseId']].dropna().drop_duplicates()
    rows = pairs.to_dict('records')

    # Accumulate scopes as comma-separated string so edges shared across
    # filters get all labels (e.g. "cvd,diabetes")
    query = (
        "UNWIND $rows AS row "
        "MATCH (g:Gene {geneSymbol: row.geneSymbol})"
        "-[r:geneAssociatesWithDisease]->"
        "(d:Disease {xrefUmlsCUI: row.diseaseId}) "
        "WHERE r.source = 'DisGeNET' "
        "SET r.disease_scope = CASE "
        "  WHEN r.disease_scope IS NULL THEN $scope "
        "  WHEN r.disease_scope CONTAINS $scope THEN r.disease_scope "
        "  ELSE r.disease_scope + ',' + $scope "
        "END"
    )

    batch_size = 1000
    with loader.driver.session() as session:
        for i in range(0, len(rows), batch_size):
            session.run(query, rows=rows[i:i + batch_size], scope=disease_key)

    logger.info(f"[{disease_key}] Tagged {len(rows)} edges with disease_scope='{disease_key}'")


def report_stats():
    """Print final Neo4j graph stats."""
    from neo4j import GraphDatabase

    uri = os.getenv('MEMGRAPH_URI', 'bolt://localhost:7687')
    username = os.getenv('MEMGRAPH_USERNAME', '')
    password = os.getenv('MEMGRAPH_PASSWORD', '')
    if not password:
        return

    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        with driver.session() as s:
            total_nodes = s.run("MATCH (n) RETURN count(n) AS c").single()['c']
            total_rels = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()['c']

            node_counts = {}
            for label in [r['l'][0] for r in s.run("MATCH (n) RETURN DISTINCT labels(n) AS l") if r['l']]:
                cnt = s.run(f"MATCH (n:{label}) RETURN count(n) AS c").single()['c']
                if cnt > 0:
                    node_counts[label] = cnt

            rel_counts = {}
            for rt in [r['rt'] for r in s.run(
                "MATCH ()-[r]->() RETURN DISTINCT type(r) AS rt"
            )]:
                cnt = s.run(f"MATCH ()-[r:`{rt}`]->() RETURN count(r) AS c").single()['c']
                if cnt > 0:
                    rel_counts[rt] = cnt

            scope_counts = {}
            for rec in s.run(
                "MATCH ()-[r:geneAssociatesWithDisease]->() "
                "WHERE r.source = 'DisGeNET' AND r.disease_scope IS NOT NULL "
                "RETURN r.disease_scope AS scope, count(r) AS c ORDER BY c DESC"
            ):
                scope_counts[rec['scope']] = rec['c']

        logger.info(f"\n{'=' * 60}")
        logger.info("FINAL GRAPH STATS")
        logger.info(f"{'=' * 60}")
        logger.info(f"Total nodes:         {total_nodes:>12,}")
        logger.info(f"Total relationships: {total_rels:>12,}")
        logger.info(f"Node types:          {len(node_counts):>12}")
        logger.info(f"Relationship types:  {len(rel_counts):>12}")

        logger.info(f"\nNode counts:")
        for label, cnt in sorted(node_counts.items(), key=lambda x: -x[1]):
            logger.info(f"  {label:30s} {cnt:>12,}")

        logger.info(f"\nRelationship counts:")
        for rt, cnt in sorted(rel_counts.items(), key=lambda x: -x[1]):
            logger.info(f"  {rt:45s} {cnt:>12,}")

        if scope_counts:
            logger.info(f"\nDisGeNET edges by disease_scope:")
            for scope, cnt in scope_counts.items():
                logger.info(f"  {scope:30s} {cnt:>8,}")

    finally:
        driver.close()


def main():
    start = time.time()

    results = {}
    for key, path in DISEASE_FILTERS.items():
        t0 = time.time()
        edges = run_disgenet_for_disease(key, path)
        elapsed = time.time() - t0
        results[key] = {'edges': edges, 'time': f'{elapsed:.1f}s'}
        logger.info(f"[{key}] {edges} edges in {elapsed:.1f}s\n")

    logger.info(f"\n{'=' * 60}")
    logger.info("DisGeNET per-disease summary:")
    logger.info(f"{'=' * 60}")
    total = 0
    for key, r in results.items():
        logger.info(f"  {key:15s}: {r['edges']:>8,} edges  ({r['time']})")
        total += r['edges']
    logger.info(f"  {'TOTAL':15s}: {total:>8,} edges")

    report_stats()

    logger.info(f"\nTotal elapsed: {(time.time() - start) / 60:.1f} minutes")


if __name__ == '__main__':
    main()
