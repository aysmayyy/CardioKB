"""
Enrich Drug nodes with PubChem CID cross-references.

Uses DrugBank drugs.tsv (drugbank_id → pubchem_cid) and CTD chemicals
vocabulary (MeSH → PubChemCID) to fill Drug.xrefPubChem.

Run after graph loading to fill Drug.xrefPubChem for nodes that lack it.
"""

import csv
import gzip
import logging
from pathlib import Path

from neo4j import GraphDatabase

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CTD_CHEMICALS_PATH = PROJECT_ROOT / "data" / "raw" / "ctd" / "CTD_chemicals.tsv.gz"
DRUGBANK_TSV = PROJECT_ROOT / "data" / "processed" / "drugbank" / "drugs.tsv"

MEMGRAPH_URI = "bolt://localhost:7687"


def enrich(driver=None):
    """Enrich Drug nodes missing xrefPubChem. Returns count of updated nodes."""
    db_to_pc = {}
    db_name_to_pc = {}
    db_cas_to_pc = {}

    if DRUGBANK_TSV.exists():
        with open(DRUGBANK_TSV) as f:
            for row in csv.DictReader(f, delimiter="\t"):
                pcid = row.get("pubchem_cid", "").strip()
                if not pcid:
                    continue
                dbid = row["drugbank_id"].strip()
                name = row["drug_name"].strip().lower()
                cas = row.get("cas_number", "").strip()
                if dbid:
                    db_to_pc[dbid] = pcid
                if name:
                    db_name_to_pc[name] = pcid
                if cas:
                    db_cas_to_pc[cas] = pcid

    mesh_to_pc = {}
    ctd_name_to_pc = {}
    ctd_cas_to_pc = {}

    if CTD_CHEMICALS_PATH.exists():
        with gzip.open(CTD_CHEMICALS_PATH, "rt") as f:
            for line in f:
                if line.startswith("#"):
                    continue
                fields = line.rstrip("\n").split("\t")
                if len(fields) < 4:
                    continue
                pcid_raw = fields[3].strip()
                if not pcid_raw:
                    continue
                pcid = pcid_raw.replace("CID:", "")
                mesh_id = fields[1].strip()
                if not mesh_id.startswith("MESH:"):
                    mesh_id = f"MESH:{mesh_id}"
                name = fields[0].strip().lower()
                cas = fields[2].strip()

                mesh_to_pc[mesh_id] = pcid
                if name:
                    ctd_name_to_pc[name] = pcid
                if cas:
                    ctd_cas_to_pc[cas] = pcid

    log.info(
        "PubChem lookups: %d DrugBank, %d MeSH, %d names, %d CAS",
        len(db_to_pc),
        len(mesh_to_pc),
        len(db_name_to_pc) + len(ctd_name_to_pc),
        len(db_cas_to_pc) + len(ctd_cas_to_pc),
    )

    own_driver = driver is None
    if own_driver:
        driver = GraphDatabase.driver(MEMGRAPH_URI, auth=("", ""))

    try:
        with driver.session() as s:
            r = s.run(
                "MATCH (d:Drug) "
                "WHERE d.xrefPubChem IS NULL OR d.xrefPubChem = '' "
                "RETURN d.id AS id, toLower(d.commonName) AS name, "
                "d.xrefMeSH AS mesh, d.xrefCAS AS cas, d.xrefDrugBank AS drugbank"
            )
            missing = [dict(rec) for rec in r]

        log.info("Drug nodes missing xrefPubChem: %d", len(missing))

        batch = []
        for d in missing:
            pcid = None
            db = d.get("drugbank") or ""
            mesh = d.get("mesh") or ""
            name = d.get("name") or ""
            cas = d.get("cas") or ""

            if db and db in db_to_pc:
                pcid = db_to_pc[db]
            elif mesh and mesh in mesh_to_pc:
                pcid = mesh_to_pc[mesh]
            elif name and name in db_name_to_pc:
                pcid = db_name_to_pc[name]
            elif name and name in ctd_name_to_pc:
                pcid = ctd_name_to_pc[name]
            elif cas and cas in db_cas_to_pc:
                pcid = db_cas_to_pc[cas]
            elif cas and cas in ctd_cas_to_pc:
                pcid = ctd_cas_to_pc[cas]

            if pcid:
                batch.append({"id": d["id"], "pubchem": pcid})

        log.info("PubChem CIDs to apply: %d", len(batch))

        updated = 0
        for i in range(0, len(batch), 500):
            chunk = batch[i : i + 500]
            with driver.session() as s:
                result = s.run(
                    "UNWIND $batch AS row "
                    "MATCH (d:Drug {id: row.id}) "
                    "SET d.xrefPubChem = row.pubchem "
                    "RETURN count(d) AS updated",
                    batch=chunk,
                )
                updated += result.single()["updated"]

        log.info("Updated %d Drug nodes with xrefPubChem", updated)

        with driver.session() as s:
            r = s.run(
                "MATCH (d:Drug) RETURN count(d) AS total, "
                "count(CASE WHEN d.xrefPubChem IS NOT NULL AND "
                "d.xrefPubChem <> '' THEN 1 END) AS with_pc"
            )
            rec = r.single()
            pct = 100 * rec["with_pc"] / rec["total"] if rec["total"] else 0
            log.info(
                "Drug.xrefPubChem coverage: %d/%d (%.1f%%)",
                rec["with_pc"],
                rec["total"],
                pct,
            )

        return updated
    finally:
        if own_driver:
            driver.close()


if __name__ == "__main__":
    enrich()
