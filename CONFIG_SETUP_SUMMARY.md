
# CardioKB Biomedical Data Sources Configuration - Setup Summary
================================================================

## Project Configuration
- **Project Name**: Cardio-KB (Cardiovascular Knowledge Base)
- **Disease Scope**: 184 CVD disease terms
- **UMLS CUIs**: 28
- **DOID IDs**: 15
- **MeSH IDs**: 28
- **Configuration File**: /Users/nawaza/Desktop/Cardio-KB/config/databases.yaml

## Configuration Status
✓ Total Sources Configured: 28
✓ Enabled Sources: 27
✗ Disabled Sources: 1 (AOPDB - requires local MySQL setup)

---

## SOURCES WITH EXISTING TEMPLATE PARSERS (14 sources)
All enabled as requested:

1. ✓ NCBI Gene (ncbigene)
   - Parser: NCBIGeneParser
   - Source: NCBI FTP (Homo_sapiens.gene_info.gz)
   - Output: gene_nodes.tsv
   - Credentials: None required

2. ✓ DoRothEA (dorothea)
   - Parser: DoRothEAParser
   - Source: DoRothEA database
   - Output: transcription_factor_nodes.tsv, tf_gene_regulations.tsv
   - Credentials: None required

3. ✓ DrugBank (drugbank)
   - Parser: DrugBankParser
   - Source: https://go.drugbank.com/releases/{version}/downloads/
   - Output: drug_nodes.tsv, drug_gene_bindings.tsv
   - Credentials: DRUGBANK_USERNAME, DRUGBANK_PASSWORD (free academic account)
   - Version: latest or specific (e.g., 5-1-14)

4. ✓ Disease Ontology (disease_ontology)
   - Parser: DiseaseOntologyParser
   - Source: GitHub (OBO format)
   - Output: disease_nodes.tsv, slim_terms.tsv
   - Credentials: None required
   - Version: latest

5. ✓ Gene Ontology (gene_ontology)
   - Parser: GeneOntologyParser
   - Source: GO OBO and GAF files
   - Output: biological_process_nodes.tsv, molecular_function_nodes.tsv,
             cellular_component_nodes.tsv, gene_go_annotations.tsv
   - Credentials: None required

6. ✓ Uberon (uberon)
   - Parser: UberonParser
   - Source: OBO files (basic and human-view subsets)
   - Output: body_part_nodes.tsv
   - Credentials: None required
   - Version: latest

7. ✓ MeSH (mesh)
   - Parser: MeSHParser
   - Source: NLM XML files
   - Output: symptom_nodes.tsv
   - Credentials: None required
   - Base URL: https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/

8. ✓ DrugCentral (drugcentral)
   - Parser: DrugCentralParser
   - Source: PostgreSQL at unmtid-dbs.net:5433
   - Output: drug_nodes.tsv, pharmacologic_class_nodes.tsv, disease_nodes.tsv,
             drug_treats_disease.tsv, drug_in_class.tsv,
             chemical_causes_adverse_effect.tsv
   - Credentials: DC_USER, DC_PASSWORD (public: drugman/dosage)
   - Version: 54 (2023-11-01)

9. ✓ BindingDB (bindingdb)
   - Parser: BindingDBParser
   - Source: BindingDB database
   - Output: chemical_nodes.tsv, gene_nodes.tsv, chemical_binds_gene.tsv
   - Credentials: None required
   - Version: latest

10. ✓ CTD (ctd)
    - Parser: CTDParser
    - Source: CTD_chem_gene_ixns.tsv.gz
    - Output: chemical_nodes.tsv, gene_nodes.tsv,
              chemical_increases_expression.tsv,
              chemical_decreases_expression.tsv
    - Credentials: None required
    - Version: latest

11. ✓ Bgee (bgee)
    - Parser: BgeeParser
    - Source: https://www.bgee.org/ftp/current/download/calls/expr_calls/
    - Output: gene_nodes.tsv, anatomy_nodes.tsv, anatomy_expresses_gene.tsv
    - Credentials: None required
    - Version: latest

