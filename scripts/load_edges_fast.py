#!/usr/bin/env python3
"""
Fast edge loader with label hints for index usage.
"""

import csv
import logging
from pathlib import Path
from neo4j import GraphDatabase

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "output"
BATCH_SIZE = 5000

driver = GraphDatabase.driver("bolt://localhost:7687", auth=None)

# Map ID prefix to node label
PREFIX_TO_LABEL = {
    'NCBIGene:': 'Gene',
    'DOID:': 'Disease',
    'UBERON:': 'BodyPart',
    'DrugBank:': 'Drug',
    'DrugCentral:': 'Drug',
    'CTD:': 'Drug',
    'UMLS:': 'SideEffect',
    'GO:': None,  # Could be BP, CC, or MF - handle specially
    'HP:': 'Phenotype',
    'HGNC:': None,  # Could be GeneFamily or TranscriptionFactor
    'Reactome:': 'Pathway',
    'NCT:': 'ClinicalTrial',
    'ClinVar:': 'Variant',
    'DrugCentralPharmClass:': 'PharmacologicClass',
    'MeSH:': 'Symptom',
}

# Edge type to (start_label, end_label) mapping for ambiguous cases
EDGE_TYPE_LABELS = {
    'geneAssociatedWithCellularComponent': ('Gene', 'CellularComponent'),
    'geneParticipatesInBiologicalProcess': ('Gene', 'BiologicalProcess'),
    'geneHasMolecularFunction': ('Gene', 'MolecularFunction'),
    'geneInFamily': ('Gene', 'GeneFamily'),
    'transcriptionFactorInteractsWithGene': ('TranscriptionFactor', 'Gene'),
}


def get_label_from_id(id_str: str, edge_type: str = None, is_start: bool = True) -> str:
    """Infer node label from ID prefix."""
    # Check edge type mapping first for ambiguous cases
    if edge_type in EDGE_TYPE_LABELS:
        labels = EDGE_TYPE_LABELS[edge_type]
        return labels[0] if is_start else labels[1]

    # Fall back to prefix matching
    for prefix, label in PREFIX_TO_LABEL.items():
        if id_str.startswith(prefix):
            if label:
                return label
            # Handle GO: prefix based on content
            if prefix == 'GO:':
                return 'BiologicalProcess'  # Default, will match via index
    return None


def load_edge_file(csv_path: Path, rel_type: str) -> int:
    """Load edges from CSV using batched UNWIND with label hints."""
    rows = []
    start_label = None
    end_label = None

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            start = row.get(':START_ID', '')
            end = row.get(':END_ID', '')
            if start and end:
                rows.append({'start': start, 'end': end})
                # Infer labels from first row
                if start_label is None:
                    start_label = get_label_from_id(start, rel_type, True)
                    end_label = get_label_from_id(end, rel_type, False)

    if not rows:
        return 0

    # Build query with or without labels
    if start_label and end_label:
        query = f"""
        UNWIND $batch AS edge
        MATCH (a:{start_label} {{id: edge.start}})
        MATCH (b:{end_label} {{id: edge.end}})
        CREATE (a)-[r:{rel_type}]->(b)
        """
        logger.info(f"    Using labels: ({start_label})->({end_label})")
    else:
        query = f"""
        UNWIND $batch AS edge
        MATCH (a {{id: edge.start}})
        MATCH (b {{id: edge.end}})
        CREATE (a)-[r:{rel_type}]->(b)
        """
        logger.info(f"    No label hint available")

    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i+BATCH_SIZE]
        with driver.session() as session:
            try:
                result = session.run(query, batch=batch)
                summary = result.consume()
                total += summary.counters.relationships_created
            except Exception as e:
                logger.warning(f"  Batch error at row {i}: {str(e)[:80]}")

    return total


def main():
    # Check current state
    with driver.session() as session:
        nodes = session.run("MATCH (n) RETURN count(n) as c").single()["c"]
        edges = session.run("MATCH ()-[r]->() RETURN count(r) as c").single()["c"]
        logger.info(f"Current: {nodes:,} nodes, {edges:,} edges")

    if nodes == 0:
        logger.error("No nodes loaded! Load nodes first.")
        return

    logger.info("\n=== Loading edges ===")
    edge_files = sorted(OUTPUT_DIR.glob("edges_*.csv"), key=lambda p: p.stat().st_size)
    logger.info(f"Found {len(edge_files)} edge files")

    total = 0
    for i, ef in enumerate(edge_files):
        rel_type = ef.stem.replace("edges_", "")
        count = load_edge_file(ef, rel_type)
        logger.info(f"  [{i+1}/{len(edge_files)}] {ef.name}: {count:,} edges")
        total += count

    logger.info(f"Total edges loaded: {total:,}")

    # Final stats
    with driver.session() as session:
        nodes = session.run("MATCH (n) RETURN count(n) as c").single()["c"]
        edges = session.run("MATCH ()-[r]->() RETURN count(r) as c").single()["c"]
        logger.info(f"\n=== FINAL: {nodes:,} nodes, {edges:,} edges ===")

    driver.close()


if __name__ == "__main__":
    main()
