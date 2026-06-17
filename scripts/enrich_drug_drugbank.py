"""
Enrich Drug nodes with DrugBank cross-references.

Maps Drug.xrefMeSH, Drug.commonName, and Drug.xrefCAS to DrugBank IDs
using PubChem CID, CAS number, name, and synonym bridges via the CTD
chemicals vocabulary and DrugBank drugs.tsv.

Run after graph loading to fill Drug.xrefDrugBank for nodes that lack it.
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


def _build_drugbank_lookups():
    """Build name/CAS/PubChem → DrugBank ID lookups from drugs.tsv."""
    name_map = {}
    cas_map = {}
    pubchem_map = {}

    if not DRUGBANK_TSV.exists():
        log.warning("DrugBank drugs.tsv not found at %s", DRUGBANK_TSV)
        return name_map, cas_map, pubchem_map

    with open(DRUGBANK_TSV) as f:
        for row in csv.DictReader(f, delimiter="\t"):
            dbid = row["drugbank_id"].strip()
            name = row["drug_name"].strip().lower()
            cas = row.get("cas_number", "").strip()
            pcid = row.get("pubchem_cid", "").strip()
            if name:
                name_map[name] = dbid
            if cas:
                cas_map[cas] = dbid
            if pcid:
                pubchem_map[pcid] = dbid

    return name_map, cas_map, pubchem_map


def _build_mesh_info():
    """Build MeSH → {name, cas, pubchem, synonyms} from CTD chemicals."""
    mesh_info = {}
    if not CTD_CHEMICALS_PATH.exists():
        log.warning("CTD chemicals file not found at %s", CTD_CHEMICALS_PATH)
        return mesh_info

    with gzip.open(CTD_CHEMICALS_PATH, "rt") as f:
        for line in f:
            if line.startswith("#"):
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 2:
                continue
            mesh_id = fields[1].strip()
            if not mesh_id.startswith("MESH:"):
                mesh_id = f"MESH:{mesh_id}"
            mesh_info[mesh_id] = {
                "name": fields[0].strip().lower(),
                "cas": fields[2].strip() if len(fields) > 2 else "",
                "pubchem": fields[3].strip().replace("CID:", "")
                if len(fields) > 3
                else "",
                "synonyms": fields[11].strip() if len(fields) > 11 else "",
                "ctd_synonyms": fields[12].strip() if len(fields) > 12 else "",
            }
    return mesh_info


def enrich(driver=None):
    """Enrich Drug nodes missing xrefDrugBank. Returns count of updated nodes."""
    db_name, db_cas, db_pubchem = _build_drugbank_lookups()
    mesh_info = _build_mesh_info()

    log.info(
        "Lookups: %d names, %d CAS, %d PubChem, %d MeSH entries",
        len(db_name),
        len(db_cas),
        len(db_pubchem),
        len(mesh_info),
    )

    def _resolve_mesh(mesh):
        info = mesh_info.get(mesh, {})
        if not info:
            return None
        pc = info.get("pubchem", "")
        if pc and pc in db_pubchem:
            return db_pubchem[pc]
        cas = info.get("cas", "")
        if cas and cas in db_cas:
            return db_cas[cas]
        name = info.get("name", "")
        if name and name in db_name:
            return db_name[name]
        for field in ["synonyms", "ctd_synonyms"]:
            for syn in info.get(field, "").split("|"):
                syn = syn.strip().lower()
                if syn and syn in db_name:
                    return db_name[syn]
        return None

    own_driver = driver is None
    if own_driver:
        driver = GraphDatabase.driver(MEMGRAPH_URI, auth=("", ""))

    try:
        with driver.session() as s:
            r = s.run(
                "MATCH (d:Drug) "
                "WHERE d.xrefDrugBank IS NULL OR d.xrefDrugBank = '' "
                "RETURN d.id AS id, toLower(d.commonName) AS name, "
                "d.xrefMeSH AS mesh, d.xrefCAS AS cas"
            )
            missing = [dict(rec) for rec in r]

        log.info("Drug nodes missing xrefDrugBank: %d", len(missing))

        batch = []
        for d in missing:
            dbid = None
            mesh = d.get("mesh") or ""
            name = d.get("name") or ""
            cas = d.get("cas") or ""
            if mesh:
                dbid = _resolve_mesh(mesh)
            if not dbid and name and name in db_name:
                dbid = db_name[name]
            if not dbid and cas and cas in db_cas:
                dbid = db_cas[cas]
            if dbid:
                batch.append({"id": d["id"], "drugbank": dbid})

        log.info("DrugBank IDs to apply: %d", len(batch))

        updated = 0
        for i in range(0, len(batch), 500):
            chunk = batch[i : i + 500]
            with driver.session() as s:
                result = s.run(
                    "UNWIND $batch AS row "
                    "MATCH (d:Drug {id: row.id}) "
                    "SET d.xrefDrugBank = row.drugbank "
                    "RETURN count(d) AS updated",
                    batch=chunk,
                )
                updated += result.single()["updated"]

        log.info("Updated %d Drug nodes with xrefDrugBank", updated)

        with driver.session() as s:
            r = s.run(
                "MATCH (d:Drug) RETURN count(d) AS total, "
                "count(CASE WHEN d.xrefDrugBank IS NOT NULL AND "
                "d.xrefDrugBank <> '' THEN 1 END) AS with_db"
            )
            rec = r.single()
            pct = 100 * rec["with_db"] / rec["total"] if rec["total"] else 0
            log.info(
                "Drug.xrefDrugBank coverage: %d/%d (%.1f%%)",
                rec["with_db"],
                rec["total"],
                pct,
            )

        return updated
    finally:
        if own_driver:
            driver.close()


if __name__ == "__main__":
    enrich()
