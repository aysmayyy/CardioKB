#!/usr/bin/env python3
"""Load edges into Memgraph with multi-property matching."""

import pandas as pd
from neo4j import GraphDatabase
from pathlib import Path
import sys
import re

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "output"
driver = GraphDatabase.driver("bolt://localhost:7687", auth=("", ""))


def get_gene_match_clause(id_val: str, alias: str) -> tuple[str, dict]:
    """Return Cypher WHERE clause and params for matching a Gene node."""
    # Numeric -> geneId
    if id_val.isdigit():
        return f"{alias}.geneId = $p_{alias}", {f"p_{alias}": id_val}
    # ENSG -> xrefEnsembl
    if id_val.startswith("ENSG"):
        return f"{alias}.xrefEnsembl = $p_{alias}", {f"p_{alias}": id_val}
    # ENSP -> also try xrefEnsembl (protein ID)
    if id_val.startswith("ENSP"):
        return f"{alias}.xrefEnsembl CONTAINS $p_{alias}", {f"p_{alias}": id_val[:15]}
    # Otherwise assume gene symbol
    return f"{alias}.geneSymbol = $p_{alias}", {f"p_{alias}": id_val}


def get_drug_match_clause(id_val: str, alias: str) -> tuple[str, dict]:
    """Return Cypher WHERE clause and params for matching a Drug node."""
    # DrugBank ID
    if id_val.startswith("DB"):
        return f"{alias}.xrefDrugBank = $p_{alias}", {f"p_{alias}": id_val}
    # MeSH ID (with or without prefix)
    if id_val.startswith("MESH:") or re.match(r"^[CD]\d+$", id_val):
        mesh_id = id_val.replace("MESH:", "")
        return f"{alias}.xrefMeSH = $p_{alias}", {f"p_{alias}": mesh_id}
    # Numeric - try drugbankId numeric part
    if id_val.isdigit():
        return f"{alias}.id CONTAINS $p_{alias}", {f"p_{alias}": id_val}
    # Otherwise try common name
    return f"toLower({alias}.commonName) = toLower($p_{alias})", {f"p_{alias}": id_val}


def get_disease_match_clause(id_val: str, alias: str) -> tuple[str, dict]:
    """Return Cypher WHERE clause and params for matching a Disease node."""
    # DOID format
    if id_val.startswith("DOID:") or id_val.isdigit():
        doid = id_val.replace("DOID:", "")
        return f"{alias}.diseaseId = $p_{alias}", {f"p_{alias}": doid}
    # CUI format
    if re.match(r"^C\d{7}$", id_val):
        return f"{alias}.xrefUmlsCUI = $p_{alias}", {f"p_{alias}": id_val}
    # MeSH
    if id_val.startswith("MESH:"):
        return f"{alias}.xrefMeSH = $p_{alias}", {f"p_{alias}": id_val.replace("MESH:", "")}
    # Disease name (fallback)
    return f"toLower({alias}.diseaseName) = toLower($p_{alias})", {f"p_{alias}": id_val}


def get_match_clause(label: str, id_val: str, alias: str) -> tuple[str, str, dict]:
    """Return (node_label, WHERE clause, params) for matching a node."""
    if label in ("Gene",):
        clause, params = get_gene_match_clause(id_val, alias)
        return "Gene", clause, params
    elif label in ("Drug", "Compound"):
        clause, params = get_drug_match_clause(id_val, alias)
        return "Drug", clause, params
    elif label in ("Disease",):
        clause, params = get_disease_match_clause(id_val, alias)
        return "Disease", clause, params
    elif label in ("BodyPart", "Anatomy"):
        # Try id directly with prefix
        if id_val.startswith("UBERON:"):
            return "Anatomy", f"{alias}.id = $p_{alias}", {f"p_{alias}": id_val}
        elif id_val.startswith("BTO:"):
            return "Anatomy", f"{alias}.id CONTAINS $p_{alias}", {f"p_{alias}": id_val}
        return "Anatomy", f"{alias}.id = $p_{alias}", {f"p_{alias}": f"UBERON:{id_val}" if id_val.isdigit() else id_val}
    elif label == "Phenotype":
        hp_id = id_val if id_val.startswith("HP:") else f"HP:{id_val}"
        return "Phenotype", f"{alias}.id = $p_{alias}", {f"p_{alias}": hp_id}
    elif label == "Pathway":
        return "Pathway", f"{alias}.id = $p_{alias}", {f"p_{alias}": id_val}
    elif label == "GeneFamily":
        return "GeneFamily", f"{alias}.id CONTAINS $p_{alias}", {f"p_{alias}": id_val}
    elif label == "SideEffect":
        return "SideEffect", f"{alias}.id = $p_{alias}", {f"p_{alias}": id_val}
    elif label == "PharmacologicClass":
        return "PharmacologicClass", f"{alias}.id CONTAINS $p_{alias}", {f"p_{alias}": id_val.replace("MeSH:", "")}
    elif label == "ClinicalTrial":
        nct = id_val if id_val.startswith("NCT") else f"NCT{id_val}"
        return "ClinicalTrial", f"{alias}.id = $p_{alias}", {f"p_{alias}": nct}
    elif label == "Variant":
        return "Variant", f"{alias}.id = $p_{alias}", {f"p_{alias}": id_val}
    elif label == "BiologicalProcess":
        go_id = id_val if id_val.startswith("GO:") else f"GO:{id_val}"
        return "BiologicalProcess", f"{alias}.id = $p_{alias}", {f"p_{alias}": go_id}
    elif label == "MolecularFunction":
        go_id = id_val if id_val.startswith("GO:") else f"GO:{id_val}"
        return "MolecularFunction", f"{alias}.id = $p_{alias}", {f"p_{alias}": go_id}
    elif label == "CellularComponent":
        go_id = id_val if id_val.startswith("GO:") else f"GO:{id_val}"
        return "CellularComponent", f"{alias}.id = $p_{alias}", {f"p_{alias}": go_id}
    elif label == "TranscriptionFactor":
        return "TranscriptionFactor", f"{alias}.id CONTAINS $p_{alias}", {f"p_{alias}": id_val}
    elif label == "DrugLabel":
        return "DrugLabel", f"{alias}.id = $p_{alias}", {f"p_{alias}": id_val}
    elif label == "Symptom":
        return "Symptom", f"{alias}.id = $p_{alias}", {f"p_{alias}": id_val}
    else:
        return label, f"{alias}.id = $p_{alias}", {f"p_{alias}": id_val}