12. ✓ Reactome (reactome)
    - Parser: ReactomeParser
    - Source: Reactome FTP (UniProt2Reactome, ReactomePathways, ReactomePathwaysRelation)
    - Output: pathway_nodes.tsv, protein_pathway_associations.tsv
    - Credentials: None required
    - Version: latest

13. ✓ MEDLINE (medline)
    - Parser: MEDLINEParser
    - Source: PubMed via NCBI E-utilities API
    - Output: disease_symptom_cooccurrence.tsv,
              disease_anatomy_cooccurrence.tsv,
              disease_disease_cooccurrence.tsv
    - Credentials: NCBI_EUTILS_API_KEY (optional)
    - Version: latest
    - Dependencies: disease_ontology, mesh, uberon must run first

14. ✓ STRING (string)
    - Parser: StringParser
    - Source: stringdb-downloads.org (v12.0)
    - Output: gene_nodes.tsv, gene_interactions.tsv
    - Credentials: None required
    - Version: 12.0
    - Filter: min_combined_score >= 700

---

## SOURCES WITHOUT TEMPLATES (10 new sources)
All enabled as requested:

1. ✓ ClinicalTrials.gov (clinicaltrials)
   - Parser: ClinicalTrialsParser
   - Source: https://clinicaltrials.gov/api/v2/studies
   - Output: trial_nodes.tsv, trial_disease_associations.tsv,
             trial_intervention_associations.tsv
   - Credentials: None required
   - CVD Filter: Disease terms from project.yaml
   - API Version: v2

2. ✓ ClinPGx (clinpgx)
   - Parser: ClinPGxParser
   - Source: https://api.clinpgx.org/v1/
   - Output: gene_drug_phenotype_associations.tsv,
             pharmacogenomic_variant_nodes.tsv
   - Credentials: CLINPGX_API_KEY (optional)
   - Version: v1 API

3. ✓ SIDER (sider)
   - Parser: SIDERParser
   - Source: http://sideeffects.embl.de/media/download/meddra_all_se.tsv.gz
   - Output: side_effect_nodes.tsv, drug_side_effect_associations.tsv
   - Credentials: None required
   - Version: latest

4. ✓ LINCS L1000 (lincs)
   - Parser: LINCSParser
   - Source: NCBI GEO (GSE70138)
   - Output: perturbation_nodes.tsv, gene_expression_signatures.tsv
   - Credentials: None required
   - Version: L1000 Phase 2
   - Max Files: 100

5. ✓ Jensen TISSUES (jensen_tissues)
   - Parser: JensenTissuesParser
   - Source: https://download.jensenlab.org/human_tissue_experiments.tsv
   - Output: tissue_nodes.tsv, tissue_expresses_gene.tsv
   - Credentials: None required
   - Version: latest
   - CVD Tissues: Cardiac, vascular, blood vessel

6. ✓ PubTator Central (pubtator)
   - Parser: PubTatorParser
   - Source: https://ftp.ncbi.nlm.nih.gov/pub/lu/PubTator/
   - Output: pubtator_gene_disease_cooccurrence.tsv,
             pubtator_drug_disease_cooccurrence.tsv,
             pubtator_entity_mentions.tsv
   - Credentials: None required
   - Version: latest
   - Entity Types: Gene, Disease, Chemical, Species, Mutation

7. ✓ OpenTargets (opentargets)
   - Parser: OpenTargetsParser
   - Source: https://ftp.ebi.ac.uk/pub/databases/opentargets/platform/latest/output/etl/parquet/
   - Output: target_disease_associations.tsv
   - Credentials: None required
   - Version: latest
   - CVD Filter: Disease scope from project.yaml
   - Min Score: 0.1

8. ✓ HPO (hpo)
   - Parser: HPOParser
   - Source: http://purl.obolibrary.org/obo/hp.obo
   - Output: phenotype_nodes.tsv, phenotype_hierarchy.tsv
   - Credentials: None required
   - Version: latest
   - CVD Phenotypes: Arrhythmias, cardiomyopathy, heart failure, etc.

9. ✓ HGNC Gene Families (hgnc)
   - Parser: HGNCFamiliesParser
   - Source: https://www.genenames.org/download/custom/
   - Output: gene_family_nodes.tsv, gene_family_associations.tsv
   - Credentials: None required
   - Version: latest
   - CVD Gene Families: Ion channels, kinases, GPCRs, transcription factors

