"""
Load drugTreatsDisease edges from two sources:
1. DrugCentral treats TSV (struct_id -> DrugBank ID, UMLS CUI -> Disease)
2. ClinicalTrials.gov Phase 3/4 trials (filtered drug-disease treatment pairs)

ClinicalTrials.gov filters (all four must pass for an edge to be created):
  1. primaryPurpose == "TREATMENT" (excludes Prevention, Diagnostic, etc.)
  2. Drug must be in an EXPERIMENTAL arm (excludes comparators/placebos)
  3. Disease must match the first-listed condition (primary condition convention)
  4. Edges carry a trialCount property (number of qualifying trials supporting the pair)
"""

import csv
import logging
import os
import time
from collections import Counter, defaultdict
from neo4j import GraphDatabase
import requests

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger()

MEMGRAPH_URI = os.environ.get("MEMGRAPH_URI", "bolt://localhost:7687")
MEMGRAPH_USER = os.environ.get("MEMGRAPH_USERNAME", "")
MEMGRAPH_PASS = os.environ.get("MEMGRAPH_PASSWORD", "")


def get_driver():
    return GraphDatabase.driver(MEMGRAPH_URI, auth=(MEMGRAPH_USER, MEMGRAPH_PASS))


def build_cui_mapping(driver):
    """Build CUI -> list of Disease graph IDs, handling pipe-separated CUI fields."""
    cui_to_ids = defaultdict(list)
    with driver.session() as s:
        result = s.run("MATCH (d:Disease) RETURN d")
        for rec in result:
            node = dict(rec["d"])
            cui_field = node.get("xrefUmlsCUI", "")
            disease_id = node.get("id", "")
            if cui_field and disease_id:
                for cui in cui_field.split("|"):
                    cui = cui.strip()
                    if cui:
                        cui_to_ids[cui].append(disease_id)
    return cui_to_ids


def load_drugcentral_treats(driver, cui_to_ids):
    """Load drugTreatsDisease from DrugCentral TSV."""
    log.info("=" * 50)
    log.info("DrugCentral drugTreatsDisease")
    log.info("=" * 50)

    struct_to_db = {}
    with open("data/processed/drugcentral/drugs.tsv") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            sid = row["struct_id"]
            dbid = row.get("drugbank_id") or row.get("canonical_drugbank_id", "")
            if sid and dbid:
                struct_to_db[sid] = dbid.strip()
    log.info(f"struct->drugbank mapping: {len(struct_to_db)}")

    batch = []
    skipped_no_db = 0
    skipped_no_disease = 0
    unmatched_cuis = set()

    with open("data/processed/drugcentral/drug_treats_disease.tsv") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            drugbank_id = struct_to_db.get(row["struct_id"])
            if not drugbank_id:
                skipped_no_db += 1
                continue

            disease_ids = cui_to_ids.get(row["disease_id"], [])
            if not disease_ids:
                skipped_no_disease += 1
                unmatched_cuis.add(row["disease_id"])
                continue

            drug_graph_id = f"drug_{drugbank_id.lower()}"
            for did in disease_ids:
                batch.append({"drug_id": drug_graph_id, "disease_id": did})

    log.info(f"Edges to load: {len(batch)}")
    log.info(f"Skipped (no DrugBank ID): {skipped_no_db}")
    log.info(f"Skipped (no Disease match): {skipped_no_disease}")
    if unmatched_cuis:
        log.info(f"Unmatched CUIs: {unmatched_cuis}")

    total = 0
    for i in range(0, len(batch), 1000):
        with driver.session() as s:
            result = s.run(
                """
                UNWIND $batch AS row
                MATCH (d:Drug {id: row.drug_id})
                MATCH (dis:Disease {id: row.disease_id})
                CREATE (d)-[:drugTreatsDisease {source: "DrugCentral"}]->(dis)
                RETURN count(*) AS created
                """,
                batch=batch[i : i + 1000],
            )
            total += result.single()["created"]

    log.info(f"Loaded {total} drugTreatsDisease edges (DrugCentral)\n")
    return total


_CT_API_BASE = "https://clinicaltrials.gov/api/v2/studies"
_CT_BATCH_SIZE = 50
_CT_API_DELAY = 0.35


