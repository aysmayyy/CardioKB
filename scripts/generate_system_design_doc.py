"""Generate the CardioKB System Design Word document."""

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from pathlib import Path


def add_heading(doc, text, level=1):
    h = doc.add_heading(text, level=level)
    return h


def add_table(doc, headers, rows):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = 'Light Grid Accent 1'
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    # Header row
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = h
        for p in cell.paragraphs:
            for run in p.runs:
                run.bold = True
    # Data rows
    for r_idx, row in enumerate(rows):
        for c_idx, val in enumerate(row):
            table.rows[r_idx + 1].cells[c_idx].text = str(val)
    doc.add_paragraph()
    return table


def build_doc():
    doc = Document()

    # -- Title Page --
    doc.add_paragraph()
    title = doc.add_heading('CardioKB: System Design Document', level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle = doc.add_paragraph('Biomedical Knowledge Graph for Disease Research and Precision Medicine')
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.runs[0].font.size = Pt(14)
    subtitle.runs[0].font.color.rgb = RGBColor(100, 100, 100)

    meta = doc.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta.add_run('Version 1.0  |  March 2026\n').font.size = Pt(11)
    meta.add_run('12-Week Rotation Project (January - April 2026)').font.size = Pt(11)

    doc.add_page_break()

    # -- Table of Contents placeholder --
    add_heading(doc, 'Table of Contents', level=1)
    toc_items = [
        '1. Executive Summary',
        '2. System Overview',
        '3. Architecture',
        '   3.1. High-Level Architecture',
        '   3.2. Component Diagram',
        '   3.3. Data Flow',
        '4. Data Layer',
        '   4.1. Data Sources (36 Parsers)',
        '   4.2. Parser Framework',
        '   4.3. Ontology Configuration System',
        '   4.4. ID Mapping & Cross-Reference Resolution',
        '5. Storage Layer: Neo4j Knowledge Graph',
        '   5.1. Graph Schema',
        '   5.2. Node Types',
        '   5.3. Relationship Types',
        '   5.4. Loading Strategy',
        '   5.5. Indexing & Performance',
        '6. Application Layer',
        '   6.1. Pipeline Orchestrator',
        '   6.2. Flask Web API',
        '   6.3. Web Dashboard',
        '7. AI Agent Layer',
        '   7.1. DatabaseAgent (Autonomous Parser Generation)',
        '   7.2. DiseaseQueryAgent (On-Demand Enrichment)',
        '8. Disease Scoping & Filtering',
        '9. Post-Processing',
        '   9.1. Disease-Specificity Scoring',
        '   9.2. ID Mapping Validation & Gap Repair',
        '10. Deployment & Operations',
        '11. Security Considerations',
        '12. Current Statistics',
        '13. Limitations & Future Work',
    ]
    for item in toc_items:
        p = doc.add_paragraph(item)
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.space_before = Pt(0)

    doc.add_page_break()

    # =====================================================================
    # 1. Executive Summary
    # =====================================================================
    add_heading(doc, '1. Executive Summary', level=1)
    doc.add_paragraph(
        'CardioKB is a general-purpose biomedical knowledge graph that integrates 36 heterogeneous '
        'data sources into a unified Neo4j graph database. While initially scoped to cardiovascular '
        'disease, the system is disease-agnostic by design — most parsers ingest data spanning all '
        'human diseases, genes, drugs, pathways, and phenotypes. The knowledge graph currently '
        'contains 5.47 million nodes and 44.5 million relationships across 21 node types and '
        '42 relationship types.'
    )
    doc.add_paragraph(
        'The system features two AI-powered agents: a DatabaseAgent that autonomously generates '
        'new data source parsers from just a name and URL using the Claude API, and a '
        'DiseaseQueryAgent that enriches the graph for any disease on demand by fetching '
        'gene-disease associations and clinical trials. A web dashboard provides interactive '
        'graph visualization, Cypher querying, and AI-driven disease exploration.'
    )
    doc.add_paragraph(
        'The architecture is adapted from AlzKB (Alzheimer\'s Knowledge Base) but replaces the '
        'original RDF/Memgraph pipeline with direct Cypher-based Neo4j loading, adds 28 additional '
        'data sources, and introduces AI-assisted parser generation and disease enrichment capabilities.'
    )

    # =====================================================================
    # 2. System Overview
    # =====================================================================
    add_heading(doc, '2. System Overview', level=1)

    add_heading(doc, 'Technology Stack', level=2)
    add_table(doc,
              ['Component', 'Technology'],
              [
                  ['Language', 'Python 3.11 (conda environment: cardiokb)'],
                  ['Graph Database', 'Neo4j (Bolt protocol)'],
                  ['Web Framework', 'Flask (port 5050)'],
                  ['AI/LLM', 'Claude API (Anthropic) — Haiku 4.5 for agent tasks'],
                  ['Frontend', 'HTML/CSS/JS with vis.js (graph visualization)'],
                  ['Key Libraries', 'pandas, numpy, requests, neo4j, obonet, lxml, scipy'],
                  ['Testing', 'pytest'],
                  ['Version Control', 'Git (GitHub)'],
              ])

    add_heading(doc, 'Design Principles', level=2)
    principles = [
        ('Declarative schema mapping', 'All data-to-graph mappings are defined in ontology_configs.py, not hardcoded in loader logic. Adding a new edge type is a config change, not a code change.'),
        ('Provenance tracking', 'Every relationship carries a source property identifying the originating database (28 unique source labels), enabling multi-source evidence aggregation and conflict resolution.'),
        ('Idempotent loading', 'All node and relationship creation uses MERGE (not CREATE), making the pipeline safe to re-run without creating duplicates.'),
        ('Graceful degradation', 'Credential-gated parsers (OMIM, DisGeNET, DrugBank, AOP-DB) are automatically skipped when credentials are missing. The pipeline completes with whatever sources are available.'),
        ('Disease-agnostic core', 'Only 3 of 36 parsers accept a disease filter parameter. The remaining 33 ingest complete datasets regardless of disease scope.'),
    ]
    for title, desc in principles:
        p = doc.add_paragraph()
        p.add_run(f'{title}: ').bold = True
        p.add_run(desc)

    # =====================================================================
    # 3. Architecture
    # =====================================================================
    add_heading(doc, '3. Architecture', level=1)

    add_heading(doc, '3.1. High-Level Architecture', level=2)
    doc.add_paragraph(
        'CardioKB follows a four-layer architecture: Data Layer (parsers + raw sources), '
        'Storage Layer (Neo4j graph + TSV archive), Application Layer (pipeline orchestrator + '
        'Flask API + web dashboard), and AI Agent Layer (DatabaseAgent + DiseaseQueryAgent).'
    )

    doc.add_paragraph(
        'The system operates in two primary modes: (1) Batch pipeline mode, where the full '
        'pipeline downloads, parses, and loads all 36 sources end-to-end, and (2) Interactive mode, '
        'where users query and enrich the graph through the web interface.'
    )

    add_heading(doc, '3.2. Component Diagram', level=2)
    components = [
        'src/main.py — Pipeline orchestrator (CardioKBPipeline class)',
        'src/parsers/ — 36 data source parsers (inherit BaseParser)',
        'src/parsers/hetionet_components/ — 14 Hetionet-derived component parsers',
        'src/ontology_configs.py — 85 declarative Neo4j schema mappings',
        'src/neo4j_loader.py — Cypher-based batch loader (UNWIND + MERGE)',
        'src/id_mapping.py — Cross-reference resolution and gap repair',
        'src/api.py — Flask web API with SSE streaming',
        'src/database_agent.py — AI-powered autonomous parser generator',
        'src/disease_agent.py — AI-powered on-demand disease enrichment',
        'src/agent.py — Base agent (Claude API + DisGeNET standardization)',
        'src/orchestrator.py — Pipeline health check with Neo4j-based status detection',
        'src/utils.py — Shared utilities (disease term loading, search patterns)',
        'scripts/compute_specificity.py — Post-load disease-specificity scoring',
        'interface/index.html — Web dashboard (Explore, Query, Build KG, Extract)',
    ]
    for c in components:
        doc.add_paragraph(c, style='List Bullet')

    add_heading(doc, '3.3. Data Flow', level=2)
    doc.add_paragraph('The batch pipeline executes four sequential steps:')
    steps = [
        ('Step 1: Data Retrieval & Parsing', 'Each of the 36 parsers downloads its source data (or reads from cache if --skip-download is set), parses it into pandas DataFrames keyed by entity type (e.g., "genes", "gene_disease_associations"), and returns a Dict[str, DataFrame].'),
        ('Step 2: TSV Export', 'All parsed DataFrames are exported to data/processed/<source>/ as tab-separated files, creating a reproducible snapshot of each pipeline run.'),
        ('Step 3: Neo4j Loading', 'The Neo4jLoader iterates through 85 ontology configs in two passes — Pass 1 loads nodes (MERGE by primary key), Pass 2 loads relationships (MATCH subject + object, MERGE edge). Post-load ID mapping validation checks all relationship match rates and creates missing nodes for low-match configs (gap repair).'),
        ('Step 4: Post-Processing', 'Computes disease-specificity scores (specificityScore property) for all 5.47M nodes in batches of 50K, tags CVD-relevant Disease nodes, and stores computation metadata.'),
    ]
    for title, desc in steps:
        p = doc.add_paragraph()
        p.add_run(f'{title}. ').bold = True
        p.add_run(desc)

    # =====================================================================
    # 4. Data Layer
    # =====================================================================
    add_heading(doc, '4. Data Layer', level=1)

    add_heading(doc, '4.1. Data Sources (36 Parsers)', level=2)
    doc.add_paragraph(
        'CardioKB integrates 36 biomedical data sources organized in three phases:'
    )

    add_heading(doc, 'Phase 1: Core Parsers (8 sources)', level=3)
    add_table(doc,
              ['#', 'Source', 'Access', 'Key Data'],
              [
                  ['1', 'ClinicalTrials.gov', 'Public API v2', '576K trials, 1.16M edges'],
                  ['2', 'ClinPGx (PharmGKB successor)', 'Public API', 'Pharmacogenomics: 2,299 edges'],
                  ['3', 'NCBI Gene', 'Public FTP', '216K gene nodes'],
                  ['4', 'DoRothEA (OmniPath)', 'Public API', '15K TF-gene interactions'],
                  ['5', 'OMIM', 'API key', '7,354 gene-disease edges'],
                  ['6', 'DisGeNET', 'API key', '23,704 gene-disease edges'],
                  ['7', 'DrugBank', 'XML file', '46K drugs, 19K drug-target edges'],
                  ['8', 'AOP-DB', 'SQL dump', '396K pathway edges'],
              ])

    add_heading(doc, 'Phase 2: Hetionet Component Parsers (21 sources)', level=3)
    add_table(doc,
              ['#', 'Source', 'Key Data'],
              [
                  ['9', 'Disease Ontology', '44K disease nodes'],
                  ['10', 'Gene Ontology', '323K annotation edges'],
                  ['11', 'Uberon (anatomy)', '15K anatomy nodes'],
                  ['12', 'MeSH (symptoms)', '966 symptom nodes'],
                  ['13', 'SIDER (side effects)', '149K side effect edges'],
                  ['14', 'LINCS L1000', '357K expression edges'],
                  ['15', 'MEDLINE', '7.2K literature cooccurrence edges'],
                  ['16', 'DrugCentral', '40K drug-disease/pharmacologic edges'],
                  ['17', 'GWAS Catalog', '45K gene-disease associations'],
                  ['18', 'BindingDB', '26K drug-gene binding edges'],
                  ['19', 'PubTator Central', '17M literature-mined edges'],
                  ['20', 'CTD', '432K chemical-gene expression edges'],
                  ['21', 'Bgee', '7.2M tissue expression edges'],
                  ['22', 'Hetionet (precomputed)', '337K gene interaction + side effect edges'],
                  ['23', 'Jensen Lab DISEASES', '21K gene-disease edges'],
                  ['24', 'Jensen Lab TISSUES', '982K gene-tissue edges'],
                  ['25', 'HPO', '304K gene-phenotype edges'],
                  ['26', 'Reactome', '193K pathway edges'],
                  ['27', 'WikiPathways', '93K pathway edges'],
                  ['28', 'STRING', '229K protein interaction edges'],
                  ['29', 'OpenTargets', '2.4M gene-disease edges'],
              ])

    add_heading(doc, 'Phase 3: Agent-Generated Parsers (7 sources)', level=3)
    add_table(doc,
              ['#', 'Source', 'Key Data'],
              [
                  ['30', 'HGNC', '216K gene nodes enriched with HGNC cross-references'],
                  ['31', 'HGNC Gene Families', '1,934 families, 34K geneInFamily edges'],
                  ['32', 'ClinVar', '4.49M variants, 12.6M edges'],
                  ['33', 'DrugAge', '866 gene-aging association edges'],
                  ['34', 'CellAge', 'Senescence gene nodes'],
                  ['35', 'AnAge', '8,032 species longevity nodes'],
                  ['36', 'GenAge', 'Aging-associated gene nodes'],
              ])

    add_heading(doc, 'Credential-Gated Sources', level=3)
    add_table(doc,
              ['Parser', 'Required Credentials', 'Fallback'],
              [
                  ['OMIM', 'OMIM_API_KEY', 'Skipped if missing'],
                  ['DisGeNET', 'DISGENET_API_KEY', 'Skipped if missing'],
                  ['DrugBank', 'DRUGBANK_USERNAME + PASSWORD', 'Auto-detects local XML file'],
                  ['AOP-DB', 'MYSQL_USERNAME + PASSWORD', 'Auto-detects local SQL dump'],
              ])

    add_heading(doc, '4.2. Parser Framework', level=2)
    doc.add_paragraph(
        'All 36 parsers inherit from BaseParser (src/parsers/base_parser.py), which provides:'
    )
    features = [
        'download_data() — Abstract method; each parser implements its own download logic (HTTP, FTP, API pagination, local file detection)',
        'parse_data() -> Dict[str, DataFrame] — Abstract method; returns parsed data keyed by entity type',
        'get_schema() -> Dict — Abstract method; returns column schema for validation',
        'download_file(url, filename) — Shared HTTP download with caching (skips if file exists)',
        'extract_gzip(path) — Shared gzip extraction with caching',
        'read_tsv() / read_csv() — Shared file readers with logging',
        'validate_data(df, required_columns) — Column presence validation',
    ]
    for f in features:
        doc.add_paragraph(f, style='List Bullet')

    doc.add_paragraph(
        'The parser returns a dictionary of DataFrames. The keys must match the '
        'source_filename values in ontology_configs.py so the loader can find the right '
        'config for each DataFrame. For example, the DisGeNET parser returns '
        '{"gene_disease_associations": df, "diseases": df, ...}.'
    )

    add_heading(doc, '4.3. Ontology Configuration System', level=2)
    doc.add_paragraph(
        'The ontology configuration system (src/ontology_configs.py) is the central schema '
        'mapping layer. It contains 85 configuration entries that declaratively define how '
        'parsed DataFrames map to Neo4j nodes and relationships. Each config specifies:'
    )

    add_table(doc,
              ['Field', 'Description', 'Example'],
              [
                  ['type', 'node or relationship', 'relationship'],
                  ['source_filename', 'Key matching parser output dict', 'gene_disease_associations'],
                  ['node_label / rel_type', 'Neo4j label or relationship type', 'geneAssociatesWithDisease'],
                  ['primary_key', 'Property used for MERGE dedup (nodes)', 'geneSymbol'],
                  ['subject_node_type', 'Source node label (relationships)', 'Gene'],
                  ['subject_key', 'Source node match property', 'geneSymbol'],
                  ['object_node_type', 'Target node label (relationships)', 'Disease'],
                  ['object_key', 'Target node match property', 'xrefUmlsCUI'],
                  ['source_label', 'Provenance label set on r.source', 'DisGeNET'],
                  ['column_map', 'DataFrame column -> Neo4j property mapping', '{"geneSymbol": "geneSymbol"}'],
              ])

    doc.add_paragraph(
        'Config keys follow the convention {source_name}.{data_name} (e.g., '
        '"disgenet.gene_disease_associations"). The Neo4jLoader iterates all configs in two '
        'passes: nodes first, then relationships, ensuring all referenced nodes exist before '
        'edges are created.'
    )

    add_heading(doc, '4.4. ID Mapping & Cross-Reference Resolution', level=2)
    doc.add_paragraph(
        'The ID mapping module (src/id_mapping.py) handles the challenge of integrating '
        'data sources that use different identifier systems (NCBI Gene IDs, Ensembl IDs, '
        'gene symbols, DOID, UMLS CUI, MeSH, DrugBank IDs, etc.).'
    )
    doc.add_paragraph('Key capabilities:')
    capabilities = [
        'ID_SYSTEMS registry — Maps 17 identifier systems to their (node_label, property_name) pairs in Neo4j',
        'IDMapper class — Builds in-memory cross-reference lookups from Neo4j node properties',
        'validate_mapping() — Checks what percentage of source IDs match existing graph nodes',
        'suggest_mapping() — When match rate is low, suggests alternative ID properties that might work better',
        'create_missing_nodes() — Creates new nodes for unmatched IDs (only if they have >= 10 edges, to avoid noise)',
        'Post-processing remaps — PubTator MeSH-to-DOID and GWAS trait-to-DOID remapping during pipeline parsing',
    ]
    for c in capabilities:
        doc.add_paragraph(c, style='List Bullet')

    # =====================================================================
    # 5. Storage Layer
    # =====================================================================
    add_heading(doc, '5. Storage Layer: Neo4j Knowledge Graph', level=1)

    add_heading(doc, '5.1. Graph Schema', level=2)
    doc.add_paragraph(
        'The Neo4j graph uses a labeled property graph model. Nodes have one or more labels '
        '(e.g., :Gene, :Disease) and properties (e.g., geneSymbol, commonName). Relationships '
        'are typed (e.g., geneAssociatesWithDisease) and carry properties including the mandatory '
        'source field for provenance.'
    )

    add_heading(doc, '5.2. Node Types (21)', level=2)
    add_table(doc,
              ['Node Type', 'Count', 'Primary Key', 'Description'],
              [
                  ['Variant', '4,488,042', 'variantId', 'Genetic variants (ClinVar)'],
                  ['ClinicalTrial', '576,334', 'trialId', 'Clinical trials (ClinicalTrials.gov)'],
                  ['Gene', '216,315', 'geneSymbol', 'Human genes (NCBI Gene, HGNC)'],
                  ['Drug', '46,142', 'commonName / xrefDrugbank', 'Drugs and chemicals'],
                  ['Disease', '43,972', 'commonName / xrefDiseaseOntology', 'Diseases (Disease Ontology, OMIM, DisGeNET)'],
                  ['BiologicalProcess', '24,547', 'geneOntologyId', 'GO biological processes'],
                  ['Phenotype', '19,389', 'xrefHPO', 'Human phenotypes (HPO)'],
                  ['BodyPart', '14,937', 'xrefUberon', 'Anatomical structures (Uberon)'],
                  ['MolecularFunction', '10,123', 'geneOntologyId', 'GO molecular functions'],
                  ['Species', '8,032', 'speciesName', 'Species (AnAge longevity data)'],
                  ['Pathway', '6,469', 'pathwayName', 'Biological pathways (Reactome, WikiPathways, AOP-DB)'],
                  ['SideEffect', '5,734', 'xrefUmlsCUI', 'Drug side effects (SIDER)'],
                  ['CellularComponent', '4,069', 'geneOntologyId', 'GO cellular components'],
                  ['GeneFamily', '1,934', 'familyId', 'Gene families (HGNC)'],
                  ['PharmacologicClass', '1,646', 'classId', 'Drug classes (DrugCentral)'],
                  ['Symptom', '966', 'xrefMeSH', 'Disease symptoms (MeSH)'],
                  ['DrugLabel', '378', 'labelId', 'FDA drug labels (ClinPGx)'],
                  ['TranscriptionFactor', '367', 'TF', 'Transcription factors (DoRothEA)'],
                  ['AgeingProperty', '3', 'propertyName', 'Aging properties (DrugAge)'],
                  ['DiseaseCache', '7', 'diseaseKey', 'Agent build cache entries'],
                  ['_Metadata', '1', 'key', 'System metadata (specificity timestamp)'],
              ])

    add_heading(doc, '5.3. Relationship Types (42)', level=2)
    doc.add_paragraph(
        'All relationships carry a source property identifying the originating database. '
        'The same relationship type can come from multiple sources (e.g., geneAssociatesWithDisease '
        'has edges from PubTator, OpenTargets, GWAS, DisGeNET, OMIM, and Jensen DISEASES). '
        'There are 28 unique source labels across 42 relationship types totaling 44.5M edges.'
    )

    add_table(doc,
              ['Relationship Type', 'Source(s)', 'Total Edges'],
              [
                  ['geneAssociatesWithDisease', 'PubTator, OpenTargets, GWAS, DisGeNET, Jensen, OMIM', '17,393,760'],
                  ['bodyPartUnderexpressesGene', 'Bgee', '7,211,055'],
                  ['hasVariant / variantInGene', 'ClinVar', '4,439,480 each'],
                  ['associatedWithVariant / variantAssociatedWithDisease', 'ClinVar', '1,862,448 each'],
                  ['geneExpressedInBodyPart', 'Jensen TISSUES', '982,116'],
                  ['STUDIES_CONDITION', 'ClinicalTrials.gov', '818,839'],
                  ['geneInteractsWithGene', 'STRING, Hetionet', '365,768'],
                  ['TESTS_INTERVENTION', 'ClinicalTrials.gov', '345,632'],
                  ['geneInPathway / pathwayContainsGene', 'AOP-DB, Reactome, WikiPathways', '340,744 each'],
                  ['geneAssociatesWithPhenotype', 'HPO', '303,817'],
                  ['geneRegulatesGene', 'LINCS L1000', '279,578'],
                  ['chemicalIncreasesExpression', 'CTD', '218,152'],
                  ['chemicalDecreasesExpression', 'CTD', '213,587'],
                  ['diseaseAssociatesWithDisease', 'PubTator', '2,138,895'],
                  ['compoundCausesSideEffect', 'SIDER', '148,518'],
                  ['drugCausesSideEffect', 'Hetionet', '138,540'],
                  ['geneParticipatesInBiologicalProcess', 'Gene Ontology', '135,351'],
                  ['geneHasMolecularFunction', 'Gene Ontology', '93,564'],
                  ['geneAssociatedWithCellularComponent', 'Gene Ontology', '93,792'],
                  ['geneCovariesWithGene', 'Hetionet', '61,797'],
                  ['compoundUpregulatesGene', 'LINCS L1000', '36,688'],
                  ['compoundDownregulatesGene', 'LINCS L1000', '40,895'],
                  ['geneInFamily / familyContainsGene', 'HGNC', '34,006 each'],
                  ['chemicalBindsGene', 'BindingDB', '26,467'],
                  ['drugBindsGene', 'DrugBank', '19,085'],
                  ['pharmacologicClassIncludesCompound', 'DrugCentral', '16,403'],
                  ['transcriptionFactorInteractsWithGene', 'DoRothEA', '15,092'],
                  ['drugTreatsDisease', 'DrugCentral', '6,242'],
                  ['drugPalliatesDisease', 'DrugCentral', '1,012'],
                  ['diseaseLocalizesToAnatomy', 'MEDLINE', '3,602'],
                  ['diseasePresentsSymptom', 'MEDLINE', '3,068'],
                  ['associatedWithAging', 'DrugAge', '866'],
                  ['diseaseResemblesDisease', 'MEDLINE', '543'],
              ])

    add_heading(doc, '5.4. Loading Strategy', level=2)
    doc.add_paragraph(
        'The Neo4jLoader (src/neo4j_loader.py) uses UNWIND-based Cypher batching with a '
        'batch size of 1,000 rows. All operations use MERGE to ensure idempotency.'
    )
    doc.add_paragraph('Node loading pattern:')
    doc.add_paragraph(
        'UNWIND $batch AS row\n'
        'MERGE (n:Gene {geneSymbol: row.geneSymbol})\n'
        'SET n.xrefNcbiGene = row.xrefNcbiGene, n.xrefEnsembl = row.xrefEnsembl',
        style='No Spacing'
    )
    doc.add_paragraph('Relationship loading pattern:')
    doc.add_paragraph(
        'UNWIND $batch AS row\n'
        'MATCH (s:Gene {geneSymbol: row.geneSymbol})\n'
        'MATCH (o:Disease {xrefDiseaseOntology: row.diseaseId})\n'
        'MERGE (s)-[r:geneAssociatesWithDisease]->(o)\n'
        'SET r.source = "DisGeNET", r.score = row.score',
        style='No Spacing'
    )
    doc.add_paragraph(
        'The loader processes configs in two passes: Pass 1 loads all node configs, Pass 2 loads '
        'all relationship configs. This ensures referenced nodes exist before edges reference them. '
        'Each relationship automatically gets its r.source property set from the config\'s source_label field.'
    )

    add_heading(doc, '5.5. Indexing & Performance', level=2)
    doc.add_paragraph(
        'Neo4j indexes are critical for MERGE and MATCH performance. The loader creates '
        'indexes on primary key properties for each node label (e.g., Gene.geneSymbol, '
        'Disease.xrefDiseaseOntology). An additional index exists on Gene.specificityScore '
        'for ranked queries. The transaction memory limit is configured at 716.8 MiB, which '
        'required batched processing for the specificity score computation across large labels '
        '(ClinicalTrial: 576K nodes, Variant: 4.49M nodes).'
    )

    # =====================================================================
    # 6. Application Layer
    # =====================================================================
    add_heading(doc, '6. Application Layer', level=1)

    add_heading(doc, '6.1. Pipeline Orchestrator', level=2)
    doc.add_paragraph(
        'The CardioKBPipeline class (src/main.py) orchestrates the end-to-end build process. '
        'It supports two flags: --skip-download (reuse cached data files) and --skip-neo4j '
        '(parse and export TSV only, no graph loading). The pipeline:'
    )
    pipeline_steps = [
        'Instantiates all 36 parsers with the raw data directory',
        'Calls download_data() on each parser (unless --skip-download)',
        'Calls parse_data() to get Dict[str, DataFrame] from each',
        'Exports all DataFrames to data/processed/<source>/*.tsv',
        'Initializes Neo4jLoader with credentials from .env',
        'Loads nodes (Pass 1) then relationships (Pass 2) via ontology configs',
        'Runs post-load ID mapping validation with gap repair',
        'Computes disease-specificity scores for all nodes',
        'Tags CVD-relevant Disease nodes (90 whole-word patterns)',
    ]
    for s in pipeline_steps:
        doc.add_paragraph(s, style='List Number')

    add_heading(doc, '6.2. Flask Web API', level=2)
    doc.add_paragraph(
        'The Flask backend (src/api.py, port 5050) provides REST endpoints and SSE streaming:'
    )
    add_table(doc,
              ['Endpoint', 'Method', 'Description'],
              [
                  ['/api/graph-stats', 'GET', 'Node/relationship counts, source labels, totals'],
                  ['/api/diseases', 'GET', 'Available disease filters'],
                  ['/api/search', 'GET', 'Search nodes by name/type'],
                  ['/api/query', 'POST', 'Execute Cypher query, return results'],
                  ['/api/subgraph', 'GET', 'Extract N-hop disease subgraph'],
                  ['/api/specificity-info', 'GET', 'Specificity score metadata'],
                  ['/api/agent/build-disease-graph', 'POST', 'Trigger DiseaseQueryAgent (SSE)'],
                  ['/api/agent/add-database', 'POST', 'Trigger DatabaseAgent'],
                  ['/api/health-check', 'GET', 'Pipeline health check (SSE streaming)'],
              ])

    add_heading(doc, '6.3. Web Dashboard', level=2)
    doc.add_paragraph(
        'The single-page web interface (interface/index.html) provides four main features:'
    )
    tabs = [
        ('Explore tab', 'Interactive vis.js graph visualization of disease subgraphs. Nodes are ranked by disease-specificity score. Supports Core layer (direct associations) and Discovery layer (2-hop hypothesis generation). Click nodes for detail panels with properties, neighbors, and specificity scores.'),
        ('Query tab', 'Neo4j Browser-style multi-panel Cypher interface. Each query creates a new result panel (newest at top) with table and graph visualization tabs. Includes query templates and Ctrl+Enter shortcut.'),
        ('Build Knowledge Graph (sidebar)', 'AI-powered disease enrichment. Enter any disease name (abbreviations, synonyms accepted). The DiseaseQueryAgent standardizes via Claude, fetches DisGeNET + ClinicalTrials.gov data, loads into Neo4j, and auto-opens Explore.'),
        ('Extract Disease Subgraph (sidebar)', 'Configurable N-hop subgraph extraction (1-3 hops) with stats and JSON/CSV export for downstream analysis.'),
    ]
    for title, desc in tabs:
        p = doc.add_paragraph()
        p.add_run(f'{title}: ').bold = True
        p.add_run(desc)

    # =====================================================================
    # 7. AI Agent Layer
    # =====================================================================
    add_heading(doc, '7. AI Agent Layer', level=1)

    add_heading(doc, '7.1. DatabaseAgent (Autonomous Parser Generation)', level=2)
    doc.add_paragraph(
        'The DatabaseAgent (src/database_agent.py) uses the Claude API to autonomously generate '
        'complete parsers for new biomedical data sources. The user provides only a database name '
        'and a download URL.'
    )
    doc.add_paragraph('Workflow:')
    agent_steps = [
        'Sample download — Downloads the first 64KB to detect format (TSV, CSV, JSON, XML) and discover actual column names',
        'Code generation — Sends file sample, BaseParser source, SKILL.md guide, and example parser to Claude, which generates a complete parser class + ontology configs',
        'Pipeline integration — Saves parser to src/parsers/, adds ontology configs, registers in main.py and __init__.py',
        'Execute & validate — Runs the parser, validates ID mappings against Neo4j, loads data, verifies edge counts',
    ]
    for s in agent_steps:
        doc.add_paragraph(s, style='List Number')

    doc.add_paragraph(
        'The agent uses Claude Haiku 4.5 (configurable via DATABASE_AGENT_MODEL env var) for '
        'cost-effective code generation. Seven parsers in production were generated entirely by '
        'this agent: HGNC, HGNC Families, ClinVar, DrugAge, CellAge, AnAge, and GenAge.'
    )

    doc.add_paragraph('Key bugs discovered and fixed during development:')
    bugs = [
        'Column name hallucination — Claude invented column names not in the source. Fixed by injecting actual column names from the sample download.',
        'Duplicate configs on re-run — Fixed by detecting and removing existing entries before appending.',
        'Gzip partial download failure — Fixed with streaming GzipFile that tolerates truncated data.',
        'Comment-line header detection — Files using #-prefixed headers (e.g., ClinVar) were initially skipped. Fixed by treating delimiter-containing # lines as headers.',
    ]
    for b in bugs:
        doc.add_paragraph(b, style='List Bullet')

    add_heading(doc, '7.2. DiseaseQueryAgent (On-Demand Enrichment)', level=2)
    doc.add_paragraph(
        'The DiseaseQueryAgent (src/disease_agent.py) enriches the knowledge graph for any '
        'disease on demand through the web interface.'
    )
    doc.add_paragraph('Workflow:')
    disease_steps = [
        'Cache check — Returns instantly if disease was previously built (DiseaseCache node in Neo4j)',
        'Standardize — Uses Claude to resolve abbreviations and synonyms to canonical form (e.g., "PD" -> "Parkinson\'s Disease")',
        'Coverage query — Queries Neo4j for existing genes, drugs, trials, and pathways connected to the disease',
        'DisGeNET fetch — Fetches gene-disease associations via API (max 200 disease IDs, 2-minute timeout)',
        'ClinicalTrials.gov fetch — Queries API v2 for relevant trials (max 500 across 5 pages, 1.2s rate limiting)',
        'Neo4j load — Loads trial nodes + STUDIES_CONDITION relationships using MERGE',
        'Cache + stats — Creates DiseaseCache node and returns subgraph statistics',
    ]
    for s in disease_steps:
        doc.add_paragraph(s, style='List Number')

    # =====================================================================
    # 8. Disease Scoping
    # =====================================================================
    add_heading(doc, '8. Disease Scoping & Filtering', level=1)
    doc.add_paragraph(
        'Disease term files live in ontology/diseases/ (one term per line, # for comments). '
        'The active filter is ontology/disease_filter.txt, a symlink to diseases/cvd.txt.'
    )
    add_table(doc,
              ['File', 'Terms', 'Disease Area'],
              [
                  ['cvd.txt', '90', 'Cardiovascular disease (default)'],
                  ['alzheimers.txt', '35', "Alzheimer's & related dementias"],
                  ['cancer.txt', '70', 'Cancer / oncology'],
                  ['asthma.txt', '48', 'Asthma & respiratory diseases'],
                  ['diabetes.txt', '52', 'Diabetes & metabolic diseases'],
              ])
    doc.add_paragraph(
        'Only 3 of 36 parsers use the disease filter: ClinicalTrialsParser (API queries per term), '
        'DisGeNETParser (API search per term), and MEDLINECooccurrenceParser (DOID filtering). '
        'The remaining 33 parsers are fully disease-agnostic and load complete datasets.'
    )

    # =====================================================================
    # 9. Post-Processing
    # =====================================================================
    add_heading(doc, '9. Post-Processing', level=1)

    add_heading(doc, '9.1. Disease-Specificity Scoring', level=2)
    doc.add_paragraph(
        'After loading, the pipeline computes a specificityScore property on every node in the graph. '
        'The formula is: specificityScore = 1.0 / (number of distinct Disease neighbors). '
        'A gene connecting to 5 diseases scores 0.2; one connecting to 20,000 scores 0.00005. '
        'Disease nodes themselves get 0.0 (they ARE diseases). Nodes with no Disease connections get 1.0.'
    )
    doc.add_paragraph(
        'The computation runs in batches of 50,000 nodes per label to stay within Neo4j\'s '
        'transaction memory limit (716.8 MiB). Results are stored as a node property for '
        'O(1) lookup during queries. The computation timestamp is stored in a _Metadata node.'
    )

    add_heading(doc, '9.2. ID Mapping Validation & Gap Repair', level=2)
    doc.add_paragraph(
        'After Neo4j loading, the pipeline validates all relationship configs by checking what '
        'percentage of source and target IDs in each TSV file match existing graph nodes. '
        'Configs with < 50% match rate trigger the suggest_mapping() function, which may '
        'recommend alternative ID properties. The create_missing_nodes() function creates new '
        'Disease (or other) nodes for unmatched IDs that have >= 10 edges, then re-loads '
        'the affected relationship configs to recover orphaned edges.'
    )
    doc.add_paragraph(
        'Example: DisGeNET gene-disease edges initially matched only 40.6% of disease IDs. '
        'Gap repair created 286 new Disease nodes, recovering 11,907 edges.'
    )

    # =====================================================================
    # 10. Deployment
    # =====================================================================
    add_heading(doc, '10. Deployment & Operations', level=1)

    add_heading(doc, 'Local Development', level=2)
    doc.add_paragraph(
        'The system runs locally with conda for Python environment management and a local '
        'Neo4j instance. The Flask server runs on port 5050. Environment variables are stored '
        'in .env (not committed to version control).'
    )

    add_heading(doc, 'Pipeline Execution', level=2)
    add_table(doc,
              ['Command', 'Description'],
              [
                  ['python src/main.py', 'Full pipeline: download + parse + TSV + Neo4j + specificity'],
                  ['python src/main.py --skip-download', 'Reparse from cached data'],
                  ['python src/main.py --skip-neo4j', 'Parse + TSV export only'],
                  ['python src/main.py --skip-download --skip-neo4j', 'Reparse cached data, TSV only'],
                  ['bash run.sh', 'Launch Flask + open browser'],
                  ['python src/api.py --port 5050', 'Start Flask server only'],
              ])

    add_heading(doc, 'Monitoring', level=2)
    doc.add_paragraph(
        'The orchestrator (src/orchestrator.py) provides a health check that dynamically detects '
        'parser status from Neo4j by querying r.source values. The web dashboard Admin panel '
        'shows parser status, pipeline health (SSE streaming), and ID mapping validation reports. '
        'Pipeline logs are written to logs/cardiokb_build.log.'
    )

    # =====================================================================
    # 11. Security
    # =====================================================================
    add_heading(doc, '11. Security Considerations', level=1)
    security = [
        'Credentials (.env) are gitignored and never logged, displayed, or included in output',
        'Neo4j authentication via Bolt protocol with username/password',
        'API keys (OMIM, DisGeNET, Anthropic) stored as environment variables',
        'No user authentication on the web dashboard (local development only)',
        'Cypher injection is mitigated by parameterized queries in the Neo4j driver',
        'The Flask server serves static files from the interface/ directory only',
    ]
    for s in security:
        doc.add_paragraph(s, style='List Bullet')

    # =====================================================================
    # 12. Current Statistics
    # =====================================================================
    add_heading(doc, '12. Current Statistics', level=1)
    add_table(doc,
              ['Metric', 'Value'],
              [
                  ['Total nodes', '5,469,407'],
                  ['Total relationships', '44,489,262'],
                  ['Node types', '21'],
                  ['Relationship types', '42'],
                  ['Data sources', '36 (36 parsers)'],
                  ['Relationship source labels', '28'],
                  ['Ontology configs', '85'],
                  ['Node-only sources', '8 (Disease Ontology, Uberon, MeSH, NCBI Gene, CellAge, AnAge, GenAge, HGNC base)'],
                  ['Disease filter terms (CVD)', '90'],
                  ['CVD-tagged Disease nodes', '1,374'],
                  ['Agent-generated parsers', '7'],
              ])

    # =====================================================================
    # 13. Limitations & Future Work
    # =====================================================================
    add_heading(doc, '13. Limitations & Future Work', level=1)

    add_heading(doc, 'Current Limitations', level=2)
    limitations = [
        'Neo4j transaction memory (716.8 MiB) constrains query complexity on high-degree nodes; batched processing required for large operations',
        'DiseaseQueryAgent is limited to DisGeNET + ClinicalTrials.gov; other sources require full pipeline re-run',
        'Broad disease categories (e.g., "cancer") are capped at 200 disease IDs in the DiseaseQueryAgent to keep response times under 2 minutes',
        'MeSH parser produces nodes only (no relationship data)',
        'No automated scheduling — pipeline runs are manual',
        'Web dashboard has no user authentication (local use only)',
        'CTD chemical-to-drug matching is partial (~41% match rate due to MeSH ID coverage)',
    ]
    for l in limitations:
        doc.add_paragraph(l, style='List Bullet')

    add_heading(doc, 'Future Work', level=2)
    future = [
        'Machine learning models for link prediction and drug repurposing using the knowledge graph',
        'Automated pipeline scheduling with change detection',
        'Graph embedding generation (node2vec, TransE) for downstream ML tasks',
        'Additional data sources (UniProt, IntAct, ChEMBL, FDA adverse events)',
        'Multi-user web deployment with authentication',
        'Graph versioning and diff tracking between pipeline runs',
    ]
    for f in future:
        doc.add_paragraph(f, style='List Bullet')

    # Save
    output_path = Path('/Users/nawaza/Desktop/Cardio-KB/docs/CardioKB_System_Design.docx')
    doc.save(str(output_path))
    print(f"Saved: {output_path}")
    return output_path


if __name__ == '__main__':
    build_doc()
