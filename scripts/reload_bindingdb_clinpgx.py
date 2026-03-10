#!/usr/bin/env python3
"""
Reload BindingDB and ClinPGx relationship configs into Neo4j.

Fixes applied:
1. BindingDB: Fixed column name mismatch, vectorized parsing, added
   UniProt→Entrez Gene ID mapping so chemicalBindsGene matches Gene nodes.
2. ClinPGx AFFECTS_RESPONSE_TO: Explode semicolons, case-normalize drug names
   to DrugBank, map drug classes to PharmacologicClass nodes.

Reads from cached raw data. No downloads needed.
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

AFFECTED_CONFIGS = [
    'bindingdb.drug_binds_gene',
    'clinpgx.clinical_annotations',
    'clinpgx.clinical_annotations_pharma_class',
]


def reparse_bindingdb():
    """Re-run BindingDB parser from cached raw TSV."""
    from src.parsers.hetionet_components.bindingdb_parser import BindingDBParser

    parser = BindingDBParser(data_dir=str(RAW_DIR))
    data = parser.parse_data()

    if not data:
        logger.error("BindingDB parser returned no data!")
        return {}

    # Export updated TSVs
    out_dir = PROCESSED_DIR / 'bindingdb'
    out_dir.mkdir(parents=True, exist_ok=True)
    for key, df in data.items():
        tsv_path = out_dir / f"{key}.tsv"
        df.to_csv(tsv_path, sep='\t', index=False)
        logger.info(f"Exported {key}: {len(df)} rows -> {tsv_path}")

    return data


def normalize_clinpgx():
    """Re-parse ClinPGx from raw cache, then normalize annotations."""
    from src.parsers import ClinPGxParser
    from src.main import CardioKBPipeline

    # Re-parse from raw cached API data to get original annotations
    parser = ClinPGxParser(data_dir=str(RAW_DIR))
    cpgx_raw = parser.parse_data()

    if not cpgx_raw or 'clinical_annotations' not in cpgx_raw:
        logger.error("ClinPGx parser returned no clinical_annotations!")
        return {}

    ann = cpgx_raw['clinical_annotations']
    logger.info(f"Re-parsed {len(ann)} ClinPGx clinical annotations from raw data")

    # Load DrugBank drugs for case matching
    db_path = PROCESSED_DIR / 'drugbank' / 'drugs.tsv'
    drugbank_data = {}
    if db_path.exists():
        drugbank_data = {'drugs': pd.read_csv(db_path, sep='\t')}

    # Use the pipeline's normalization method
    pipeline = CardioKBPipeline(str(project_root))
    cpgx = {'clinical_annotations': ann}
    parsed_data = {'drugbank': drugbank_data} if drugbank_data else {}
    drug_df, pharma_df = pipeline._normalize_clinpgx_annotations(cpgx, parsed_data)

    result = {}

    out_dir = PROCESSED_DIR / 'clinpgx'
    out_dir.mkdir(parents=True, exist_ok=True)

    if drug_df is not None and len(drug_df) > 0:
        tsv_path = out_dir / 'clinical_annotations.tsv'
        drug_df.to_csv(tsv_path, sep='\t', index=False)
        logger.info(f"Exported clinical_annotations (Drug): {len(drug_df)} rows -> {tsv_path}")
        result['clinical_annotations'] = drug_df

    if pharma_df is not None and len(pharma_df) > 0:
        tsv_path = out_dir / 'clinical_annotations_pharma_class.tsv'
        pharma_df.to_csv(tsv_path, sep='\t', index=False)
        logger.info(f"Exported clinical_annotations_pharma_class: {len(pharma_df)} rows -> {tsv_path}")
        result['clinical_annotations_pharma_class'] = pharma_df

    return result


def main():
    uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
    username = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', '')

    if not password:
        logger.error("NEO4J_PASSWORD not set")
        sys.exit(1)

    # Step 1: Re-parse BindingDB
    logger.info("=" * 60)
    logger.info("Step 1: Re-parsing BindingDB")
    logger.info("=" * 60)
    bindingdb_data = reparse_bindingdb()

    # Step 2: Normalize ClinPGx
    logger.info("=" * 60)
    logger.info("Step 2: Normalizing ClinPGx annotations")
    logger.info("=" * 60)
    clinpgx_data = normalize_clinpgx()

    # Step 3: Build parsed_data for loader
    parsed_data = {}
    if bindingdb_data:
        parsed_data['bindingdb'] = bindingdb_data
    if clinpgx_data:
        parsed_data['clinpgx'] = clinpgx_data

    # Step 4: Load into Neo4j
    logger.info("=" * 60)
    logger.info("Step 3: Loading into Neo4j")
    logger.info("=" * 60)

    with Neo4jLoader(uri, username, password) as loader:
        # Setup indexes for match properties
        loader.setup_indexes(ONTOLOGY_CONFIGS)

        # Load relationships
        for config_key in AFFECTED_CONFIGS:
            config = ONTOLOGY_CONFIGS.get(config_key)
            if not config:
                logger.warning(f"Config not found: {config_key}")
                continue
            if config.get('data_type') != 'relationship':
                continue

            source_name, data_name = config_key.split('.', 1)
            df = None
            if source_name in parsed_data and data_name in parsed_data[source_name]:
                df = parsed_data[source_name][data_name]
            else:
                tsv_path = PROCESSED_DIR / source_name / config['source_filename']
                if tsv_path.exists():
                    df = pd.read_csv(tsv_path, sep='\t')

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
