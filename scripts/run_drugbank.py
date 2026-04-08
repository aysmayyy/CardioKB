#!/usr/bin/env python
"""
Standalone script to run the DrugBank parser and load into Neo4j.

Parses drug data from the full database XML, exports TSVs,
and loads into Neo4j to enrich existing Drug nodes with DrugBank IDs.

Usage:
    python scripts/run_drugbank.py                  # Parse + TSV + Neo4j
    python scripts/run_drugbank.py --skip-neo4j     # Parse + TSV only
"""

import os
import sys
import logging
import argparse
from pathlib import Path

# Ensure project root is on path
_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.parsers.drugbank_parser import DrugBankParser
from src.ontology_configs import ONTOLOGY_CONFIGS
from src.memgraph_loader import Neo4jLoader

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('drugbank_build.log'),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description='Run DrugBank parser standalone')
    parser.add_argument('--skip-neo4j', action='store_true',
                        help='Skip Neo4j loading (parse + TSV export only)')
    parser.add_argument('--base-dir', default='.', help='Project base directory')
    args = parser.parse_args()

    base_dir = Path(args.base_dir)
    raw_dir = base_dir / 'data' / 'raw'
    processed_dir = base_dir / 'data' / 'processed'

    # --- Step 1: Initialize parser ---
    logger.info("=" * 60)
    logger.info("DrugBank Standalone Pipeline")
    logger.info("=" * 60)

    drugbank_parser = DrugBankParser(data_dir=str(raw_dir))

    # --- Step 2: Check data availability ---
    if not drugbank_parser.download_data():
        logger.error("No DrugBank data source available")
        sys.exit(1)

    # --- Step 3: Parse ---
    data = drugbank_parser.parse_data()
    if not data:
        logger.error("No data parsed from DrugBank")
        sys.exit(1)

    for key, df in data.items():
        logger.info(f"  {key}: {len(df):,} rows, columns: {list(df.columns)}")

    # --- Step 4: Export TSVs ---
    output_dir = processed_dir / 'drugbank'
    output_dir.mkdir(parents=True, exist_ok=True)

    for data_name, df in data.items():
        tsv_path = output_dir / f"{data_name}.tsv"
        df.to_csv(tsv_path, sep='\t', index=False)
        logger.info(f"  Exported {tsv_path} ({len(df):,} rows)")

    # --- Step 5: Load into Neo4j ---
    if args.skip_neo4j:
        logger.info("Skipping Neo4j loading (--skip-neo4j)")
        logger.info("Done!")
        return

    from dotenv import load_dotenv
    load_dotenv()

    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    username = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', '')

    if not password:
        logger.error("NEO4J_PASSWORD not set. Set it in .env or environment.")
        sys.exit(1)

    # Filter ontology configs to DrugBank only
    drugbank_configs = {
        k: v for k, v in ONTOLOGY_CONFIGS.items()
        if k.startswith('drugbank.')
    }
    logger.info(f"Loading {len(drugbank_configs)} DrugBank configs into Neo4j")

    try:
        with Neo4jLoader(uri, username, password) as loader:
            loader.setup_constraints(drugbank_configs)
            loader.setup_indexes(drugbank_configs)
            loader.load_from_configs(
                {'drugbank': data}, drugbank_configs, processed_dir
            )

            verification = loader.verify_graph()
            logger.info("Neo4j Graph Verification:")
            logger.info(f"  Node counts: {verification['node_counts']}")
            logger.info(f"  Relationship counts: {verification['relationship_counts']}")
            logger.info(f"  Total nodes: {verification['total_nodes']}")
            logger.info(f"  Total relationships: {verification['total_relationships']}")

    except Exception as e:
        logger.error(f"Neo4j loading failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)

    logger.info("DrugBank pipeline complete!")


if __name__ == '__main__':
    main()