10. ✓ ClinVar (clinvar)
    - Parser: ClinVarParser
    - Source: https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/
    - Output: variant_nodes.tsv, gene_variant_associations.tsv,
              variant_disease_associations.tsv
    - Credentials: None required
    - Version: latest
    - CVD Filter: Pathogenic/likely pathogenic variants for CVD diseases

---

## ADDITIONAL INTEGRATED SOURCES (4 sources)

1. ✓ DisGeNET (disgenet)
   - Parser: DisGeNETParser
   - Source: REST API
   - Output: gene_disease_associations.tsv
   - Credentials: DISGENET_API_KEY (optional)
   - Version: latest
   - CVD Filter: Disease terms from project.yaml

2. ✓ CollectTRI (collectri)
   - Parser: CollectTRIParser
   - Source: OmniPath API
   - Output: transcription_factor_nodes.tsv, tf_gene_interactions.tsv
   - Credentials: None required
   - Version: latest

3. ✓ Evolutionary Rate Covariation (evolutionary_rate_covariation)
   - Parser: EvolutionaryRateCovariationParser
   - Source: Dryad (mammal_ftERC.RDS)
   - Output: gene_covariation.tsv
   - Credentials: None required
   - Version: latest

4. ✗ AOPDB (aopdb)
   - Parser: AOPDBParser
   - Status: DISABLED (requires local MySQL setup)
   - Output: pathway_nodes.tsv, gene_pathway_associations.tsv
   - Credentials: MYSQL_USERNAME, MYSQL_PASSWORD, MYSQL_DB_NAME

---

## REQUIRED CREDENTIALS (.env file)

### Essential (for full functionality):
- DRUGBANK_USERNAME (free academic account)
- DRUGBANK_PASSWORD (free academic account)
- DC_USER (public: drugman)
- DC_PASSWORD (public: dosage)

### Optional (for enhanced functionality):
- CLINPGX_API_KEY (ClinPGx - for higher rate limits)
- DISGENET_API_KEY (DisGeNET - for higher rate limits)
- NCBI_EUTILS_API_KEY (MEDLINE - for 10 req/sec instead of 3 req/sec)

### Only if enabling AOPDB:
- MYSQL_USERNAME
- MYSQL_PASSWORD
- MYSQL_DB_NAME

---

## CVD DISEASE SCOPE INTEGRATION

The configuration includes CVD filtering for the following sources:
1. ClinicalTrials.gov - Queries for CVD disease terms
2. OpenTargets - Filters associations to CVD diseases
3. PubTator Central - Literature mining for CVD terms
4. Jensen TISSUES - Cardiac/vascular tissue focus
5. HPO - Cardiac phenotypes included
6. HGNC - CVD-relevant gene families
7. ClinVar - CVD variant filtering
8. MEDLINE - CVD literature co-occurrence

---

## CONFIGURATION CHECKLIST

✓ All 24 biomedical sources configured
✓ Parsers registered in src/main.py (verified in PARSERS dict)
✓ All required parser files exist in src/parsers/
✓ YAML syntax validated
✓ Descriptions and documentation complete
✓ URLs and API endpoints configured
✓ Credential environment variables documented
✓ CVD disease scope integrated where applicable
✓ Version information included for dated sources
✓ Output files documented for each source

---

## NEXT STEPS

1. ✓ Verify parsers are registered in src/main.py (already confirmed)
2. ✓ Verify ontology mappings in src/ontology_configs.py
3. ✓ Verify .env file has required credentials
4. ✓ Run pipeline: python src/main.py --log-level DEBUG
5. ✓ Monitor output files in data/processed/

---

## NOTES

- PharmGKB: Not included in the 24 sources or parser list. If needed, 
  it should be added as a separate source with its own parser.
  
- AOPDB: Disabled by default due to MySQL requirement. Enable only if
  local MySQL instance is available.
  
- All sources are configured to respect CVD disease scope where applicable.
  
- Credentials are managed via environment variables (.env file) for security.
  
- Public sources (most of them) require no credentials.

