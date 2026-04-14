#!/usr/bin/env python3
"""
Reload PubTator and GWAS relationship data into Neo4j with correct ID remapping.

Root cause: Disease Ontology parser requires obonet/pronto which isn't installed,
so the MeSH→DOID (PubTator) and trait→DOID (GWAS) remapping was skipped during
the full pipeline run. This script loads the disease_ontology TSVs directly and
applies the remapping before loading into Neo4j.

Reads from cached processed TSVs. No downloads needed.
"""

import os
import sys
import logging
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

# Setup
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

from src.ontology_configs import ONTOLOGY_CONFIGS
from src.memgraph_loader import Neo4jLoader
from src.id_mapping import remap_pubtator_mesh_to_doid, remap_gwas_disease_to_doid

PROCESSED_DIR = project_root / 'data' / 'processed'

AFFECTED_CONFIGS = [
    'pubtator.disease_disease_cooccurrence',
    'pubtator.gene_disease_literature',
    'gwas.gene_disease_gwas',
]


def main():
    uri = os.getenv('MEMGRAPH_URI', 'bolt://localhost:7687')
    username = os.getenv('MEMGRAPH_USERNAME', '')
    password = os.getenv('MEMGRAPH_PASSWORD', '')

    if not password:
        logger.error("MEMGRAPH_PASSWORD not set")
        sys.exit(1)

    # Step 1: Load Disease Ontology TSVs for ID remapping
    logger.info("=" * 60)
    logger.info("Step 1: Loading Disease Ontology data for ID remapping")
    logger.info("=" * 60)

    do_dir = PROCESSED_DIR / 'disease_ontology'
    xrefs_df = pd.read_csv(do_dir / 'disease_xrefs.tsv', sep='\t')
    nodes_df = pd.read_csv(do_dir / 'disease_nodes.tsv', sep='\t')
    logger.info(f"Loaded {len(xrefs_df)} disease xrefs, {len(nodes_df)} disease nodes")

    parsed_data = {
        'disease_ontology': {
            'disease_xrefs': xrefs_df,
            'disease_nodes': nodes_df,
        }
    }

    # Step 2: Re-parse PubTator from raw data, then apply MeSH→DOID remap
    logger.info("=" * 60)
    logger.info("Step 2: Re-parsing PubTator from raw data + MeSH→DOID remap")
    logger.info("=" * 60)

    from src.parsers.hetionet_components.pubtator_parser import PubTatorParser
    RAW_DIR = project_root / 'data' / 'raw'
    parser = PubTatorParser(data_dir=str(RAW_DIR))
    pubtator_raw = parser.parse_data()

    if not pubtator_raw:
        logger.error("PubTator parser returned no data!")
        pubtator_raw = {}

    parsed_data['pubtator'] = pubtator_raw
    remap_pubtator_mesh_to_doid(parsed_data)

    # Export remapped TSVs
    pt_dir = PROCESSED_DIR / 'pubtator'
    pt_dir.mkdir(parents=True, exist_ok=True)
    for key, df in parsed_data['pubtator'].items():
        tsv_path = pt_dir / f'{key}.tsv'
        df.to_csv(tsv_path, sep='\t', index=False)
        logger.info(f"Exported remapped {key}: {len(df)} rows -> {tsv_path}")

    # Step 3: Load GWAS TSV and apply trait→DOID remap
    logger.info("=" * 60)
    logger.info("Step 3: Loading GWAS data and remapping trait→DOID")
    logger.info("=" * 60)

    gwas_path = PROCESSED_DIR / 'gwas' / 'gene_disease_gwas.tsv'
    if gwas_path.exists():
        gwas_df = pd.read_csv(gwas_path, sep='\t')
        logger.info(f"Loaded gene_disease_gwas: {len(gwas_df)} rows")
        parsed_data['gwas'] = {'gene_disease_gwas': gwas_df}
        remap_gwas_disease_to_doid(parsed_data)

        # Export remapped GWAS TSV
        gwas_out = PROCESSED_DIR / 'gwas' / 'gene_disease_gwas.tsv'
        parsed_data['gwas']['gene_disease_gwas'].to_csv(gwas_out, sep='\t', index=False)
        logger.info(f"Exported remapped gene_disease_gwas: {len(parsed_data['gwas']['gene_disease_gwas'])} rows")

    # Step 4: Load into Neo4j
    logger.info("=" * 60)
    logger.info("Step 4: Loading into Neo4j")
    logger.info("=" * 60)

    with Neo4jLoader(uri, username, password) as loader:
        loader.setup_indexes(ONTOLOGY_CONFIGS)

        for config_key in AFFECTED_CONFIGS:
            config = ONTOLOGY_CONFIGS.get(config_key)
            if not config:
                logger.warning(f"Config not found: {config_key}")
                continue
            if config.get('data_type') != 'relationship':
                continue
            if config.get('skip'):
                logger.info(f"Skipping {config_key} (skip=True)")
                continue

            source_name, data_name = config_key.split('.', 1)
            df = None
            if source_name in parsed_data and data_name in parsed_data[source_name]:
                df = parsed_data[source_name][data_name]

            if df is not None and len(df) > 0:
                loader._load_relationships(df, config, config_key)
            else:
                logger.warning(f"No data for {config_key}")

        # Verify
        logger.info("=" * 60)
        logger.info("Verification")
        logger.info("=" * 60)
        verification = loader.verify_graph()
        logger.info(f"Total nodes: {verification['total_nodes']:,}")
        logger.info(f"Total relationships: {verification['total_relationships']:,}")
        logger.info("Relationship counts:")
        for rel_type, cnt in sorted(verification['relationship_counts'].items()):
            logger.info(f"  {rel_type}: {cnt:,}")


if __name__ == '__main__':
    main()
