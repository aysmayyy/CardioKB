
# CardioKB Data Sources

## Summary
- **32 databases** — 32 parsers, all working
- **373,869 nodes** | **26,581,028 relationships** | **18 node types** | **35 relationship types** | **25 sources**

## Phase 1: Core Parsers

| # | Database | URL | Access Type | Parser Status | Notes |
|---|----------|-----|-------------|---------------|-------|
| 1 | ClinicalTrials.gov | AACT bulk download | Public | Working | 576,029 trials, all diseases |
| 2 | ClinPGx (PharmGKB successor) | https://api.clinpgx.org/v1/data/ | Public API | Working | 454 annotations, 1,060 variants, 294 AFFECTS_RESPONSE_TO edges |
| 3 | NCBI Gene | https://ftp.ncbi.nlm.nih.gov/gene/DATA/GENE_INFO/ | Public FTP | Working | 193,687 genes |
| 4 | DoRothEA (OmniPath) | https://omnipathdb.org/interactions?datasets=dorothea | Public API | Working | 15,092 TF-gene interactions |
| 5 | OMIM | https://api.omim.org/api | API key required | Working | 1,556 CVD diseases, 1,632 gene-disease edges |
| 6 | DisGeNET | https://api.disgenet.com/api/v1 | API key required | Working | 341 DO-matched + 559 new diseases, 5,010 gene-disease edges |
| 7 | DrugBank | https://go.drugbank.com/releases/ | XML file or login | Working | 19,842 drugs, 19,047 drug-target edges |
| 8 | AOP-DB | https://gaftp.epa.gov/EPADataCommons/ORD/AOP-DB/ | SQL dump or MySQL | Working | 173,500 chemicals, 4,646 pathways, 187,247 gene-pathway edges |

## Phase 2: Hetionet Component Parsers

| # | Database | URL | Access Type | Parser Status | Notes |
|---|----------|-----|-------------|---------------|-------|
| 9 | Disease Ontology (DOID) | https://raw.githubusercontent.com/DiseaseOntology/HumanDiseaseOntology/main/src/ontology/doid.obo | Public | Working | 12,012 diseases |
| 10 | Gene Ontology (GO) | http://current.geneontology.org/ontology/go-basic.obo | Public | Working | 38,739 GO terms, 376,442 annotations |
| 11 | Uberon (anatomy) | http://purl.obolibrary.org/obo/uberon.obo | Public | Working | 14,675 anatomy nodes |
| 12 | MeSH (symptoms) | https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/ | Public | Working | 966 symptom nodes |
| 13 | SIDER (side effects) | https://raw.githubusercontent.com/dhimmel/SIDER4/.../data/ | Public | Working | 5,734 side effects, 153,663 edges |
| 14 | LINCS L1000 (gene expression) | https://raw.githubusercontent.com/dhimmel/lincs/.../data/ | Public | Working | 336,999 edges |
| 15 | MEDLINE (literature cooccurrence) | https://raw.githubusercontent.com/dhimmel/medline/master/data/ | Public | Working | 7,213 cooccurrence edges |
| 16 | DrugCentral (drug-disease) | https://unmtid-dbs.net/download/ | Public | Working | 14,572 relationships |
| 17 | GWAS Catalog (associations) | https://www.ebi.ac.uk/gwas/api/search/downloads/full | Public | Working | 90,578 gene-disease associations (3-strategy DOID remap) |
| 18 | BindingDB (drug-target) | https://www.bindingdb.org/bind/downloads/ | Public | Working | 23,954 drug-gene bindings via UniProt→Entrez mapping |
| 19 | PubTator Central (literature mining) | https://ftp.ncbi.nlm.nih.gov/pub/lu/PubTatorCentral/ | Public FTP | Working | 69M+ literature edges |
| 20 | CTD (chemical-gene) | http://ctdbase.org/reports/CTD_chem_gene_ixns.tsv.gz | Public | Working | 677,015 expression edges |
| 21 | Bgee (gene expression) | https://www.bgee.org/ftp/current/download/calls/expr_calls/ | Public FTP | Working | 6,609,112 expression edges |
| 22 | Hetionet (precomputed edges) | https://github.com/hetio/hetionet/raw/main/hetnet/tsv/ | Public | Working | 613,470 precomputed edges |
| 23 | Jensen Lab DISEASES | https://diseases.jensenlab.org/ | Public | Working | Gene-disease associations |
| 24 | Jensen Lab TISSUES | https://tissues.jensenlab.org/ | Public | Working | 988,006 gene-tissue edges, 262 BTO tissue nodes |
| 25 | HPO (Human Phenotype Ontology) | https://hpo.jax.org/ | Public | Working | 19,389 phenotypes, 270,272 gene-phenotype edges |
| 26 | Reactome | https://reactome.org/ | Public | Working | 2,806 pathways, 147,005 geneInPathway edges |
| 27 | WikiPathways | https://www.wikipathways.org/ | Public | Working | 982 pathways, 40,039 geneInPathway edges |
| 28 | STRING | https://string-db.org/ | Public | Working | 228,193 geneInteractsWithGene edges (confidence > 700) |
| 29 | OpenTargets | https://platform.opentargets.org/ | Public | Working | 2,345,386 geneAssociatesWithDisease edges (EFO→DOID mapping) |

## Phase 3: Agent-Generated Parsers

| # | Database | URL | Access Type | Parser Status | Notes |
|---|----------|-----|-------------|---------------|-------|
| 30 | HGNC | https://www.genenames.org/ | Public | Working | 44,361 Gene nodes enriched (xrefHGNC, geneName, locusGroup, locusType) |
| 31 | HGNC Gene Families | https://www.genenames.org/ | Public | Working | 1,934 GeneFamily nodes, 33,967 geneInFamily edges |
| 32 | ClinVar | https://ftp.ncbi.nlm.nih.gov/pub/clinvar/ | Public FTP | Working | 4,486,982 Variant nodes, 5.7M disease-variant + 4.5M gene-variant edges |

## Credential-Gated Sources

| Parser | Required Env Vars | Status |
|--------|-------------------|--------|
| OMIMParser | `OMIM_API_KEY` | Loaded |
| DisGeNETParser | `DISGENET_API_KEY` | Loaded |
| DrugBankParser | `DRUGBANK_USERNAME`, `DRUGBANK_PASSWORD` (or XML file) | Loaded via XML |
| AOPDBParser | `MYSQL_USERNAME`, `MYSQL_PASSWORD` (or SQL dump) | Loaded via SQL dump |

## Relationship Source Labels (25)

All relationships carry a `source` property identifying the originating database:

`AOP-DB`, `Bgee`, `BindingDB`, `CTD`, `ClinPGx`, `ClinicalTrials.gov`, `DisGeNET`, `DoRothEA`, `DrugBank`, `DrugCentral`, `GWAS Catalog`, `Gene Ontology`, `HGNC`, `HPO`, `Hetionet`, `Jensen DISEASES`, `Jensen TISSUES`, `LINCS L1000`, `MEDLINE`, `OMIM`, `OpenTargets`, `PubTator`, `Reactome`, `SIDER`, `STRING`, `WikiPathways`

Note: Disease Ontology contributes nodes only (no relationship source label). HGNC enriches Gene nodes (no relationship source); HGNC Families uses `HGNC` as source label.
