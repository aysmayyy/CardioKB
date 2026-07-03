#!/usr/bin/env python3
"""
Parse DrugBank XML indication text and create drugTreatsDisease and
drugTreatsPhenotype edges by matching Disease/Phenotype node names
against free-text indications.

Usage:
    python scripts/drugbank_indications.py                          # dry run
    python scripts/drugbank_indications.py --apply                  # disease edges only
    python scripts/drugbank_indications.py --apply --phenotypes     # disease + phenotype edges
"""

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

from neo4j import GraphDatabase

DRUGBANK_XML = "data/raw/drugbank/full_database.xml"
NS = "{http://www.drugbank.ca}"
SOURCE_LABEL = "DrugBank_Indications"
MIN_NAME_LEN = 5

# HPO modifier/severity terms that match too broadly in indication text
PHENOTYPE_BLOCKLIST = {
    "acute", "chronic", "severe", "moderate", "mild", "refractory",
    "progressive", "recurrent", "bilateral", "unilateral", "congenital",
    "familial", "generalized", "focal", "diffuse", "localized",
    "transient", "persistent", "intermittent", "variable", "abnormal",
    "delayed", "elevated", "reduced", "absent", "increased", "decreased",
    "short", "long", "rapid", "slow",
}


def get_node_names(driver, label, name_prop):
    """Fetch node names from the graph, filtered by minimum length."""
    with driver.session() as s:
        rows = s.run(
            f"MATCH (n:{label}) RETURN n.{name_prop} AS name"
        ).data()
    return [r["name"] for r in rows if r["name"] and len(r["name"]) >= MIN_NAME_LEN]


def build_patterns(names, blocklist=None):
    """Build compiled regex patterns for whole-word matching."""
    patterns = []
    for name in sorted(names, key=len, reverse=True):
        if blocklist and name.lower().strip() in blocklist:
            continue
        escaped = re.escape(name)
        pattern = re.compile(r"\b" + escaped + r"\b", re.IGNORECASE)
        patterns.append((name, pattern))
    return patterns


def parse_drugbank_indications(xml_path):
    """Stream-parse DrugBank XML and yield (drugbank_id, drug_name, indication_text)."""
    for event, elem in ET.iterparse(xml_path, events=("end",)):
        if elem.tag == f"{NS}drug" and elem.attrib.get("type"):
            db_id_elem = elem.find(f"{NS}drugbank-id[@primary='true']")
            name_elem = elem.find(f"{NS}name")
            ind_elem = elem.find(f"{NS}indication")
            if (
                db_id_elem is not None
                and db_id_elem.text
                and ind_elem is not None
                and ind_elem.text
                and ind_elem.text.strip()
            ):
                yield (
                    db_id_elem.text.strip(),
                    name_elem.text.strip() if name_elem is not None and name_elem.text else "",
                    ind_elem.text.strip(),
                )
            elem.clear()


def match_indications(xml_path, patterns):
    """Match node names against indication text. Returns list of (drugbank_id, drug_name, matched_name)."""
    edges = []
    drugs_processed = 0
    for db_id, drug_name, indication in parse_drugbank_indications(xml_path):
        drugs_processed += 1
        matched = set()
        for name, pattern in patterns:
            if pattern.search(indication):
                matched.add(name)
        for name in matched:
            edges.append((db_id, drug_name, name))
    return edges, drugs_processed


def write_disease_edges(driver, edges):
    """Write drugTreatsDisease edges to Memgraph."""
    query = """
    UNWIND $batch AS row
    MATCH (drug:Drug {xrefDrugBank: row.drugbank_id})
    MATCH (disease:Disease {diseaseName: row.target_name})
    MERGE (drug)-[r:drugTreatsDisease]->(disease)
    ON CREATE SET r.source = $source
    RETURN count(r) AS created
    """
    return _write_batch(driver, edges, query)


def write_phenotype_edges(driver, edges):
    """Write drugTreatsPhenotype edges to Memgraph."""
    query = """
    UNWIND $batch AS row
    MATCH (drug:Drug {xrefDrugBank: row.drugbank_id})
    MATCH (pheno:Phenotype {phenotypeName: row.target_name})
    MERGE (drug)-[r:drugTreatsPhenotype]->(pheno)
    ON CREATE SET r.source = $source
    RETURN count(r) AS created
    """
    return _write_batch(driver, edges, query)


def _write_batch(driver, edges, query):
    batch = [{"drugbank_id": db_id, "target_name": tn} for db_id, _, tn in edges]
    chunk_size = 500
    total = 0
    with driver.session() as s:
        for i in range(0, len(batch), chunk_size):
            chunk = batch[i : i + chunk_size]
            result = s.run(query, batch=chunk, source=SOURCE_LABEL).single()
            total += result["created"]
            print(f"  Batch {i // chunk_size + 1}: processed {len(chunk)} edges")
    return total