def parse_id(raw: str) -> tuple[str, str]:
    """Parse 'Label:value' to (label, value)."""
    if ":" in str(raw):
        parts = str(raw).split(":", 1)
        return parts[0], parts[1]
    return "", str(raw)


def load_edge_file(csv_path: Path, batch_size: int = 1000) -> tuple[int, str]:
    """Load edges from a CSV file."""
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        return 0, f"read error: {e}"

    if ":START_ID" not in df.columns or ":END_ID" not in df.columns:
        return 0, "missing ID columns"

    rel_type = df[":TYPE"].iloc[0] if ":TYPE" in df.columns else csv_path.stem.replace("edges_", "")
    prop_cols = [c for c in df.columns if not c.startswith(":")]

    total = 0
    errors = 0

    with driver.session() as session:
        for i in range(0, len(df), batch_size):
            batch = df.iloc[i:i+batch_size]
            batch_created = 0

            for _, row in batch.iterrows():
                src_label, src_val = parse_id(row[":START_ID"])
                tgt_label, tgt_val = parse_id(row[":END_ID"])

                if not src_label or not tgt_label:
                    errors += 1
                    continue

                try:
                    src_node_label, src_clause, src_params = get_match_clause(src_label, src_val, "a")
                    tgt_node_label, tgt_clause, tgt_params = get_match_clause(tgt_label, tgt_val, "b")

                    props = {c: row[c] for c in prop_cols if pd.notna(row[c])}
                    params = {**src_params, **tgt_params, "props": props}

                    query = f"""
                    MATCH (a:{src_node_label}) WHERE {src_clause}
                    MATCH (b:{tgt_node_label}) WHERE {tgt_clause}
                    CREATE (a)-[r:{rel_type}]->(b)
                    SET r = $props
                    """
                    result = session.run(query, **params)
                    summary = result.consume()
                    batch_created += summary.counters.relationships_created
                except Exception as e:
                    errors += 1
                    if errors <= 3:
                        print(f"    Error: {src_label}:{src_val} -> {tgt_label}:{tgt_val}: {str(e)[:50]}")

            total += batch_created

            if i % 10000 == 0 and i > 0:
                print(f"    Progress: {i:,}/{len(df):,} rows, {total:,} edges")
                sys.stdout.flush()

    return total, f"{errors} errors" if errors else None


def main():
    edge_files = sorted(OUTPUT_DIR.glob("edges_*.csv"))
    print(f"Found {len(edge_files)} edge files")

    # Check current state
    with driver.session() as session:
        current = session.run("MATCH ()-[r]->() RETURN count(r) as c").single()["c"]
        print(f"Current edges in DB: {current:,}")

    grand_total = current
    for i, ef in enumerate(edge_files):
        # Check if this edge type already has edges
        rel_type = ef.stem.replace("edges_", "")
        with driver.session() as session:
            existing = session.run(f"MATCH ()-[r:{rel_type}]->() RETURN count(r) as c").single()["c"]

        if existing > 0:
            print(f"[{i+1}/{len(edge_files)}] {ef.name}: {existing:,} (already loaded)")
            continue

        count, err = load_edge_file(ef)
        status = f"{count:,}" + (f" ({err})" if err else "")
        print(f"[{i+1}/{len(edge_files)}] {ef.name}: {status}")
        sys.stdout.flush()
        grand_total += count

    # Final count
    with driver.session() as session:
        final = session.run("MATCH ()-[r]->() RETURN count(r) as c").single()["c"]

    print(f"\nFinal edges in DB: {final:,}")
    driver.close()


if __name__ == "__main__":
    main()
