#!/usr/bin/env python3
"""
Fast batch loader for Memgraph using UNWIND.
Loads nodes first, then edges with label hints for index usage.
"""

import csv
import logging
import sys
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
    'HP:': 'Phenotype',
    'Reactome:': 'Pathway',
    'NCT:': 'ClinicalTrial',
    'ClinVar:': 'Variant',
    'DrugCentralPharmClass:': 'PharmacologicClass',
    'MeSH:': 'Symptom',
}

# Edge type to (start_label, end_label) for ambiguous cases
EDGE_LABELS = {
    'geneAssociatedWithCellularComponent': ('Gene', 'CellularComponent'),
    'geneParticipatesInBiologicalProcess': ('Gene', 'BiologicalProcess'),
    'geneHasMolecularFunction': ('Gene', 'MolecularFunction'),
    'geneInFamily': ('Gene', 'GeneFamily'),
    'transcriptionFactorInteractsWithGene': ('TranscriptionFactor', 'Gene'),
    'compoundInPharmacologicClass': ('Drug', 'PharmacologicClass'),
}


def get_label(id_str: str, rel_type: str, is_start: bool) -> str:
    """Get node label from ID prefix or edge type mapping."""
    if rel_type in EDGE_LABELS:
        return EDGE_LABELS[rel_type][0 if is_start else 1]
    for prefix, label in PREFIX_TO_LABEL.items():
        if id_str.startswith(prefix):
            return label
    return None


def load_nodes():
    """Load all node CSV files."""
    node_files = sorted(OUTPUT_DIR.glob("nodes_*.csv"))
    logger.info(f"Found {len(node_files)} node files")

    total = 0
    for nf in node_files:
        label = nf.stem.replace("nodes_", "")
        count = load_node_file(nf, label)
        logger.info(f"  {nf.name}: {count:,} nodes")
        total += count

    return total


def load_node_file(csv_path: Path, label: str) -> int:
    """Load nodes from CSV using batched UNWIND."""
    rows = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            clean = {k: v for k, v in row.items() if k != ':LABEL' and v}
            rows.append(clean)

    if not rows:
        return 0

    with driver.session() as session:
        try:
            session.run(f"CREATE INDEX ON :{label}(id)")
        except:
            pass

    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i+BATCH_SIZE]
        query = f"""
        UNWIND $batch AS row
        CREATE (n:{label})
        SET n = row
        """
        with driver.session() as session:
            result = session.run(query, batch=batch)
            summary = result.consume()
            total += summary.counters.nodes_created

    return total


def load_edges():
    """Load all edge CSV files."""
    edge_files = sorted(OUTPUT_DIR.glob("edges_*.csv"), key=lambda p: p.stat().st_size)
    logger.info(f"Found {len(edge_files)} edge files")

    total = 0
    for i, ef in enumerate(edge_files):
        rel_type = ef.stem.replace("edges_", "")
        count = load_edge_file(ef, rel_type)
        logger.info(f"  [{i+1}/{len(edge_files)}] {ef.name}: {count:,} edges")
        total += count

    return total


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
                if start_label is None:
                    start_label = get_label(start, rel_type, True)
                    end_label = get_label(end, rel_type, False)

    if not rows:
        return 0

    if start_label and end_label:
        query = f"""
        UNWIND $batch AS edge
        MATCH (a:{start_label} {{id: edge.start}})
        MATCH (b:{end_label} {{id: edge.end}})
        CREATE (a)-[r:{rel_type}]->(b)
        """
    else:
        logger.warning(f"    No labels for {rel_type}, using full scan")
        query = f"""
        UNWIND $batch AS edge
        MATCH (a {{id: edge.start}})
        MATCH (b {{id: edge.end}})
        CREATE (a)-[r:{rel_type}]->(b)
        """

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
    with driver.session() as session:
        nodes = session.run("MATCH (n) RETURN count(n) as c").single()["c"]
        edges = session.run("MATCH ()-[r]->() RETURN count(r) as c").single()["c"]
        logger.info(f"Current: {nodes:,} nodes, {edges:,} edges")

    if nodes == 0:
        logger.info("\n=== Loading nodes ===")
        node_count = load_nodes()
        logger.info(f"Total nodes loaded: {node_count:,}")
    else:
        logger.info("Nodes already loaded, skipping...")

    logger.info("\n=== Loading edges ===")
    edge_count = load_edges()
    logger.info(f"Total edges loaded: {edge_count:,}")

    with driver.session() as session:
        nodes = session.run("MATCH (n) RETURN count(n) as c").single()["c"]
        edges = session.run("MATCH ()-[r]->() RETURN count(r) as c").single()["c"]
        logger.info(f"\n=== FINAL: {nodes:,} nodes, {edges:,} edges ===")

    driver.close()


if __name__ == "__main__":
    main()
