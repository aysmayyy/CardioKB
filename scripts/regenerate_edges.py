#!/usr/bin/env python3
"""
Regenerate edges_geneAssociatesWithDisease.csv and edges_STUDIES_CONDITION.csv
from processed TSVs, joining against existing node CSVs.
"""
import csv
import sys
from pathlib import Path
from collections import defaultdict

OUTPUT_DIR = Path("/Users/nawaza/Desktop/Cardio-KB/data/output")
PROCESSED_DIR = Path("/Users/nawaza/Desktop/Cardio-KB/data/processed")


def build_gene_lookups():
    """Build gene_id -> node_id and gene_symbol -> node_id from nodes_Gene.csv."""
    ncbi_to_id = {}
    symbol_to_id = {}
    with open(OUTPUT_DIR / "nodes_Gene.csv", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("xrefNcbiGene"):
                ncbi_to_id[row["xrefNcbiGene"]] = row["id"]
            if row.get("geneSymbol"):
                symbol_to_id[row["geneSymbol"].upper()] = row["id"]
    return ncbi_to_id, symbol_to_id


def build_disease_lookups():
    """Build DOID -> node_id and commonName -> node_id from nodes_Disease.csv."""
    doid_to_id = {}
    name_to_id = {}
    with open(OUTPUT_DIR / "nodes_Disease.csv", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("xrefDiseaseOntology"):
                doid_to_id[row["xrefDiseaseOntology"]] = row["id"]
            if row.get("commonName"):
                name_to_id[row["commonName"].lower()] = row["id"]
    return doid_to_id, name_to_id


def build_trial_lookup():
    """Build NCT ID -> node_id from nodes_ClinicalTrial.csv."""
    nct_to_id = {}
    with open(OUTPUT_DIR / "nodes_ClinicalTrial.csv", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("trialId"):
                nct_to_id[row["trialId"]] = row["id"]
    return nct_to_id


def regenerate_gene_associates_with_disease():
    print("Building gene and disease lookups...")
    ncbi_to_id, symbol_to_id = build_gene_lookups()
    doid_to_id, _ = build_disease_lookups()
    print(f"  Genes: {len(ncbi_to_id)} by NCBI ID, {len(symbol_to_id)} by symbol")
    print(f"  Diseases: {len(doid_to_id)} by DOID")

    seen = set()
    rows = []

    # PubTator: gene_id (NCBI) + disease_id (DOID)
    pubtator_path = PROCESSED_DIR / "pubtator" / "pubtator_gene_disease.tsv"
    pubtator_matched = 0
    pubtator_total = 0
    with open(pubtator_path, newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            pubtator_total += 1
            gene_node = ncbi_to_id.get(row["gene_id"])
            disease_node = doid_to_id.get(row["disease_id"])
            if gene_node and disease_node:
                key = (gene_node, disease_node)
                if key not in seen:
                    seen.add(key)
                    rows.append({
                        "start_id": gene_node,
                        "end_id": disease_node,
                        "source": "PubTator",
                    })
                    pubtator_matched += 1
    print(f"  PubTator: {pubtator_matched}/{pubtator_total} matched (deduplicated)")

    # OpenTargets: gene_symbol + disease_id (DOID)
    ot_path = PROCESSED_DIR / "opentargets" / "target_disease_associations.tsv"
    ot_matched = 0
    ot_total = 0
    with open(ot_path, newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            ot_total += 1
            gene_node = symbol_to_id.get(row["gene_symbol"].upper())
            disease_node = doid_to_id.get(row["disease_id"])
            if gene_node and disease_node:
                key = (gene_node, disease_node)
                if key not in seen:
                    seen.add(key)
                    rows.append({
                        "start_id": gene_node,
                        "end_id": disease_node,
                        "score": row.get("overall_score", ""),
                        "source": "OpenTargets",
                    })
                    ot_matched += 1
    print(f"  OpenTargets: {ot_matched}/{ot_total} matched (deduplicated)")

    out_path = OUTPUT_DIR / "edges_geneAssociatesWithDisease.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["start_id", "end_id", "score", "source"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Wrote {len(rows)} edges -> {out_path}")
    return len(rows)


def regenerate_studies_condition():
    print("Building trial and disease lookups...")
    nct_to_id = build_trial_lookup()
    _, name_to_id = build_disease_lookups()
    print(f"  Trials: {len(nct_to_id)} by NCT ID")
    print(f"  Diseases: {len(name_to_id)} by commonName")

    seen = set()
    rows = []
    matched = 0
    total = 0

    ct_path = PROCESSED_DIR / "clinicaltrials" / "trial_disease_associations.tsv"
    with open(ct_path, newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            total += 1
            trial_node = nct_to_id.get(row["nct_id"])
            disease_node = name_to_id.get(row["condition"].lower())
            if trial_node and disease_node:
                key = (trial_node, disease_node)
                if key not in seen:
                    seen.add(key)
                    rows.append({
                        "start_id": trial_node,
                        "end_id": disease_node,
                    })
                    matched += 1

    print(f"  ClinicalTrials: {matched}/{total} matched (deduplicated)")

    out_path = OUTPUT_DIR / "edges_STUDIES_CONDITION.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["start_id", "end_id"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Wrote {len(rows)} edges -> {out_path}")
    return len(rows)


if __name__ == "__main__":
    print("=== Regenerating geneAssociatesWithDisease ===")
    n1 = regenerate_gene_associates_with_disease()
    print()
    print("=== Regenerating STUDIES_CONDITION ===")
    n2 = regenerate_studies_condition()
    print()
    print(f"Done. geneAssociatesWithDisease: {n1}, STUDIES_CONDITION: {n2}")
