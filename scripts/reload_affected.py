#!/usr/bin/env python3
"""
Reload affected relationship configs into Neo4j after bug fixes.

Fixes applied:
1. DrugCentral: Re-parse to get drugbank_id mapping + pharmacologic classes
2. CTD: Add MESH: prefix to chemical_id
3. Hetionet precomputed: Config now matches on xrefNcbiGene (int)
4. LINCS: Config already correct, just reload
5. AOP-DB: Type-preserving int for entrez gene IDs

Reads from cached raw data + existing TSVs. No downloads needed.
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
from src.neo4j_loader import Neo4jLoader

RAW_DIR = project_root / 'data' / 'raw'
PROCESSED_DIR = project_root / 'data' / 'processed'

# Configs to reload (relationship configs that were broken)
AFFECTED_CONFIGS = [
    # DrugCentral
    'drugcentral.pharmacologic_classes',          # node
    'drugcentral.pharmacologic_class_includes_compound',
    'drugcentral.drug_treats_disease',
    'drugcentral.drug_palliates_disease',
    # CTD
    'ctd.chemical_increases_expression',
    'ctd.chemical_decreases_expression',
    # Hetionet precomputed
    'hetionet_precomputed.gene_interacts',
    'hetionet_precomputed.gene_covaries',
    'hetionet_precomputed.gene_regulates',
    # LINCS
    'lincs.compound_upregulates_gene',
    'lincs.compound_downregulates_gene',
    'lincs.gene_regulates_gene',
    # AOP-DB (entrez int fix)
    'aopdb.gene_pathway_relationships',
]


def reparse_drugcentral():
    """Re-run DrugCentral parser from cached SQL dump."""
    from src.parsers.hetionet_components.drugcentral_parser import DrugCentralParser

    parser = DrugCentralParser(data_dir=str(RAW_DIR))
    data = parser.parse_data()

    if not data:
        logger.error("DrugCentral parser returned no data!")
        return {}

    # Export updated TSVs
    out_dir = PROCESSED_DIR / 'drugcentral'
    out_dir.mkdir(parents=True, exist_ok=True)
    for key, df in data.items():
        tsv_path = out_dir / f"{key}.tsv"
        df.to_csv(tsv_path, sep='\t', index=False)
        logger.info(f"Exported {key}: {len(df)} rows -> {tsv_path}")

    return data


def load_ctd_with_prefix():
    """Load CTD TSVs and add MESH: prefix to chemical_id."""
    data = {}
    for key in ('chemical_increases_expression', 'chemical_decreases_expression'):
        tsv = PROCESSED_DIR / 'ctd' / f'{key}.tsv'
        if tsv.exists():
            df = pd.read_csv(tsv, sep='\t')
            if 'chemical_id' in df.columns:
                df['chemical_id'] = df['chemical_id'].apply(
                    lambda x: f'MESH:{x}' if pd.notna(x) and not str(x).startswith('MESH:') else x
                )
            data[key] = df
            logger.info(f"CTD {key}: {len(df)} rows (MESH: prefix applied)")
    return data


def load_tsv(source, filename):
    """Load a TSV file from processed dir."""
    tsv = PROCESSED_DIR / source / filename
    if tsv.exists():
        df = pd.read_csv(tsv, sep='\t')
        logger.info(f"Loaded {source}/{filename}: {len(df)} rows")
        return df
    logger.warning(f"TSV not found: {tsv}")
    return None


def main():
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    username = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', '')

    if not password:
        logger.error("NEO4J_PASSWORD not set")
        sys.exit(1)

    # Step 1: Re-parse DrugCentral
    logger.info("=" * 60)
    logger.info("Step 1: Re-parsing DrugCentral")
    logger.info("=" * 60)
    dc_data = reparse_drugcentral()

    # Step 2: Load CTD with MESH: prefix
    logger.info("=" * 60)
    logger.info("Step 2: Loading CTD with MESH: prefix")
    logger.info("=" * 60)
    ctd_data = load_ctd_with_prefix()

    # Step 3: Build parsed_data dict for loader
    parsed_data = {}
    if dc_data:
        parsed_data['drugcentral'] = dc_data
    if ctd_data:
        parsed_data['ctd'] = ctd_data

    # Hetionet precomputed, LINCS, AOP-DB: load from existing TSVs
    # (the config fixes handle the matching — TSV data is fine)

    # Step 4: Load into Neo4j
    logger.info("=" * 60)
    logger.info("Step 3: Loading into Neo4j")
    logger.info("=" * 60)

    with Neo4jLoader(uri, username, password) as loader:
        # Setup indexes for new match properties
        loader.setup_indexes(ONTOLOGY_CONFIGS)

        # Load nodes first (PharmacologicClass)
        for config_key in AFFECTED_CONFIGS:
            config = ONTOLOGY_CONFIGS.get(config_key)
            if not config or config.get('data_type') != 'node':
                continue

            source_name, data_name = config_key.split('.', 1)
            df = None
            if source_name in parsed_data and data_name in parsed_data[source_name]:
                df = parsed_data[source_name][data_name]
            else:
                df = load_tsv(source_name, config['source_filename'])

            if df is not None and len(df) > 0:
                loader._load_nodes(df, config, config_key)
            else:
                logger.warning(f"No data for {config_key}")

        # Load relationships
        for config_key in AFFECTED_CONFIGS:
            config = ONTOLOGY_CONFIGS.get(config_key)
            if not config or config.get('data_type') != 'relationship':
                continue

            source_name, data_name = config_key.split('.', 1)
            df = None
            if source_name in parsed_data and data_name in parsed_data[source_name]:
                df = parsed_data[source_name][data_name]
            else:
                df = load_tsv(source_name, config['source_filename'])

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
        logger.info("Node counts:")
        for label, cnt in sorted(verification['node_counts'].items()):
            logger.info(f"  {label}: {cnt:,}")
        logger.info("Relationship counts:")
        for rel_type, cnt in sorted(verification['relationship_counts'].items()):
            logger.info(f"  {rel_type}: {cnt:,}")


if __name__ == '__main__':
    main()
