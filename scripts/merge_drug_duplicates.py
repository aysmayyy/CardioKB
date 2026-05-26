#!/usr/bin/env python3
"""
Merge Drug node duplicates: DrugCentral drugs that have a xrefDrugBank matching a DrugBank drug.
Uses batched operations with explicit labels for index usage.
"""

import logging
from neo4j import GraphDatabase

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

driver = GraphDatabase.driver("bolt://localhost:7687", auth=None)
BATCH_SIZE = 1000

# Map relationship types to target node labels
REL_TARGET_LABELS = {
    'compoundInPharmacologicClass': 'PharmacologicClass',
    'compoundCausesSideEffect': 'SideEffect',
    'drugTreatsDisease': 'Disease',
    'compoundDownregulatesGene': 'Gene',
    'compoundUpregulatesGene': 'Gene',
    'drugBindsGene': 'Gene',
    'chemicalBindsGene': 'Gene',
    'chemicalIncreasesExpression': 'Gene',
    'chemicalDecreasesExpression': 'Gene',
}


def get_initial_counts() -> tuple[int, int]:
    with driver.session() as session:
        nodes = session.run("MATCH (n:Drug) RETURN count(n) as c").single()["c"]
        rels = session.run("MATCH ()-[r]->() RETURN count(r) as c").single()["c"]
    return nodes, rels


def merge_all_duplicates():
    """Merge DrugCentral duplicates into DrugBank nodes using labeled queries."""
    logger.info("Step 1: Finding duplicate pairs...")

    with driver.session() as session:
        result = session.run("""
            MATCH (dc:Drug)
            WHERE dc.id STARTS WITH 'DrugCentral:'
              AND dc.xrefDrugBank IS NOT NULL
              AND dc.xrefDrugBank <> ''
            WITH dc, dc.xrefDrugBank AS dbid
            MATCH (db:Drug)
            WHERE db.id = 'DrugBank:' + dbid
            RETURN dc.id AS dc_id, db.id AS db_id
        """)
        pairs = {r["dc_id"]: r["db_id"] for r in result}

    logger.info(f"Found {len(pairs):,} duplicate pairs")

    if not pairs:
        return 0

    dc_ids = list(pairs.keys())

    logger.info("Step 2: Transferring outgoing relationships...")

    with driver.session() as session:
        result = session.run("""
            MATCH (dc:Drug)-[r]->()
            WHERE dc.id IN $dc_ids
            RETURN DISTINCT type(r) AS rel_type
        """, dc_ids=dc_ids)
        out_rel_types = [r["rel_type"] for r in result]

    logger.info(f"  Found {len(out_rel_types)} outgoing rel types: {out_rel_types}")

    for rel_type in out_rel_types:
        target_label = REL_TARGET_LABELS.get(rel_type)
        if not target_label:
            logger.warning(f"  Skipping {rel_type} - no target label mapping")
            continue

        with driver.session() as session:
            result = session.run(f"""
                MATCH (dc:Drug)-[r:{rel_type}]->(target:{target_label})
                WHERE dc.id IN $dc_ids
                RETURN dc.id AS dc_id, target.id AS target_id
            """, dc_ids=dc_ids)
            edges = [(r["dc_id"], r["target_id"]) for r in result]

        if not edges:
            continue

        logger.info(f"  Transferring {len(edges):,} {rel_type} -> {target_label}...")

        for i in range(0, len(edges), BATCH_SIZE):
            batch = edges[i:i+BATCH_SIZE]
            batch_data = [{"db_id": pairs[dc_id], "target_id": tid} for dc_id, tid in batch]

            with driver.session() as session:
                session.run(f"""
                    UNWIND $batch AS edge
                    MATCH (db:Drug {{id: edge.db_id}})
                    MATCH (target:{target_label} {{id: edge.target_id}})
                    CREATE (db)-[:{rel_type}]->(target)
                """, batch=batch_data)

        logger.info(f"    Done with {rel_type}")

    logger.info("Step 3: Transferring incoming relationships...")

    with driver.session() as session:
        result = session.run("""
            MATCH ()-[r]->(dc:Drug)
            WHERE dc.id IN $dc_ids
            RETURN DISTINCT type(r) AS rel_type
        """, dc_ids=dc_ids)
        in_rel_types = [r["rel_type"] for r in result]

    logger.info(f"  Found {len(in_rel_types)} incoming rel types: {in_rel_types}")

    for rel_type in in_rel_types:
        # For incoming, source could be various types, query without label for now
        with driver.session() as session:
            result = session.run(f"""
                MATCH (source)-[r:{rel_type}]->(dc:Drug)
                WHERE dc.id IN $dc_ids
                RETURN source.id AS source_id, dc.id AS dc_id, labels(source)[0] AS src_label
            """, dc_ids=dc_ids)
            edges = [(r["source_id"], r["dc_id"], r["src_label"]) for r in result]

        if not edges:
            continue

        # Group by source label for faster queries
        by_label = {}
        for sid, dc_id, label in edges:
            by_label.setdefault(label, []).append((sid, dc_id))

        for label, label_edges in by_label.items():
            logger.info(f"  Transferring {len(label_edges):,} {rel_type} from {label}...")

            for i in range(0, len(label_edges), BATCH_SIZE):
                batch = label_edges[i:i+BATCH_SIZE]
                batch_data = [{"source_id": sid, "db_id": pairs[dc_id]} for sid, dc_id in batch]

                with driver.session() as session:
                    session.run(f"""
                        UNWIND $batch AS edge
                        MATCH (source:{label} {{id: edge.source_id}})
                        MATCH (db:Drug {{id: edge.db_id}})
                        CREATE (source)-[:{rel_type}]->(db)
                    """, batch=batch_data)

    logger.info("Step 4: Deleting duplicate DrugCentral nodes...")

    total_deleted = 0
    for i in range(0, len(dc_ids), BATCH_SIZE):
        batch = dc_ids[i:i+BATCH_SIZE]
        with driver.session() as session:
            result = session.run("""
                MATCH (dc:Drug)
                WHERE dc.id IN $batch
                DETACH DELETE dc
                RETURN count(dc) AS deleted
            """, batch=batch)
            total_deleted += result.single()["deleted"]

    logger.info(f"  Deleted {total_deleted:,} duplicate nodes")
    return len(pairs)


def main():
    logger.info("=== Drug Duplicate Merger (Batched + Labeled) ===")

    nodes_before, rels_before = get_initial_counts()
    logger.info(f"Before: {nodes_before:,} Drug nodes, {rels_before:,} total relationships")

    merged = merge_all_duplicates()

    nodes_after, rels_after = get_initial_counts()
    logger.info(f"\nAfter: {nodes_after:,} Drug nodes, {rels_after:,} total relationships")
    logger.info(f"Nodes reduced by: {nodes_before - nodes_after:,}")
    logger.info(f"Duplicates merged: {merged:,}")

    driver.close()


if __name__ == "__main__":
    main()
