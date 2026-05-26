#!/usr/bin/env python3
"""Load all edges into Memgraph with comprehensive ID resolution."""

import pandas as pd
from neo4j import GraphDatabase
from pathlib import Path
import sys
from typing import Optional

OUT = Path(__file__).parent.parent / "data" / "output"
driver = GraphDatabase.driver("bolt://localhost:7687", auth=("", ""))

print("Building comprehensive ID lookup maps...")
sys.stdout.flush()

# Gene lookups: geneId, geneSymbol, xrefEnsembl -> node id
gene_by_geneId = {}
gene_by_symbol = {}
gene_by_ensembl = {}

# Drug lookups: xrefDrugBank -> node id
drug_by_drugbank = {}

# BodyPart lookups: UBERON id -> node id
bodypart_by_uberon = {}

# Other entity ID sets (for direct matching)
other_ids = {}

with driver.session() as session:
    # Gene lookups
    result = session.run("MATCH (g:Gene) RETURN g.id, g.geneId, g.geneSymbol, g.xrefEnsembl")
    for rec in result:
        gid = rec["g.id"]
        if rec["g.geneId"]:
            gene_by_geneId[str(rec["g.geneId"])] = gid
        if rec["g.geneSymbol"]:
            gene_by_symbol[rec["g.geneSymbol"]] = gid
        if rec["g.xrefEnsembl"]:
            gene_by_ensembl[rec["g.xrefEnsembl"]] = gid
    print(f"  Gene: {len(gene_by_geneId)} by geneId, {len(gene_by_symbol)} by symbol, {len(gene_by_ensembl)} by Ensembl")

    # Drug lookups
    result = session.run("MATCH (d:Drug) RETURN d.id, d.xrefDrugBank")
    for rec in result:
        did = rec["d.id"]
        if rec["d.xrefDrugBank"]:
            drug_by_drugbank[rec["d.xrefDrugBank"]] = did
    print(f"  Drug: {len(drug_by_drugbank)} by DrugBank")

    # BodyPart lookups
    result = session.run("MATCH (b:BodyPart) RETURN b.id")
    for rec in result:
        bid = rec["b.id"]
        # Extract UBERON:xxxx part from UBERON:UBERON:xxxx
        if bid and "UBERON:" in bid:
            short_id = bid.replace("UBERON:UBERON:", "UBERON:")
            bodypart_by_uberon[short_id] = bid
    print(f"  BodyPart: {len(bodypart_by_uberon)} by UBERON")

    # Other entities - store ID -> ID mappings
    for label in ['BiologicalProcess', 'MolecularFunction', 'CellularComponent',
                  'Pathway', 'SideEffect', 'Phenotype', 'GeneFamily',
                  'PharmacologicClass', 'ClinicalTrial', 'Variant',
                  'TranscriptionFactor', 'Symptom', 'DrugLabel', 'Disease']:
        result = session.run(f"MATCH (n:{label}) RETURN n.id")
        other_ids[label] = {rec["n.id"]: rec["n.id"] for rec in result}
        if other_ids[label]:
            print(f"  {label}: {len(other_ids[label])}")


def resolve_gene_id(val: str) -> Optional[str]:
    """Resolve Gene ID to node id."""
    # Try geneId (numeric)
    if val in gene_by_geneId:
        return gene_by_geneId[val]
    # Try symbol
    if val in gene_by_symbol:
        return gene_by_symbol[val]
    # Try Ensembl
    if val in gene_by_ensembl:
        return gene_by_ensembl[val]
    return None


def resolve_drug_id(val: str) -> Optional[str]:
    """Resolve Drug ID to node id."""
    if val in drug_by_drugbank:
        return drug_by_drugbank[val]
    # Drug edges with MESH: prefix can't be resolved (no MeSH in Drug nodes)
    return None


def resolve_bodypart_id(val: str) -> Optional[str]:
    """Resolve BodyPart ID to node id."""
    # val is like "UBERON:0000002"
    if val in bodypart_by_uberon:
        return bodypart_by_uberon[val]
    return None


def resolve_id(label: str, val: str) -> Optional[str]:
    """Resolve edge ID to node ID."""
    if label == "Gene":
        return resolve_gene_id(val)
    elif label in ("Drug", "Compound"):
        return resolve_drug_id(val)
    elif label in ("BodyPart", "Anatomy"):
        return resolve_bodypart_id(val)
    elif label in other_ids:
        # Try direct match
        if val in other_ids[label]:
            return val
        # Try with common prefixes
        for prefix in [f"GO:{val}", f"HP:{val}", f"DOID:{val}", f"R-HSA-{val}"]:
            if prefix in other_ids.get(label, {}):
                return prefix
        return None
    else:
        return None


def parse_edge_id(raw):
    """Parse Label:value to (label, value)."""
    if ":" in str(raw):
        parts = str(raw).split(":", 1)
        return parts[0], parts[1]
    return "", str(raw)


def load_edge_file(ef: Path) -> int:
    """Load edges from CSV file. Returns count loaded."""
    df = pd.read_csv(ef)
    if ":START_ID" not in df.columns:
        return 0

    rel_type = df[":TYPE"].iloc[0] if ":TYPE" in df.columns else ef.stem.replace("edges_", "")

    # Resolve all IDs
    resolved = []
    for _, row in df.iterrows():
        src_label, src_val = parse_edge_id(row[":START_ID"])
        tgt_label, tgt_val = parse_edge_id(row[":END_ID"])

        src_id = resolve_id(src_label, src_val)
        tgt_id = resolve_id(tgt_label, tgt_val)

        if src_id and tgt_id:
            resolved.append((src_id, tgt_id))

    if not resolved:
        return 0

    # Batch load edges
    batch_size = 5000
    loaded = 0
    with driver.session() as session:
        for i in range(0, len(resolved), batch_size):
            batch = resolved[i:i+batch_size]
            try:
                query = f"""
                UNWIND $edges AS edge
                MATCH (a {{id: edge[0]}})
                MATCH (b {{id: edge[1]}})
                CREATE (a)-[r:{rel_type}]->(b)
                """
                result = session.run(query, edges=batch)
                summary = result.consume()
                loaded += summary.counters.relationships_created
            except Exception as e:
                print(f"    Batch error: {str(e)[:60]}")
                break

    return loaded


# Main loading
print(f"\nLoading edges from {OUT}...")
sys.stdout.flush()

total = 0
for ef in sorted(OUT.glob("edges_*.csv")):
    if ef.name.startswith("fixed_"):
        continue

    df = pd.read_csv(ef)
    orig = len(df) if ":START_ID" in df.columns else 0

    count = load_edge_file(ef)
    total += count

    pct = (count / orig * 100) if orig > 0 else 0
    print(f"  {ef.name}: {count:,}/{orig:,} ({pct:.1f}%)")
    sys.stdout.flush()

# Final count
with driver.session() as session:
    final = session.run("MATCH ()-[r]->() RETURN count(r) as c").single()["c"]

print(f"\nTotal edges in Memgraph: {final:,}")
driver.close()
