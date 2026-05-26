"""Load only relationships (Pass 2) - nodes already loaded."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from ontology_configs import ONTOLOGY_CONFIGS
from memgraph_loader import Neo4jLoader
import pandas as pd
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

uri = os.environ.get("MEMGRAPH_URI", "bolt://127.0.0.1:7687")
username = os.environ.get("MEMGRAPH_USERNAME", "")
password = os.environ.get("MEMGRAPH_PASSWORD", "")
processed_dir = Path(__file__).parent.parent / "data" / "processed"

with Neo4jLoader(uri, username, password) as loader:
    logger.info("=" * 60)
    logger.info("Loading relationships only (nodes already loaded)")
    logger.info("=" * 60)
    
    for config_key, config in ONTOLOGY_CONFIGS.items():
        if config.get('data_type') != 'relationship' or config.get('skip'):
            continue
        
        source_name = config_key.split('.')[0]
        tsv_path = processed_dir / source_name / config['source_filename']
        
        if not tsv_path.exists():
            logger.warning(f"  {config_key}: file not found, skipping")
            continue
        
        try:
            df = pd.read_csv(tsv_path, sep='\t')
            if len(df) > 0:
                loader._load_relationships(df, config, config_key)
        except Exception as e:
            logger.error(f"  {config_key}: {e}")
    
    stats = loader.verify_graph()
    logger.info(f"Done! {stats['total_nodes']:,} nodes, {stats['total_relationships']:,} relationships")
