"""
Merge duplicate Drug nodes in Memgraph.

The BaseAgent pipeline creates duplicate Drug nodes when multiple sources
(DrugBank, CTD, ClinPGx, DrugCentral) load the same compound under different
internal IDs (drugId). All copies share the same xrefDrugBank value, which
serves as the canonical identifier for merging.

Duplication ranges from 2x (5,229 groups) to 8x (2 groups, e.g., salt/ester
forms like betamethasone dipropionate/acetate/benzoate that DrugBank maps to
the same parent compound).

For each duplicate group, this script:
1. Picks the DrugBank-sourced node (id starts with "drug_db") as survivor
2. Copies useful properties from duplicates to the survivor (union, not overwrite)
3. Transfers all edges from duplicates to the survivor (deduplicating by
   type + target + source to avoid creating identical edges)
4. DETACH DELETEs the duplicates

Run AFTER the full pipeline load. Idempotent — safe to re-run.
"""

import logging
import os
import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

_project_root = str(Path(__file__).parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

load_dotenv(Path(_project_root) / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

MEMGRAPH_URI = os.getenv("MEMGRAPH_URI", "bolt://localhost:7687")
MEMGRAPH_USER = os.getenv("MEMGRAPH_USERNAME", "")
MEMGRAPH_PASS = os.getenv("MEMGRAPH_PASSWORD", "")


def get_count(session, query):
    return session.run(query).single()[0]


def find_duplicate_groups(session):
    """Find all Drug nodes sharing the same xrefDrugBank."""
    result = session.run(
        'MATCH (n:Drug) '
        'WHERE n.xrefDrugBank IS NOT NULL AND n.xrefDrugBank <> "" '
        'WITH n.xrefDrugBank AS dbid, collect(n) AS nodes, count(n) AS cnt '
        'WHERE cnt > 1 '
        'RETURN dbid, [n IN nodes | id(n)] AS node_ids, '
        '       [n IN nodes | n.id] AS slug_ids, cnt '
        'ORDER BY cnt DESC'
    )
    groups = []
    for rec in result:
        groups.append({
            'dbid': rec['dbid'],
            'node_ids': rec['node_ids'],
            'slug_ids': rec['slug_ids'],
            'cnt': rec['cnt'],
        })
    return groups


def pick_survivor(node_ids, slug_ids):
    """Pick the DrugBank-sourced node as survivor. Prefer id starting with 'drug_db'."""
    for nid, slug in zip(node_ids, slug_ids):
        if slug and slug.startswith('drug_db'):
            return nid
    # Fallback: pick the first node
    return node_ids[0]


def merge_properties(session, survivor_id, duplicate_ids):
    """Copy non-empty properties from duplicates to survivor where survivor's value is empty."""
    for dup_id in duplicate_ids:
        result = session.run(
            'MATCH (dup:Drug) WHERE id(dup) = $dup_id '
            'MATCH (surv:Drug) WHERE id(surv) = $surv_id '
            'RETURN properties(dup) AS dup_props, properties(surv) AS surv_props',
            dup_id=dup_id,
            surv_id=survivor_id,
        )
        rec = result.single()
        if not rec:
            continue
        dup_props = rec['dup_props'] or {}
        surv_props = rec['surv_props'] or {}

        set_parts = []
        params = {'surv_id': survivor_id}
        pi = 0
        for k, v in dup_props.items():
            if k in ('id', 'drugId'):
                continue
            if v and str(v).strip():
                surv_val = surv_props.get(k)
                if not surv_val or str(surv_val).strip() == '':
                    pname = f'p{pi}'
                    set_parts.append(f'n.{k} = ${pname}')
                    params[pname] = v
                    pi += 1

        if set_parts:
            session.run(
                'MATCH (n:Drug) WHERE id(n) = $surv_id '
                f'SET {", ".join(set_parts)}',
                **params,
            )


def transfer_edges(session, survivor_id, duplicate_ids):
    """Transfer all edges from duplicates to survivor. Returns stats."""
    stats = {'out_moved': 0, 'out_deduped': 0, 'in_moved': 0, 'in_deduped': 0}

    for dup_id in duplicate_ids:
        # Outgoing: (dup)-[r]->(target)
        out = list(session.run(
            'MATCH (dup:Drug) WHERE id(dup) = $dup_id '
            'MATCH (dup)-[r]->(target) '
            'RETURN type(r) AS rel_type, properties(r) AS props, id(target) AS target_id',
            dup_id=dup_id,
        ))
        for rec in out:
            rel_type = rec['rel_type']
            props = rec['props'] or {}
            target_id = rec['target_id']
            source = props.get('source', '')

            # Check for existing equivalent edge on survivor
            check = session.run(
                f'MATCH (s:Drug) WHERE id(s) = $sid '
                f'MATCH (s)-[r:{rel_type}]->(t) WHERE id(t) = $tid AND r.source = $src '
                f'RETURN count(r) AS cnt',
                sid=survivor_id, tid=target_id, src=source,
            )
            if check.single()['cnt'] > 0:
                stats['out_deduped'] += 1
                continue

            prop_parts = []
            params = {'sid': survivor_id, 'tid': target_id}
            for i, (k, v) in enumerate(props.items()):
                pn = f'p{i}'
                prop_parts.append(f'r.{k} = ${pn}')
                params[pn] = v
            set_clause = f'SET {", ".join(prop_parts)}' if prop_parts else ''
            session.run(
                f'MATCH (s:Drug) WHERE id(s) = $sid '
                f'MATCH (t) WHERE id(t) = $tid '
                f'CREATE (s)-[r:{rel_type}]->(t) {set_clause}',
                **params,
            )
            stats['out_moved'] += 1

        # Incoming: (source)-[r]->(dup)
        inc = list(session.run(
            'MATCH (dup:Drug) WHERE id(dup) = $dup_id '
            'MATCH (src)-[r]->(dup) '
            'RETURN type(r) AS rel_type, properties(r) AS props, id(src) AS src_id',
            dup_id=dup_id,
        ))
        for rec in inc:
            rel_type = rec['rel_type']
            props = rec['props'] or {}
            src_id = rec['src_id']
            source = props.get('source', '')

            check = session.run(
                f'MATCH (s:Drug) WHERE id(s) = $sid '
                f'MATCH (src)-[r:{rel_type}]->(s) WHERE id(src) = $srcid AND r.source = $src '
                f'RETURN count(r) AS cnt',
                sid=survivor_id, srcid=src_id, src=source,
            )
            if check.single()['cnt'] > 0:
                stats['in_deduped'] += 1
                continue

            prop_parts = []
            params = {'sid': survivor_id, 'srcid': src_id}
            for i, (k, v) in enumerate(props.items()):
                pn = f'p{i}'
                prop_parts.append(f'r.{k} = ${pn}')
                params[pn] = v
            set_clause = f'SET {", ".join(prop_parts)}' if prop_parts else ''
            session.run(
                f'MATCH (src) WHERE id(src) = $srcid '
                f'MATCH (s:Drug) WHERE id(s) = $sid '
                f'CREATE (src)-[r:{rel_type}]->(s) {set_clause}',
                **params,
            )
            stats['in_moved'] += 1

    return stats


def delete_duplicates(session, duplicate_ids):
    """DETACH DELETE all duplicate nodes."""
    for dup_id in duplicate_ids:
        session.run(
            'MATCH (n:Drug) WHERE id(n) = $nid DETACH DELETE n',
            nid=dup_id,
        )


def main():
    driver = GraphDatabase.driver(MEMGRAPH_URI, auth=(MEMGRAPH_USER, MEMGRAPH_PASS))
    try:
        with driver.session() as session:
            nodes_before = get_count(session, 'MATCH (n) RETURN count(n)')
            edges_before = get_count(session, 'MATCH ()-[r]->() RETURN count(r)')
            drug_count_before = get_count(session, 'MATCH (n:Drug) RETURN count(n)')
            logger.info(
                f"Before: {nodes_before:,} nodes, {edges_before:,} edges, "
                f"{drug_count_before:,} Drug nodes"
            )

            logger.info("Finding duplicate groups by xrefDrugBank...")
            groups = find_duplicate_groups(session)
            if not groups:
                logger.info("No duplicate groups found.")
                return

            dist = defaultdict(int)
            for g in groups:
                dist[g['cnt']] += 1
            logger.info(f"Found {len(groups)} duplicate groups:")
            for cnt in sorted(dist):
                logger.info(f"  {cnt}x: {dist[cnt]} groups")
            total_to_remove = sum(g['cnt'] - 1 for g in groups)
            logger.info(f"Total nodes to remove: {total_to_remove}")

            totals = defaultdict(int)
            for i, g in enumerate(groups):
                survivor_id = pick_survivor(g['node_ids'], g['slug_ids'])
                dup_ids = [nid for nid in g['node_ids'] if nid != survivor_id]

                merge_properties(session, survivor_id, dup_ids)
                stats = transfer_edges(session, survivor_id, dup_ids)
                delete_duplicates(session, dup_ids)

                for k, v in stats.items():
                    totals[k] += v

                if (i + 1) % 500 == 0:
                    logger.info(f"  Processed {i + 1}/{len(groups)} groups...")

            nodes_after = get_count(session, 'MATCH (n) RETURN count(n)')
            edges_after = get_count(session, 'MATCH ()-[r]->() RETURN count(r)')
            drug_count_after = get_count(session, 'MATCH (n:Drug) RETURN count(n)')

            logger.info(f"\n{'=' * 60}")
            logger.info("MERGE COMPLETE")
            logger.info(f"{'=' * 60}")
            logger.info(f"Groups merged:           {len(groups)}")
            logger.info(f"Nodes removed:           {nodes_before - nodes_after}")
            logger.info(f"Outgoing edges moved:    {totals['out_moved']}")
            logger.info(f"Outgoing edges deduped:  {totals['out_deduped']}")
            logger.info(f"Incoming edges moved:    {totals['in_moved']}")
            logger.info(f"Incoming edges deduped:  {totals['in_deduped']}")
            logger.info(
                f"Nodes: {nodes_before:,} -> {nodes_after:,} "
                f"(Delta {nodes_after - nodes_before:,})"
            )
            logger.info(
                f"Drug nodes: {drug_count_before:,} -> {drug_count_after:,} "
                f"(Delta {drug_count_after - drug_count_before:,})"
            )
            logger.info(
                f"Edges: {edges_before:,} -> {edges_after:,} "
                f"(Delta {edges_after - edges_before:,})"
            )
    finally:
        driver.close()


if __name__ == "__main__":
    main()
