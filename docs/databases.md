
# CardioKB Data Sources

## Summary
- **26 databases** — 26 parsers, all working, deduplicated (one authoritative source per node/edge type)
- **4,896,243 nodes** | **7,683,150 relationships** | **19 node types** | **43 relationship types** | **23 source labels**
- **3 legacy sources** retained as-is: SIDER (2015), LINCS L1000 (2020), MEDLINE (pinned GitHub commit) — no live API alternatives available

## Direct Parsers (5)

| # | Database | Access Type | Parser Status | Notes |
|---|----------|-------------|---------------|-------|
| 1 | ClinicalTrials.gov | Public API v2 | Working | 85,677 trials, 33,219 STUDIES_CONDITION + 6,090 TESTS_INTERVENTION edges |
| 2 | ClinPGx (PharmGKB successor) | Public API | Working | 1,091 VARIANT_IN, 503 drugLabelAnnotatesGene, 51 drugLabelDescribesDrug, 243 AFFECTS_RESPONSE_TO edges |
| 3 | NCBI Gene | Public FTP | Working | 193,790 genes (nodes only) |
| 4 | DoRothEA (OmniPath) | Public API | Working | 12,985 TF-gene interactions with morScore + confidence |
| 5 | DrugBank | XML file | Working | 19,842 drugs + 4,572 CTD unique Drug nodes, 12,089 drugBindsGene edges |

## Hetionet-Derived Component Parsers (17)

| # | Database | Access Type | Parser Status | Notes |
|---|----------|-------------|---------------|-------|
| 6 | Disease Ontology (DOID) | Public | Working | 12,012 diseases (nodes only) |
| 7 | Gene Ontology (GO) | Public | Working | 50,350 BP + 26,935 MF + 25,794 CC edges |
| 8 | Uberon (anatomy) | Public | Working | 14,937 anatomy nodes (nodes only) |
| 9 | NCBI MeSH (symptoms) | Public | Working | 966 symptom nodes (nodes only) |
| 10 | SIDER (side effects) | Public | Working | 5,734 side effects, 148,518 compoundCausesSideEffect edges. **Legacy: pinned to 2015 GitHub commit; retained — no live API alternative** |
| 11 | LINCS L1000 (gene expression) | Public | Working | 150,540 geneRegulates + 10,218 downreg + 10,278 upreg edges with zScore. **Legacy: pinned to 2020 GitHub commit; retained — clue.io API requires institutional access** |
| 12 | MEDLINE (literature cooccurrence) | Public | Working | 726 anatomy + 524 symptom + 148 disease cooccurrence edges. **Legacy: pinned GitHub commit; retained — unique anatomy/symptom cooccurrence not covered by PubTator** |
| 13 | DrugCentral (drug-disease) | Public | Working | 16,403 pharmacologic class + 779 treats + 189 palliates edges (CUI-to-DOID mapped) |
| 14 | BindingDB (drug-target) | Public | Working | 12,250 chemicalBindsGene edges |
| 15 | PubTator Central (literature mining) | Public FTP | Working | 806,900 diseaseAssociatesWithDisease edges (gene-disease edges removed during dedup) |
| 16 | CTD (chemical-gene) | Public | Working | 4,572 unique Drug nodes (1,713 merged into DrugBank), 116,451 chemicalIncreasesExpression + 97,951 chemicalDecreasesExpression edges |
| 17 | Bgee (gene expression) | Public FTP | Working | 784,026 underexpresses + 1,872 overexpresses edges with expressionScore |
| 18 | Jensen TISSUES (gene-tissue) | Public | Working | 271,657 geneExpressedInBodyPart edges |
| 19 | HPO (Human Phenotype Ontology) | Public | Working | 19,389 phenotypes, 162,994 gene-phenotype edges |
| 20 | Reactome | Public | Working | 44,979 geneInPathway + 44,979 pathwayContainsGene edges |
| 21 | STRING | Public | Working | 121,170 geneInteractsWithGene edges (confidence > 700) |
| 22 | OpenTargets | Public | Working | 7,564,685 geneAssociatesWithDisease edges via EFO-to-DOID mapping |

## Agent-Generated Parsers (4)

| # | Database | Access Type | Parser Status | Notes |
|---|----------|-------------|---------------|-------|
| 23 | HGNC Gene Families | Public | Working | 1,934 GeneFamily nodes, 5,123 geneInFamily + 5,123 familyContainsGene edges |
| 24 | ClinVar | Public FTP | Working | 4,488,042 Variant nodes, 2,267,095 hasVariant + 2,267,095 variantInGene + 594,101 associatedWithVariant + 594,101 variantAssociatedWithDisease edges |
| 25 | DrugAge | Public | Working | 386 associatedWithAging edges, 3 AgeingProperty nodes |
| 26 | AnAge | Public | Working | 4,645 Species longevity nodes (nodes only) |

## Sources Removed During Deduplication (10)

| Removed Source | Was Providing | Replaced By | Rationale |
|---------------|---------------|-------------|-----------|
| DisGeNET | 20K gene-disease edges | OpenTargets | OpenTargets has 2.4M edges with evidence scores |
| GWAS Catalog | 45K gene-disease edges | OpenTargets | OpenTargets already ingests GWAS Catalog |
| Jensen DISEASES | 20K gene-disease edges | OpenTargets | Covered by OpenTargets text-mining with better scoring |
| OMIM | 7.3K gene-disease edges | OpenTargets | OpenTargets includes genetic evidence; OMIM gene data retained in CVD gene ontology |
| WikiPathways | 8.6K pathway edges | Reactome | Reactome is gold-standard curated; many WikiPathways imported from Reactome |
| AOP-DB | 18.5K pathway edges | Reactome | AOP-DB focuses on toxicology, less relevant for CVD |
| HGNC (base) | Gene node enrichment | NCBI Gene | NCBI Gene is primary gene reference with daily updates |
| CellAge | Senescence gene nodes | NCBI Gene | Node-only source, genes already in NCBI Gene |
| GenAge | Aging gene nodes | NCBI Gene | Node-only source, genes already in NCBI Gene |
| Hetionet (precomputed) | 138K side effects + 5K PPI + 127 covariance | SIDER + STRING | Side effects covered by SIDER, PPI by STRING; covariance dropped (127 edges) |

## Sources Modified During Deduplication (2)

| Source | Change | Reason |
|--------|--------|--------|
| PubTator Central | Removed geneAssociatesWithDisease edges. Kept diseaseAssociatesWithDisease (807K edges, unique). | OpenTargets covers gene-disease; PubTator uniquely provides disease-disease cooccurrence |
| ClinPGx | Removed Variant from node contribution. Kept DrugLabel nodes and all 4 unique edge types. | ClinVar is primary Variant source (4.5M vs 1.1K) |

## Relationship Source Labels (21)

All relationships carry a `source` property identifying the originating database:

`Bgee`, `BindingDB`, `CTD`, `ClinPGx`, `ClinVar`, `ClinicalTrials.gov`, `DoRothEA`, `DrugAge`, `DrugBank`, `DrugCentral`, `Gene Ontology`, `HGNC`, `HPO`, `Jensen TISSUES`, `LINCS L1000`, `MEDLINE`, `OpenTargets`, `PubTator`, `Reactome`, `SIDER`, `STRING`

Node-only sources (5): Disease Ontology, Uberon, NCBI MeSH, NCBI Gene, AnAge. HGNC Families uses `HGNC` as its source label.
