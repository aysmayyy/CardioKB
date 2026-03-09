
# CardioKB Data Sources

| # | Database | URL | Access Type | Have Access? | Parser Status |
|---|----------|-----|-------------|--------------|---------------|
| 1 | ClinicalTrials.gov | https://clinicaltrials.gov/api/v2/studies | Public API | Yes | Working |
| 2 | ClinPGx (PharmGKB successor) | https://api.clinpgx.org/v1/data/ | Public API | Yes | Working |
| 3 | OMIM | https://api.omim.org/api | API key required | No (`OMIM_API_KEY`) | Working (credential-gated) |
| 4 | DisGeNET | https://api.disgenet.com/api/v1 | API key optional | Partial (file fallback) | Working |
| 5 | NCBI Gene | https://ftp.ncbi.nlm.nih.gov/gene/DATA/GENE_INFO/Mammalia/Homo_sapiens.gene_info.gz | Public FTP | Yes | Working |
| 6 | DoRothEA (OmniPath) | https://omnipathdb.org/interactions?datasets=dorothea | Public API | Yes | Working |
| 7 | DrugBank | https://go.drugbank.com/releases/ | Login required | No (`DRUGBANK_USERNAME`, `DRUGBANK_PASSWORD`) | Working (credential-gated) |
| 8 | AOP-DB | https://gaftp.epa.gov/EPADataCommons/ORD/AOP-DB/ | MySQL login required | No (`MYSQL_USERNAME`, `MYSQL_PASSWORD`, `MYSQL_DB_NAME`) | Working (credential-gated) |
| 9 | Disease Ontology | https://raw.githubusercontent.com/DiseaseOntology/HumanDiseaseOntology/main/src/ontology/doid.obo | Public | Yes | Working |
| 10 | Gene Ontology | http://current.geneontology.org/ontology/go-basic.obo | Public | Yes | Working |
| 11 | Uberon | http://purl.obolibrary.org/obo/uberon.obo | Public | Yes | Working |
| 12 | SIDER | https://raw.githubusercontent.com/dhimmel/SIDER4/.../data/ | Public | Yes | Working |
| 13 | LINCS L1000 | https://raw.githubusercontent.com/dhimmel/lincs/.../data/ | Public | Yes | Working |
| 14 | PubTator Central | https://ftp.ncbi.nlm.nih.gov/pub/lu/PubTatorCentral/ | Public FTP | Yes | Working |
| 15 | CTD | http://ctdbase.org/reports/CTD_chem_gene_ixns.tsv.gz | Public | Yes | Working |
| 16 | Bgee | https://www.bgee.org/ftp/current/download/calls/expr_calls/ | Public FTP | Yes | Working |
| 17 | Hetionet (precomputed) | https://github.com/hetio/hetionet/raw/main/hetnet/tsv/hetionet-v1.0-edges.sif.gz | Public | Yes | Working |
| 18 | MeSH | https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/desc2025.xml | Public | Yes | Broken (no data parsed) |
| 19 | MEDLINE Cooccurrence | https://raw.githubusercontent.com/dhimmel/medline/master/data/ | Public | No (stale URLs) | Broken (stale URLs) |
| 20 | DrugCentral | https://unmtid-dbs.net/download/drugcentral.dump.01012025.sql.gz | Public | No (download fails) | Broken (download failure) |
| 21 | GWAS Catalog | https://www.ebi.ac.uk/gwas/api/search/downloads/full | Public | No (download fails) | Broken (download failure) |
| 22 | BindingDB | https://www.bindingdb.org/bind/downloads/BindingDB_All_2024m11.tsv.zip | Public | No (download fails) | Broken (download failure) |

**Totals:** 22 databases — 13 working, 5 broken/stale, 4 credential-gated (3 without keys, 1 partial)