def _fetch_trial_metadata(trial_ids):
    """Batch-fetch primaryPurpose, arm groups, and conditions from ClinicalTrials.gov API v2.

    Returns dict: nct_id -> {primaryPurpose, experimental_interventions: set, first_condition: str}
    """
    metadata = {}
    batches = [trial_ids[i : i + _CT_BATCH_SIZE] for i in range(0, len(trial_ids), _CT_BATCH_SIZE)]
    log.info(f"Fetching metadata for {len(trial_ids)} trials in {len(batches)} API batches...")

    for batch_idx, batch in enumerate(batches):
        try:
            resp = requests.get(
                _CT_API_BASE,
                params={
                    "filter.ids": ",".join(batch),
                    "fields": (
                        "NCTId,DesignPrimaryPurpose,"
                        "ArmGroupType,ArmGroupLabel,ArmGroupInterventionName,"
                        "InterventionName,InterventionType,Condition"
                    ),
                    "pageSize": _CT_BATCH_SIZE,
                    "format": "json",
                },
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            log.warning(f"  API batch {batch_idx + 1} failed: {exc}")
            continue

        for study in data.get("studies", []):
            proto = study.get("protocolSection", {})
            nct_id = proto.get("identificationModule", {}).get("nctId", "")
            if not nct_id:
                continue

            purpose = (
                proto.get("designModule", {})
                .get("designInfo", {})
                .get("primaryPurpose", "")
            )

            arms_mod = proto.get("armsInterventionsModule", {})
            experimental_interventions = set()
            for arm in arms_mod.get("armGroups", []):
                if arm.get("type") == "EXPERIMENTAL":
                    for iname in arm.get("interventionNames", []):
                        parts = iname.split(": ", 1)
                        experimental_interventions.add(parts[-1].strip().lower())

            conditions = proto.get("conditionsModule", {}).get("conditions", [])
            first_condition = conditions[0].strip().lower() if conditions else ""

            metadata[nct_id] = {
                "primaryPurpose": purpose,
                "experimental_interventions": experimental_interventions,
                "first_condition": first_condition,
            }

        if batch_idx < len(batches) - 1:
            time.sleep(_CT_API_DELAY)

    log.info(f"  Retrieved metadata for {len(metadata)}/{len(trial_ids)} trials")
    return metadata


def load_clinical_trials_treats(driver):
    """Derive drugTreatsDisease from ClinicalTrials Phase 3/4 trials.

    Four filters are applied:
      1. primaryPurpose must be "TREATMENT"
      2. Drug must appear in an EXPERIMENTAL arm (not comparator/placebo)
      3. Disease must match the trial's first-listed condition (primary condition)
      4. Edges carry trialCount = number of qualifying trials for the pair
    """
    log.info("=" * 50)
    log.info("ClinicalTrials.gov drugTreatsDisease (Phase 3/4, filtered)")
    log.info("=" * 50)

    # Step 1: Get all Phase 3/4 trial-drug-disease links from the graph
    with driver.session() as s:
        result = s.run(
            """
            MATCH (t:ClinicalTrial)-[:STUDIES_CONDITION]->(dis:Disease)
            MATCH (t)-[:TESTS_INTERVENTION]->(drug:Drug)
            WHERE t.phase IN ['PHASE3', 'PHASE4', 'PHASE2|PHASE3']
            RETURN t.trialId AS trialId, t.phase AS phase,
                   drug.id AS drug_id, drug.commonName AS drug_name,
                   dis.id AS disease_id, dis.diseaseName AS disease_name
            """
        )
        trial_links = [dict(rec) for rec in result]

    trial_ids = list({r["trialId"] for r in trial_links})
    log.info(f"Phase 3/4 trials with Drug+Disease links: {len(trial_ids)}")
    log.info(f"Unfiltered drug-disease-trial rows: {len(trial_links)}")

    # Step 2: Fetch metadata from ClinicalTrials.gov API
    metadata = _fetch_trial_metadata(trial_ids)

    # Step 3: Apply filters
    skip_no_meta = 0
    skip_purpose = 0
    skip_not_experimental = 0
    skip_not_primary_condition = 0
    pair_trials = defaultdict(list)  # (drug_id, disease_id) -> [trialId, ...]

    for row in trial_links:
        nct = row["trialId"]
        meta = metadata.get(nct)
        if not meta:
            skip_no_meta += 1
            continue

        # Filter 1: primaryPurpose == "TREATMENT"
        if meta["primaryPurpose"] != "TREATMENT":
            skip_purpose += 1
            continue

        # Filter 2: drug must be in an EXPERIMENTAL arm
        drug_name_lower = (row["drug_name"] or "").strip().lower()
        if drug_name_lower not in meta["experimental_interventions"]:
            skip_not_experimental += 1
            continue

        # Filter 3: disease must match the first-listed condition
        disease_name_lower = (row["disease_name"] or "").strip().lower()
        if disease_name_lower != meta["first_condition"]:
            skip_not_primary_condition += 1
            continue

        key = (row["drug_id"], row["disease_id"])
        if nct not in pair_trials[key]:
            pair_trials[key].append(nct)

    log.info(f"Filtered out — no API metadata: {skip_no_meta}")
    log.info(f"Filtered out — purpose != TREATMENT: {skip_purpose}")
    log.info(f"Filtered out — drug not in EXPERIMENTAL arm: {skip_not_experimental}")
    log.info(f"Filtered out — disease not primary condition: {skip_not_primary_condition}")
    log.info(f"Qualifying drug-disease pairs: {len(pair_trials)}")

    # Step 4: Remove pairs that already have a drugTreatsDisease edge from another source
    with driver.session() as s:
        result = s.run(
            """
            MATCH (d:Drug)-[:drugTreatsDisease]->(dis:Disease)
            RETURN d.id AS drug_id, dis.id AS disease_id
            """
        )
        existing = {(rec["drug_id"], rec["disease_id"]) for rec in result}

    new_pairs = []
    for (drug_id, disease_id), trials in pair_trials.items():
        if (drug_id, disease_id) not in existing:
            new_pairs.append({
                "drug_id": drug_id,
                "disease_id": disease_id,
                "trialCount": len(trials),
            })

    log.info(f"Already have drugTreatsDisease: {len(pair_trials) - len(new_pairs)}")
    log.info(f"New edges to load: {len(new_pairs)}")

    # Step 5: Create edges with trialCount property
    total = 0
    for i in range(0, len(new_pairs), 1000):
        with driver.session() as s:
            result = s.run(
                """
                UNWIND $batch AS row
                MATCH (d:Drug {id: row.drug_id})
                MATCH (dis:Disease {id: row.disease_id})
                CREATE (d)-[:drugTreatsDisease {
                    source: "ClinicalTrials.gov",
                    evidence: "Phase3/4",
                    trialCount: row.trialCount
                }]->(dis)
                RETURN count(*) AS created
                """,
                batch=new_pairs[i : i + 1000],
            )
            total += result.single()["created"]

    log.info(f"Loaded {total} drugTreatsDisease edges (ClinicalTrials)\n")
    return total


def load_treats(driver=None):
    """Load all drugTreatsDisease edges. Callable from pipeline or standalone."""
    own_driver = driver is None
    if own_driver:
        driver = get_driver()

    try:
        with driver.session() as s:
            r = s.run(
                """
                MATCH ()-[r:drugTreatsDisease]->()
                WHERE r.source IN ['DrugCentral', 'ClinicalTrials.gov']
                DELETE r RETURN count(r)
                """
            )
            deleted = r.single()[0]
            if deleted:
                log.info(f"Cleared {deleted} existing drugTreatsDisease edges (DrugCentral + ClinicalTrials.gov)\n")

        cui_to_ids = build_cui_mapping(driver)
        log.info(f"CUI mapping: {len(cui_to_ids)} unique CUIs\n")

        dc_count = load_drugcentral_treats(driver, cui_to_ids)
        ct_count = load_clinical_trials_treats(driver)

        log.info("=" * 50)
        log.info("Final verification")
        log.info("=" * 50)
        with driver.session() as s:
            r = s.run(
                """
                MATCH ()-[r:drugTreatsDisease]->()
                RETURN r.source AS source, count(r) AS c
                ORDER BY c DESC
                """
            )
            total = 0
            for rec in r:
                log.info(f"  {rec['source']}: {rec['c']} edges")
                total += rec["c"]
            log.info(f"  TOTAL: {total} drugTreatsDisease edges")

        return total
    finally:
        if own_driver:
            driver.close()


def main():
    load_treats()


if __name__ == "__main__":
    main()