def print_samples(edges, label, keywords):
    shown = 0
    for db_id, drug_name, target_name in edges:
        if any(k in target_name.lower() for k in keywords) and shown < 20:
            print(f"  {drug_name} -> {target_name}")
            shown += 1


def main():
    parser = argparse.ArgumentParser(description="Create treatment edges from DrugBank indications")
    parser.add_argument("--apply", action="store_true", help="Write edges to Memgraph (default: dry run)")
    parser.add_argument("--phenotypes", action="store_true", help="Also create drugTreatsPhenotype edges")
    args = parser.parse_args()

    if not os.path.exists(DRUGBANK_XML):
        print(f"Error: DrugBank XML not found at {DRUGBANK_XML}")
        sys.exit(1)

    uri = os.getenv("MEMGRAPH_URI", "bolt://localhost:7687")
    password = os.getenv("MEMGRAPH_PASSWORD", "")
    driver = GraphDatabase.driver(uri, auth=("", password))

    # --- Disease matching ---
    print("Fetching disease names from graph...")
    disease_names = get_node_names(driver, "Disease", "diseaseName")
    print(f"  {len(disease_names)} disease names (>= {MIN_NAME_LEN} chars)")
    disease_patterns = build_patterns(disease_names)

    print(f"Parsing DrugBank XML: {DRUGBANK_XML}")
    disease_edges, drugs_processed = match_indications(DRUGBANK_XML, disease_patterns)
    print(f"  Processed {drugs_processed} drugs with indication text")
    print(f"  Found {len(disease_edges)} drug-disease matches")
    print(f"  Unique drugs: {len(set(e[0] for e in disease_edges))}, "
          f"unique diseases: {len(set(e[2] for e in disease_edges))}")

    cvd_keywords = ["tachycardia", "hypertension", "heart failure", "atrial fibrillation",
                     "myocardial infarction", "coronary", "stroke", "arrhythmia"]
    print("\nCVD-relevant disease matches (sample):")
    print_samples(disease_edges, "disease", cvd_keywords)

    # --- Phenotype matching ---
    phenotype_edges = []
    if args.phenotypes:
        print("\nFetching phenotype names from graph...")
        phenotype_names = get_node_names(driver, "Phenotype", "phenotypeName")
        print(f"  {len(phenotype_names)} phenotype names (>= {MIN_NAME_LEN} chars)")
        phenotype_patterns = build_patterns(phenotype_names, blocklist=PHENOTYPE_BLOCKLIST)
        print(f"  {len(phenotype_patterns)} after blocklist filtering")

        print(f"Parsing DrugBank XML for phenotype matches...")
        phenotype_edges, _ = match_indications(DRUGBANK_XML, phenotype_patterns)
        print(f"  Found {len(phenotype_edges)} drug-phenotype matches")
        print(f"  Unique drugs: {len(set(e[0] for e in phenotype_edges))}, "
              f"unique phenotypes: {len(set(e[2] for e in phenotype_edges))}")

        print("\nTachycardia phenotype matches:")
        print_samples(phenotype_edges, "phenotype",
                      ["tachycardia", "bradycardia", "arrhythmia", "palpitation"])

    # --- Apply ---
    if args.apply:
        print(f"\nWriting {len(disease_edges)} disease edges (source: {SOURCE_LABEL})...")
        created = write_disease_edges(driver, disease_edges)
        print(f"  Created {created} new drugTreatsDisease edges")

        if args.phenotypes and phenotype_edges:
            print(f"\nWriting {len(phenotype_edges)} phenotype edges (source: {SOURCE_LABEL})...")
            created = write_phenotype_edges(driver, phenotype_edges)
            print(f"  Created {created} new drugTreatsPhenotype edges")

        with driver.session() as s:
            r = s.run("MATCH ()-[r:drugTreatsDisease]->() RETURN count(r) AS c").single()
            print(f"\n  Total drugTreatsDisease edges: {r['c']}")
            r = s.run("MATCH ()-[r:drugTreatsPhenotype]->() RETURN count(r) AS c").single()
            print(f"  Total drugTreatsPhenotype edges: {r['c']}")
    else:
        print(f"\nDry run complete. Use --apply to write edges.")
        if not args.phenotypes:
            print("Add --phenotypes to also match against Phenotype nodes (e.g., tachycardia).")

    driver.close()


if __name__ == "__main__":
    main()
