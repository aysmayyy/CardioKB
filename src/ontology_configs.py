"""
CardioKB Ontology Population Configurations

Adapted from AlzKB ontology_configs.py. Defines configuration for populating
the CardioKB Neo4j graph from various data sources.

Config keys use format: {source_name}.{data_name}
Each config includes source_filename to be self-contained.

Data types:
- 'node': Loaded as nodes (MERGE/CREATE)
- 'relationship': Loaded as relationships (MATCH subject, MATCH object, MERGE rel)
"""

# ===========================================================================
# Filename stem constants
# ===========================================================================

# AOPDB
AOPDB_AOPS = 'aops'
AOPDB_PATHWAYS = 'pathways'
AOPDB_GENE_PATHWAY_RELATIONSHIPS = 'gene_pathway_relationships'
AOPDB_DRUGS = 'drugs'
# DisGeNET
DISGENET_DISEASE_CLASSIFICATIONS = 'disease_classifications'
DISGENET_DISEASE_MAPPINGS = 'disease_mappings'
DISGENET_DISEASES = 'diseases'
DISGENET_GENE_DISEASE_ASSOCIATIONS = 'gene_disease_associations'
# DrugBank
DRUGBANK_DRUGS = 'drugs'
DRUGBANK_DRUG_BINDS_GENE = 'drug_gene_edges'
# NCBI Gene
NCBI_GENES = 'genes'
# DoRothEA
DOROTHEA_TRANSCRIPTION_FACTORS = 'transcription_factors'
DOROTHEA_TF_GENE_INTERACTIONS = 'tf_gene_interactions'
# ClinicalTrials.gov
CT_CLINICAL_TRIALS = 'trial_nodes'
CT_TRIAL_STUDIES_CONDITION = 'trial_disease_associations'
CT_TRIAL_TESTS_INTERVENTION = 'trial_intervention_associations'
# ClinPGx
CLINPGX_CLINICAL_ANNOTATIONS = 'gene_drug_interactions'
CLINPGX_DRUG_LABELS = 'drug_label_nodes'
CLINPGX_VARIANTS = 'variants'
CLINPGX_VARIANT_IN_GENE = 'variant_in_gene'
CLINPGX_CLINICAL_ANNOTATIONS_PHARMA_CLASS = 'clinical_annotations_pharma_class'
CLINPGX_DRUG_LABEL_ANNOTATES_GENE = 'drug_label_annotates_gene'
CLINPGX_DRUG_LABEL_DESCRIBES_DRUG = 'drug_label_describes_drug'

# OMIM
OMIM_GENE_PHENOTYPE_MAP = 'gene_phenotype_map'
OMIM_GENE_DISEASE = 'gene_disease'

# Hetionet Components — Disease Ontology
DO_DISEASE_NODES = 'slim_terms'
DO_DISEASE_ANATOMY = 'disease_anatomy'
DO_DISEASE_XREFS = 'disease_xrefs'
DO_DISEASE_HIERARCHY = 'disease_hierarchy'
# Hetionet Components — Gene Ontology
GO_BP_NODES = 'biological_process_nodes'
GO_MF_NODES = 'molecular_function_nodes'
GO_CC_NODES = 'cellular_component_nodes'
GO_GENE_BP = 'gene_bp_associations'
GO_GENE_MF = 'gene_mf_associations'
GO_GENE_CC = 'gene_cc_associations'
# Hetionet Components — Uberon
UBERON_ANATOMY_NODES = 'uberon_nodes'
# Hetionet Components — MeSH
MESH_SYMPTOM_NODES = 'symptom_nodes'
# Hetionet Components — SIDER
SIDER_SIDE_EFFECT_NODES = 'side_effect_nodes'
SIDER_COMPOUND_CAUSES_SE = 'drug_side_effect_associations'
SIDER_DRUG_NODES = 'sider_drug_nodes'
# Hetionet Components — LINCS
LINCS_CUG = 'compound_gene_up'
LINCS_CDG = 'compound_gene_down'
LINCS_GRG = 'gene_regulates_gene'
# Hetionet Components — MEDLINE
MEDLINE_DPS = 'disease_symptom_cooccurrence'
MEDLINE_DLA = 'disease_anatomy_cooccurrence'
MEDLINE_DRD = 'disease_disease_cooccurrence'
# Hetionet Components — DrugCentral
DC_PHARMACOLOGIC_CLASSES = 'pharmacologic_classes'
DC_PCIC = 'drug_in_class'
DC_DRUG_TREATS = 'drug_treats_disease'
DC_DRUG_PALLIATES = 'drug_palliates_disease'
# Hetionet Components — GWAS
GWAS_GENE_DISEASE = 'gene_disease_gwas'
# Hetionet Components — PubTator
PUBTATOR_DD_COOCCURRENCE = 'disease_disease_cooccurrence'
PUBTATOR_GD_LITERATURE = 'pubtator_gene_disease'
# Hetionet Components — BindingDB
BINDINGDB_DRUG_BINDS_GENE = 'drug_binds_gene'
# Hetionet Components — CTD
CTD_CHEMICAL_NODES = 'chemical_nodes'
CTD_CHEM_INCREASES_EXPR = 'chemical_increases_expression'
CTD_CHEM_DECREASES_EXPR = 'chemical_decreases_expression'
# Hetionet Components — Bgee
BGEE_OVEREXPRESSES = 'anatomy_expresses_gene'
BGEE_UNDEREXPRESSES = 'anatomy_expresses_gene'
# Hetionet Components — Hetionet Precomputed
HETIO_GENE_INTERACTS = 'gene_interacts'
HETIO_GENE_COVARIES = 'gene_covaries'
HETIO_GENE_REGULATES = 'gene_regulates'
HETIO_DRUG_CAUSES_EFFECT = 'drug_causes_effect'

# Jensen Lab DISEASES
JENSENLAB_GENE_DISEASE = 'gene_disease_associations'

# Jensen Lab TISSUES
JENSEN_TISSUES_TISSUE_NODES = 'tissue_nodes'
JENSEN_TISSUES_GENE_TISSUE = 'tissue_gene_associations'

# HPO (Human Phenotype Ontology)
HPO_PHENOTYPE_NODES = 'phenotype_nodes'
HPO_GENE_PHENOTYPE = 'gene_phenotype_associations'

# Reactome
REACTOME_PATHWAY_NODES = 'pathways'
REACTOME_GENE_PATHWAY = 'ncbi_gene_pathway_relationships'

# WikiPathways
WIKIPATHWAYS_PATHWAY_NODES = 'pathway_nodes'
WIKIPATHWAYS_GENE_PATHWAY = 'gene_pathway'

# STRING
STRING_GENE_INTERACTS = 'gene_interactions'

# OpenTargets
OPENTARGETS_GENE_DISEASE = 'target_disease_associations'

# AOPDB table mapping for MySQL queries
AOPDB_TABLE_MAPPING = {
    AOPDB_AOPS: 'aop_info',
    AOPDB_PATHWAYS: 'pathway_gene',
    AOPDB_GENE_PATHWAY_RELATIONSHIPS: 'pathway_gene',
    AOPDB_DRUGS: 'chemical_info',
}


ONTOLOGY_CONFIGS = {
    # =========================================================================
    # AOP-DB - REMOVED (redundant with Reactome pathways)
    # =========================================================================
    f'aopdb.{AOPDB_DRUGS}': {
        'data_type': 'node',
        'node_type': 'Drug',
        'source_filename': f'{AOPDB_DRUGS}.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'DTX_id',
            'data_property_map': {
                'ChemicalID': 'xrefMeSH',
                'source_database': 'sourceDatabase',
            },
            'merge_column': {
                'source_column_name': 'DTX_id',
                'data_property': 'xrefDTXSID',
            },
        },
        'merge': True,
        'skip': True,
    },
    f'aopdb.{AOPDB_PATHWAYS}': {
        'data_type': 'node',
        'node_type': 'Pathway',
        'source_filename': f'{AOPDB_PATHWAYS}.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'path_name',
            'data_property_map': {
                'path_id': 'pathwayId',
                'path_name': 'pathwayName',
                'ext_source': 'sourceDatabase',
                'source_database': 'sourceDatabase',
            },
        },
        'merge': False,
        'skip': True,
    },
    f'aopdb.{AOPDB_GENE_PATHWAY_RELATIONSHIPS}': {
        'data_type': 'relationship',
        'relationship_type': 'geneInPathway',
        'inverse_relationship_type': 'pathwayContainsGene',
        'source_label': 'AOP-DB',
        'source_filename': f'{AOPDB_GENE_PATHWAY_RELATIONSHIPS}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Gene',
            'subject_column_name': 'entrez',
            'subject_match_property': 'xrefNcbiGene',
            'object_node_type': 'Pathway',
            'object_column_name': 'path_name',
            'object_match_property': 'pathwayName',
        },
        'merge': False,
        'skip': True,
    },

    # =========================================================================
    # DisGeNET - REMOVED (redundant with OpenTargets + PubTator)
    # =========================================================================
    f'disgenet.{DISGENET_DISEASE_CLASSIFICATIONS}': {
        'data_type': 'node',
        'node_type': 'Disease',
        'source_filename': f'{DISGENET_DISEASE_CLASSIFICATIONS}.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'diseaseId',
            'data_property_map': {
                'diseaseId': 'xrefUmlsCUI',
                'diseaseName': 'commonName',
                'sourceDatabase': 'sourceDatabase',
            },
        },
        'merge': False,
        'skip': True,
    },
    f'disgenet.{DISGENET_DISEASE_MAPPINGS}': {
        'data_type': 'node',
        'node_type': 'Disease',
        'source_filename': f'{DISGENET_DISEASE_MAPPINGS}.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'diseaseId',
            'filter_column': 'DO',
            'filter_value': '0',
            'merge_column': {
                'source_column_name': 'diseaseId',
                'data_property': 'xrefUmlsCUI',
                'sourceDatabase': 'sourceDatabase',
            },
            'data_property_map': {
                'DO': 'xrefDiseaseOntology',
            },
        },
        'merge': True,
        'skip': True,
    },
    f'disgenet.{DISGENET_GENE_DISEASE_ASSOCIATIONS}': {
        'data_type': 'relationship',
        'relationship_type': 'geneAssociatesWithDisease',
        'source_label': 'DisGeNET',
        'source_filename': f'{DISGENET_GENE_DISEASE_ASSOCIATIONS}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Gene',
            'subject_column_name': 'geneSymbol',
            'subject_match_property': 'geneSymbol',
            'object_node_type': 'Disease',
            'object_column_name': 'diseaseId',
            'object_match_property': 'xrefUmlsCUI',
            'filter_column': 'diseaseType',
            'filter_value': 'disease',
        },
        'merge': False,
        'skip': True,
    },

    # =========================================================================
    # DrugBank - Drug Information
    # =========================================================================
    f'drugbank.{DRUGBANK_DRUGS}': {
        'data_type': 'node',
        'node_type': 'Drug',
        'source_filename': f'{DRUGBANK_DRUGS}.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'drugbank_id',
            'data_property_map': {
                'drugbank_id': 'xrefDrugbank',
                'cas_number': 'xrefCasRN',
                'drug_name': 'commonName',
                'pubchem_cid': 'xrefPubChemCID',
                'chembl_id': 'xrefChembl',
                'source_database': 'sourceDatabase',
            },
            'merge_column': {
                'source_column_name': 'cas_number',
                'data_property': 'xrefCasRN',
            },
        },
        'merge': True,
        'skip': False,
    },

    # ---- DrugBank Drug-Target Binding Edges ----
    f'drugbank.{DRUGBANK_DRUG_BINDS_GENE}': {
        'data_type': 'relationship',
        'relationship_type': 'drugBindsGene',
        'source_label': 'DrugBank',
        'source_filename': f'{DRUGBANK_DRUG_BINDS_GENE}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Drug',
            'subject_column_name': 'drugbank_id',
            'subject_match_property': 'xrefDrugbank',
            'object_node_type': 'Gene',
            'object_column_name': 'gene_symbol',
            'object_match_property': 'geneSymbol',
            'data_property_map': {
                'interaction_type': 'interactionType',
            },
        },
        'merge': False,
        'skip': False,
    },

    # =========================================================================
    # OMIM - REMOVED (redundant with OpenTargets + HPO)
    # =========================================================================
    f'omim.{OMIM_GENE_DISEASE}_nodes': {
        'data_type': 'node',
        'node_type': 'Disease',
        'source_filename': f'{OMIM_GENE_DISEASE}_nodes.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'phenotype_mim',
            'data_property_map': {
                'phenotype_mim': 'xrefOMIM',
                'phenotype': 'commonName',
                'source_database': 'sourceDatabase',
            },
        },
        'merge': True,
        'skip': True,
    },
    f'omim.{OMIM_GENE_DISEASE}': {
        'data_type': 'relationship',
        'relationship_type': 'geneAssociatesWithDisease',
        'source_label': 'OMIM',
        'source_filename': f'{OMIM_GENE_DISEASE}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Gene',
            'subject_column_name': 'primary_gene_symbol',
            'subject_match_property': 'geneSymbol',
            'object_node_type': 'Disease',
            'object_column_name': 'phenotype_mim',
            'object_match_property': 'xrefOMIM',
            'data_property_map': {
                'mapping_key': 'mappingKey',
                'inheritance': 'inheritance',
            },
        },
        'merge': False,
        'skip': True,
    },

    # =========================================================================
    # NCBI Gene - Gene Information
    # =========================================================================
    f'ncbigene.{NCBI_GENES}': {
        'data_type': 'node',
        'node_type': 'Gene',
        'source_filename': f'{NCBI_GENES}.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'Symbol',
            'compound_fields': {
                'dbXrefs': {'delimiter': '|', 'field_split_prefix': ':'},
            },
            'data_property_map': {
                'GeneID': 'xrefNcbiGene',
                'Symbol': 'geneSymbol',
                'type_of_gene': 'typeOfGene',
                'Full_name_from_nomenclature_authority': 'commonName',
                'xref_MIM': 'xrefOMIM',
                'xref_HGNC': 'xrefHGNC',
                'xref_Ensembl': 'xrefEnsembl',
                'chromosome': 'chromosome',
                'source_database': 'sourceDatabase',
            },
        },
        'merge': False,
        'skip': False,
    },

    # =========================================================================
    # DoRothEA - Transcription Factor Regulatory Network
    # =========================================================================
    f'dorothea.{DOROTHEA_TRANSCRIPTION_FACTORS}': {
        'data_type': 'node',
        'node_type': 'TranscriptionFactor',
        'source_filename': f'{DOROTHEA_TRANSCRIPTION_FACTORS}.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'tf_symbol',
            'data_property_map': {
                'tf_symbol': 'TF',
                'source_database': 'sourceDatabase',
            },
        },
        'merge': True,
        'skip': False,
    },
    f'dorothea.{DOROTHEA_TF_GENE_INTERACTIONS}': {
        'data_type': 'relationship',
        'relationship_type': 'transcriptionFactorInteractsWithGene',
        'source_label': 'DoRothEA',
        'source_filename': f'{DOROTHEA_TF_GENE_INTERACTIONS}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'TranscriptionFactor',
            'subject_column_name': 'tf_symbol',
            'subject_match_property': 'TF',
            'object_node_type': 'Gene',
            'object_column_name': 'target_gene',
            'object_match_property': 'geneSymbol',
            'data_property_map': {
                'mor_score': 'morScore',
                'confidence': 'confidence',
            },
        },
        'merge': False,
        'skip': False,
    },

    # =========================================================================
    # ClinicalTrials.gov - Clinical Trial Nodes and Relationships
    # =========================================================================
    f'clinicaltrials.{CT_CLINICAL_TRIALS}': {
        'data_type': 'node',
        'node_type': 'ClinicalTrial',
        'source_filename': f'{CT_CLINICAL_TRIALS}.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'nct_id',
            'data_property_map': {
                'nct_id': 'trialId',
                'brief_title': 'commonName',
                'phase': 'phase',
                'status': 'status',
                'source_database': 'sourceDatabase',
            },
        },
        'merge': False,
        'skip': False,
    },
    f'clinicaltrials.{CT_TRIAL_STUDIES_CONDITION}': {
        'data_type': 'relationship',
        'relationship_type': 'STUDIES_CONDITION',
        'source_label': 'ClinicalTrials.gov',
        'source_filename': f'{CT_TRIAL_STUDIES_CONDITION}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'ClinicalTrial',
            'subject_column_name': 'nct_id',
            'subject_match_property': 'trialId',
            'object_node_type': 'Disease',
            'object_column_name': 'condition',
            'object_match_property': 'commonName',
        },
        'merge': False,
        'skip': False,
    },
    f'clinicaltrials.{CT_TRIAL_TESTS_INTERVENTION}': {
        'data_type': 'relationship',
        'relationship_type': 'TESTS_INTERVENTION',
        'source_label': 'ClinicalTrials.gov',
        'source_filename': f'{CT_TRIAL_TESTS_INTERVENTION}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'ClinicalTrial',
            'subject_column_name': 'nct_id',
            'subject_match_property': 'trialId',
            'object_node_type': 'Drug',
            'object_column_name': 'intervention_name',
            'object_match_property': 'commonName',
        },
        'merge': False,
        'skip': False,
    },

    # =========================================================================
    # ClinPGx - Pharmacogenomics
    # =========================================================================
    f'clinpgx.{CLINPGX_VARIANTS}': {
        'data_type': 'node',
        'node_type': 'Variant',
        'source_filename': f'{CLINPGX_VARIANTS}.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'variant_id',
            'data_property_map': {
                'variant_id': 'variantId',
                'variant_name': 'commonName',
                'gene': 'gene',
                'chromosome': 'chromosome',
                'position': 'position',
                'change_classification': 'changeClassification',
                'source_database': 'sourceDatabase',
            },
        },
        'merge': False,
        'skip': True,
    },
    f'clinpgx.{CLINPGX_DRUG_LABELS}': {
        'data_type': 'node',
        'node_type': 'DrugLabel',
        'source_filename': f'{CLINPGX_DRUG_LABELS}.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'guideline_id',
            'data_property_map': {
                'guideline_id': 'labelId',
                'guideline_name': 'commonName',
                'url': 'url',
                'version': 'version',
                'source_database': 'sourceDatabase',
            },
        },
        'merge': False,
        'skip': False,
    },
    f'clinpgx.{CLINPGX_CLINICAL_ANNOTATIONS}': {
        'data_type': 'relationship',
        'relationship_type': 'AFFECTS_RESPONSE_TO',
        'source_label': 'ClinPGx',
        'source_filename': f'{CLINPGX_CLINICAL_ANNOTATIONS}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Gene',
            'subject_column_name': 'gene_symbol',
            'subject_match_property': 'geneSymbol',
            'object_node_type': 'Drug',
            'object_column_name': 'drug_name',
            'object_match_property': 'commonName',
            'data_property_map': {
                'phenotype': 'phenotype',
                'classification': 'classification',
            },
        },
        'merge': False,
        'skip': False,
    },
    f'clinpgx.{CLINPGX_VARIANT_IN_GENE}': {
        'data_type': 'relationship',
        'relationship_type': 'VARIANT_IN',
        'source_label': 'ClinPGx',
        'source_filename': f'{CLINPGX_VARIANT_IN_GENE}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Variant',
            'subject_column_name': 'variant_id',
            'subject_match_property': 'variantId',
            'object_node_type': 'Gene',
            'object_column_name': 'gene',
            'object_match_property': 'geneSymbol',
        },
        'merge': False,
        'skip': True,
    },
    f'clinpgx.{CLINPGX_CLINICAL_ANNOTATIONS_PHARMA_CLASS}': {
        'data_type': 'relationship',
        'relationship_type': 'AFFECTS_RESPONSE_TO_CLASS',
        'source_label': 'ClinPGx',
        'source_filename': f'{CLINPGX_CLINICAL_ANNOTATIONS_PHARMA_CLASS}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Gene',
            'subject_column_name': 'gene',
            'subject_match_property': 'geneSymbol',
            'object_node_type': 'PharmacologicClass',
            'object_column_name': 'pharma_class',
            'object_match_property': 'commonName',
        },
        'merge': False,
        'skip': True,
    },
    f'clinpgx.{CLINPGX_DRUG_LABEL_ANNOTATES_GENE}': {
        'data_type': 'relationship',
        'relationship_type': 'drugLabelAnnotatesGene',
        'source_label': 'ClinPGx',
        'source_filename': f'{CLINPGX_DRUG_LABEL_ANNOTATES_GENE}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'DrugLabel',
            'subject_column_name': 'label_id',
            'subject_match_property': 'labelId',
            'object_node_type': 'Gene',
            'object_column_name': 'gene',
            'object_match_property': 'geneSymbol',
        },
        'merge': False,
        'skip': True,
    },
    f'clinpgx.{CLINPGX_DRUG_LABEL_DESCRIBES_DRUG}': {
        'data_type': 'relationship',
        'relationship_type': 'drugLabelDescribesDrug',
        'source_label': 'ClinPGx',
        'source_filename': f'{CLINPGX_DRUG_LABEL_DESCRIBES_DRUG}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'DrugLabel',
            'subject_column_name': 'label_id',
            'subject_match_property': 'labelId',
            'object_node_type': 'Drug',
            'object_column_name': 'drug',
            'object_match_property': 'commonName',
        },
        'merge': False,
        'skip': True,
    },

    # =========================================================================
    # Hetionet Components (Phase 2)
    # =========================================================================

    # ---- Disease Ontology ----
    f'disease_ontology.{DO_DISEASE_NODES}': {
        'data_type': 'node',
        'node_type': 'Disease',
        'source_filename': f'{DO_DISEASE_NODES}.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'doid',
            'data_property_map': {
                'doid': 'xrefDiseaseOntology',
                'disease_name': 'commonName',
                'definition': 'definition',
                'source_database': 'sourceDatabase',
            },
        },
        'merge': True,
        'skip': False,
    },
    f'disease_ontology.{DO_DISEASE_ANATOMY}': {
        'data_type': 'relationship',
        'relationship_type': 'diseaseLocalizesToAnatomy',
        'source_label': 'Disease Ontology',
        'source_filename': f'{DO_DISEASE_ANATOMY}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Disease',
            'subject_column_name': 'disease_id',
            'subject_match_property': 'xrefDiseaseOntology',
            'object_node_type': 'BodyPart',
            'object_column_name': 'anatomy_id',
            'object_match_property': 'xrefUberon',
        },
        'merge': False,
        'skip': True,  # No TSV produced; MEDLINE covers diseaseLocalizesToAnatomy
    },
    f'disease_ontology.{DO_DISEASE_XREFS}': {
        'data_type': 'node',
        'node_type': 'Disease',
        'source_filename': f'{DO_DISEASE_XREFS}.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'doid',
            'data_property_map': {
                'doid': 'xrefDiseaseOntology',
                'xref': 'xref',
            },
        },
        'merge': True,
        'skip': True,  # One-to-many xrefs (MESH, ICD10, OMIM per disease); row-by-row loader would overwrite. Xref IDs already mapped via id_mapping.py.
    },
    f'disease_ontology.{DO_DISEASE_HIERARCHY}': {
        'data_type': 'relationship',
        'relationship_type': 'diseaseIsSubtypeOf',
        'source_label': 'Disease Ontology',
        'source_filename': f'{DO_DISEASE_HIERARCHY}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Disease',
            'subject_column_name': 'child_id',
            'subject_match_property': 'xrefDiseaseOntology',
            'object_node_type': 'Disease',
            'object_column_name': 'parent_id',
            'object_match_property': 'xrefDiseaseOntology',
        },
        'merge': True,
        'skip': True,
    },

    # ---- Gene Ontology ----
    f'gene_ontology.{GO_BP_NODES}': {
        'data_type': 'node',
        'node_type': 'BiologicalProcess',
        'source_filename': f'{GO_BP_NODES}.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'go_id',
            'data_property_map': {
                'go_id': 'geneOntologyId',
                'name': 'commonName',
                'definition': 'definition',
            },
        },
        'merge': False,
        'skip': False,
    },
    f'gene_ontology.{GO_MF_NODES}': {
        'data_type': 'node',
        'node_type': 'MolecularFunction',
        'source_filename': f'{GO_MF_NODES}.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'go_id',
            'data_property_map': {
                'go_id': 'geneOntologyId',
                'name': 'commonName',
                'definition': 'definition',
            },
        },
        'merge': False,
        'skip': False,
    },
    f'gene_ontology.{GO_CC_NODES}': {
        'data_type': 'node',
        'node_type': 'CellularComponent',
        'source_filename': f'{GO_CC_NODES}.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'go_id',
            'data_property_map': {
                'go_id': 'geneOntologyId',
                'name': 'commonName',
                'definition': 'definition',
            },
        },
        'merge': False,
        'skip': False,
    },
    f'gene_ontology.{GO_GENE_BP}': {
        'data_type': 'relationship',
        'relationship_type': 'geneParticipatesInBiologicalProcess',
        'source_label': 'Gene Ontology',
        'source_filename': f'{GO_GENE_BP}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Gene',
            'subject_column_name': 'gene_symbol',
            'subject_match_property': 'geneSymbol',
            'object_node_type': 'BiologicalProcess',
            'object_column_name': 'go_id',
            'object_match_property': 'geneOntologyId',
        },
        'merge': False,
        'skip': False,
    },
    f'gene_ontology.{GO_GENE_MF}': {
        'data_type': 'relationship',
        'relationship_type': 'geneHasMolecularFunction',
        'source_label': 'Gene Ontology',
        'source_filename': f'{GO_GENE_MF}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Gene',
            'subject_column_name': 'gene_symbol',
            'subject_match_property': 'geneSymbol',
            'object_node_type': 'MolecularFunction',
            'object_column_name': 'go_id',
            'object_match_property': 'geneOntologyId',
        },
        'merge': False,
        'skip': False,
    },
    f'gene_ontology.{GO_GENE_CC}': {
        'data_type': 'relationship',
        'relationship_type': 'geneAssociatedWithCellularComponent',
        'source_label': 'Gene Ontology',
        'source_filename': f'{GO_GENE_CC}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Gene',
            'subject_column_name': 'gene_symbol',
            'subject_match_property': 'geneSymbol',
            'object_node_type': 'CellularComponent',
            'object_column_name': 'go_id',
            'object_match_property': 'geneOntologyId',
        },
        'merge': False,
        'skip': False,
    },

    # ---- Uberon ----
    f'uberon.{UBERON_ANATOMY_NODES}': {
        'data_type': 'node',
        'node_type': 'BodyPart',
        'source_filename': f'{UBERON_ANATOMY_NODES}.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'uberon_id',
            'data_property_map': {
                'uberon_id': 'xrefUberon',
                'uberon_name': 'commonName',
                'definition': 'definition',
                'source_database': 'sourceDatabase',
            },
        },
        'merge': False,
        'skip': False,
    },

    # ---- MeSH ----
    f'mesh.{MESH_SYMPTOM_NODES}': {
        'data_type': 'node',
        'node_type': 'Symptom',
        'source_filename': f'{MESH_SYMPTOM_NODES}.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'mesh_id',
            'data_property_map': {
                'mesh_id': 'xrefMeSH',
                'mesh_name': 'commonName',
                'sourceDatabase': 'sourceDatabase',
            },
        },
        'merge': False,
        'skip': False,
    },

    # ---- SIDER ----
    f'sider.{SIDER_SIDE_EFFECT_NODES}': {
        'data_type': 'node',
        'node_type': 'SideEffect',
        'source_filename': f'{SIDER_SIDE_EFFECT_NODES}.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'umls_id',
            'data_property_map': {
                'umls_id': 'xrefUmlsCUI',
                'side_effect_name': 'commonName',
                'source_database': 'sourceDatabase',
            },
        },
        'merge': False,
        'skip': False,
    },
    f'sider.{SIDER_COMPOUND_CAUSES_SE}': {
        'data_type': 'relationship',
        'relationship_type': 'compoundCausesSideEffect',
        'source_label': 'SIDER',
        'source_filename': f'{SIDER_COMPOUND_CAUSES_SE}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Drug',
            'subject_column_name': 'pubchem_cid',
            'subject_match_property': 'xrefPubChemCID',
            'object_node_type': 'SideEffect',
            'object_column_name': 'umls_id',
            'object_match_property': 'xrefUmlsCUI',
        },
        'merge': False,
        'skip': False,
    },
    f'sider.{SIDER_DRUG_NODES}': {
        'data_type': 'node',
        'node_type': 'Drug',
        'source_filename': f'{SIDER_DRUG_NODES}.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'pubchem_cid',
            'data_property_map': {
                'pubchem_cid': 'xrefPubChemCID',
                'stitch_id': 'xrefStitch',
                'source_database': 'sourceDatabase',
            },
        },
        'merge': True,
        'skip': False,
    },

    # ---- LINCS L1000 ----
    f'lincs.{LINCS_CUG}': {
        'data_type': 'relationship',
        'relationship_type': 'compoundUpregulatesGene',
        'source_label': 'LINCS L1000',
        'source_filename': f'{LINCS_CUG}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Drug',
            'subject_column_name': 'compound_name',
            'subject_match_property': 'commonName',
            'object_node_type': 'Gene',
            'object_column_name': 'gene_symbol',
            'object_match_property': 'geneSymbol',
        },
        'merge': False,
        'skip': False,
    },
    f'lincs.{LINCS_CDG}': {
        'data_type': 'relationship',
        'relationship_type': 'compoundDownregulatesGene',
        'source_label': 'LINCS L1000',
        'source_filename': f'{LINCS_CDG}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Drug',
            'subject_column_name': 'compound_name',
            'subject_match_property': 'commonName',
            'object_node_type': 'Gene',
            'object_column_name': 'gene_symbol',
            'object_match_property': 'geneSymbol',
        },
        'merge': False,
        'skip': False,
    },
    f'lincs.{LINCS_GRG}': {
        'data_type': 'relationship',
        'relationship_type': 'geneRegulatesGene',
        'source_label': 'LINCS L1000',
        'source_filename': f'{LINCS_GRG}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Gene',
            'subject_column_name': 'source_gene',
            'subject_match_property': 'xrefNcbiGene',
            'subject_match_type': 'integer',
            'object_node_type': 'Gene',
            'object_column_name': 'target_gene',
            'object_match_property': 'xrefNcbiGene',
            'object_match_type': 'integer',
            'data_property_map': {
                'z_score': 'zScore',
            },
        },
        'merge': False,
        'skip': True,
    },

    # ---- MEDLINE Co-occurrence ----
    f'medline.{MEDLINE_DPS}': {
        'data_type': 'relationship',
        'relationship_type': 'diseasePresentsSymptom',
        'source_label': 'MEDLINE',
        'source_filename': f'{MEDLINE_DPS}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Disease',
            'subject_column_name': 'doid_code',
            'subject_match_property': 'xrefDiseaseOntology',
            'object_node_type': 'Symptom',
            'object_column_name': 'mesh_id',
            'object_match_property': 'xrefMeSH',
        },
        'merge': False,
        'skip': True,
    },
    f'medline.{MEDLINE_DLA}': {
        'data_type': 'relationship',
        'relationship_type': 'diseaseLocalizesToAnatomy',
        'source_label': 'MEDLINE',
        'source_filename': f'{MEDLINE_DLA}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Disease',
            'subject_column_name': 'doid_code',
            'subject_match_property': 'xrefDiseaseOntology',
            'object_node_type': 'BodyPart',
            'object_column_name': 'uberon_id',
            'object_match_property': 'xrefUberon',
        },
        'merge': False,
        'skip': True,
    },
    f'medline.{MEDLINE_DRD}': {
        'data_type': 'relationship',
        'relationship_type': 'diseaseResemblesDisease',
        'source_label': 'MEDLINE',
        'source_filename': f'{MEDLINE_DRD}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Disease',
            'subject_column_name': 'doid_code_0',
            'subject_match_property': 'xrefDiseaseOntology',
            'object_node_type': 'Disease',
            'object_column_name': 'doid_code_1',
            'object_match_property': 'xrefDiseaseOntology',
        },
        'merge': False,
        'skip': True,
    },

    # ---- DrugCentral ----
    'drugcentral.drugs': {
        'data_type': 'node',
        'node_type': 'Drug',
        'source_filename': 'drugs.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'drugbank_id',
            'data_property_map': {
                'drugbank_id': 'xrefDrugbank',
                'struct_id': 'xrefDrugCentral',
                'drug_name': 'commonName',
                'pubchem_cid': 'xrefPubChemCID',
                'source_database': 'sourceDatabase',
            },
        },
        'merge': True,
        'skip': False,
    },
    f'drugcentral.{DC_PHARMACOLOGIC_CLASSES}': {
        'data_type': 'node',
        'node_type': 'PharmacologicClass',
        'source_filename': f'{DC_PHARMACOLOGIC_CLASSES}.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'pharma_class_id',
            'data_property_map': {
                'pharma_class_id': 'classId',
                'pharma_class_name': 'commonName',
                'pharma_class_code': 'classCode',
                'source_database': 'sourceDatabase',
            },
        },
        'merge': False,
        'skip': False,
    },
    f'drugcentral.{DC_PCIC}': {
        'data_type': 'relationship',
        'relationship_type': 'pharmacologicClassIncludesCompound',
        'inverse_relationship_type': 'compoundInPharmacologicClass',
        'source_label': 'DrugCentral',
        'source_filename': f'{DC_PCIC}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'PharmacologicClass',
            'subject_column_name': 'pharma_class_id',
            'subject_match_property': 'classId',
            'object_node_type': 'Drug',
            'object_column_name': 'struct_id',
            'object_match_property': 'xrefDrugCentral',
        },
        'merge': False,
        'skip': False,
    },
    f'drugcentral.{DC_DRUG_TREATS}': {
        'data_type': 'relationship',
        'relationship_type': 'drugTreatsDisease',
        'source_label': 'DrugCentral',
        'source_filename': f'{DC_DRUG_TREATS}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Drug',
            'subject_column_name': 'drugbank_id',
            'subject_match_property': 'xrefDrugbank',
            'object_node_type': 'Disease',
            'object_column_name': 'doid',
            'object_match_property': 'xrefDiseaseOntology',
        },
        'merge': False,
        'skip': True,
    },
    f'drugcentral.{DC_DRUG_PALLIATES}': {
        'data_type': 'relationship',
        'relationship_type': 'drugPalliatesDisease',
        'source_label': 'DrugCentral',
        'source_filename': f'{DC_DRUG_PALLIATES}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Drug',
            'subject_column_name': 'drugbank_id',
            'subject_match_property': 'xrefDrugbank',
            'object_node_type': 'Disease',
            'object_column_name': 'doid',
            'object_match_property': 'xrefDiseaseOntology',
        },
        'merge': False,
        'skip': True,
    },

    # ---- GWAS Catalog — REMOVED (redundant with OpenTargets) ----
    f'gwas.{GWAS_GENE_DISEASE}': {
        'data_type': 'relationship',
        'relationship_type': 'geneAssociatesWithDisease',
        'source_label': 'GWAS Catalog',
        'source_filename': f'{GWAS_GENE_DISEASE}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Gene',
            'subject_column_name': 'gene_symbol',
            'subject_match_property': 'geneSymbol',
            'object_node_type': 'Disease',
            'object_column_name': 'disease_doid',
            'object_match_property': 'xrefDiseaseOntology',
        },
        'merge': False,
        'skip': True,
    },

    # ---- PubTator ----
    f'pubtator.{PUBTATOR_DD_COOCCURRENCE}': {
        'data_type': 'relationship',
        'relationship_type': 'diseaseAssociatesWithDisease',
        'source_label': 'PubTator',
        'source_filename': f'{PUBTATOR_DD_COOCCURRENCE}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Disease',
            'subject_column_name': 'disease1_id',
            'subject_match_property': 'xrefDiseaseOntology',
            'object_node_type': 'Disease',
            'object_column_name': 'disease2_id',
            'object_match_property': 'xrefDiseaseOntology',
        },
        'merge': False,
        'skip': True,
    },
    f'pubtator.{PUBTATOR_GD_LITERATURE}': {
        'data_type': 'relationship',
        'relationship_type': 'geneAssociatesWithDisease',
        'source_label': 'PubTator',
        'source_filename': f'{PUBTATOR_GD_LITERATURE}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Gene',
            'subject_column_name': 'gene_id',
            'subject_match_property': 'xrefNcbiGene',
            'subject_match_type': 'integer',
            'object_node_type': 'Disease',
            'object_column_name': 'disease_id',
            'object_match_property': 'xrefDiseaseOntology',
            'data_property_map': {
                'pmid': 'pmid',
            },
        },
        'merge': False,
        'skip': False,
    },

    # ---- BindingDB ----
    f'bindingdb.{BINDINGDB_DRUG_BINDS_GENE}': {
        'data_type': 'relationship',
        'relationship_type': 'chemicalBindsGene',
        'source_label': 'BindingDB',
        'source_filename': f'{BINDINGDB_DRUG_BINDS_GENE}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Drug',
            'subject_column_name': 'drugbank_id',
            'subject_match_property': 'xrefDrugbank',
            'object_node_type': 'Gene',
            'object_column_name': 'gene_symbol',
            'object_match_property': 'geneSymbol',
        },
        'merge': False,
        'skip': False,
    },

    # ---- CTD ----
    f'ctd.{CTD_CHEMICAL_NODES}': {
        'data_type': 'node',
        'node_type': 'Drug',
        'source_filename': f'{CTD_CHEMICAL_NODES}.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'mesh_id',
            'data_property_map': {
                'mesh_id': 'xrefMeSH',
                'chemical_name': 'commonName',
                'source_database': 'sourceDatabase',
            },
        },
        'merge': True,
        'skip': False,
    },
    f'ctd.{CTD_CHEM_INCREASES_EXPR}': {
        'data_type': 'relationship',
        'relationship_type': 'chemicalIncreasesExpression',
        'source_label': 'CTD',
        'source_filename': f'{CTD_CHEM_INCREASES_EXPR}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Drug',
            'subject_column_name': 'chemical_id',
            'subject_match_property': 'xrefMeSH',
            'object_node_type': 'Gene',
            'object_column_name': 'gene_id',
            'object_match_property': 'xrefNcbiGene',
            'object_match_type': 'integer',
        },
        'merge': False,
        'skip': False,
    },
    f'ctd.{CTD_CHEM_DECREASES_EXPR}': {
        'data_type': 'relationship',
        'relationship_type': 'chemicalDecreasesExpression',
        'source_label': 'CTD',
        'source_filename': f'{CTD_CHEM_DECREASES_EXPR}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Drug',
            'subject_column_name': 'chemical_id',
            'subject_match_property': 'xrefMeSH',
            'object_node_type': 'Gene',
            'object_column_name': 'gene_id',
            'object_match_property': 'xrefNcbiGene',
            'object_match_type': 'integer',
        },
        'merge': False,
        'skip': False,
    },

    # ---- Bgee ----
    f'bgee.{BGEE_OVEREXPRESSES}': {
        'data_type': 'relationship',
        'relationship_type': 'bodyPartExpressesGene',
        'source_label': 'Bgee',
        'source_filename': f'{BGEE_OVEREXPRESSES}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'BodyPart',
            'subject_column_name': 'uberon_id',
            'subject_match_property': 'xrefUberon',
            'object_node_type': 'Gene',
            'object_column_name': 'ensembl_gene_id',
            'object_match_property': 'xrefEnsembl',
            'data_property_map': {
                'expression_score': 'expressionScore',
            },
        },
        'merge': False,
        'skip': False,
    },
    f'bgee.{BGEE_UNDEREXPRESSES}': {
        'data_type': 'relationship',
        'relationship_type': 'bodyPartExpressesGene',
        'source_label': 'Bgee',
        'source_filename': f'{BGEE_UNDEREXPRESSES}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'BodyPart',
            'subject_column_name': 'uberon_id',
            'subject_match_property': 'xrefUberon',
            'object_node_type': 'Gene',
            'object_column_name': 'ensembl_gene_id',
            'object_match_property': 'xrefEnsembl',
            'data_property_map': {
                'expression_score': 'expressionScore',
            },
        },
        'merge': False,
        'skip': True,  # Same file as BGEE_OVEREXPRESSES; skip to avoid duplicate edges
    },

    # ---- Hetionet Precomputed — REMOVED (redundant with STRING, LINCS, SIDER) ----
    f'hetionet_precomputed.{HETIO_GENE_INTERACTS}': {
        'data_type': 'relationship',
        'relationship_type': 'geneInteractsWithGene',
        'source_label': 'Hetionet',
        'source_filename': f'{HETIO_GENE_INTERACTS}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Gene',
            'subject_column_name': 'gene1_symbol',
            'subject_match_property': 'xrefNcbiGene',
            'object_node_type': 'Gene',
            'object_column_name': 'gene2_symbol',
            'object_match_property': 'xrefNcbiGene',
        },
        'merge': False,
        'skip': True,
    },
    f'hetionet_precomputed.{HETIO_GENE_COVARIES}': {
        'data_type': 'relationship',
        'relationship_type': 'geneCovariesWithGene',
        'source_label': 'Hetionet',
        'source_filename': f'{HETIO_GENE_COVARIES}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Gene',
            'subject_column_name': 'gene1_symbol',
            'subject_match_property': 'xrefNcbiGene',
            'object_node_type': 'Gene',
            'object_column_name': 'gene2_symbol',
            'object_match_property': 'xrefNcbiGene',
        },
        'merge': False,
        'skip': True,
    },
    f'hetionet_precomputed.{HETIO_GENE_REGULATES}': {
        'data_type': 'relationship',
        'relationship_type': 'geneRegulatesGene',
        'source_label': 'Hetionet',
        'source_filename': f'{HETIO_GENE_REGULATES}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Gene',
            'subject_column_name': 'gene1_symbol',
            'subject_match_property': 'xrefNcbiGene',
            'object_node_type': 'Gene',
            'object_column_name': 'gene2_symbol',
            'object_match_property': 'xrefNcbiGene',
        },
        'merge': False,
        'skip': True,  # Subset of LINCS L1000 geneRegulatesGene; LINCS overwrites r.source
    },

    f'hetionet_precomputed.{HETIO_DRUG_CAUSES_EFFECT}': {
        'data_type': 'relationship',
        'relationship_type': 'drugCausesSideEffect',
        'source_label': 'Hetionet',
        'source_filename': f'{HETIO_DRUG_CAUSES_EFFECT}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Drug',
            'subject_column_name': 'drug_id',
            'subject_match_property': 'xrefDrugbank',
            'object_node_type': 'SideEffect',
            'object_column_name': 'effect_id',
            'object_match_property': 'xrefUmlsCUI',
        },
        'merge': False,
        'skip': True,
    },

    # =========================================================================
    # Jensen Lab DISEASES — REMOVED (redundant with OpenTargets)
    # =========================================================================
    f'jensenlab.{JENSENLAB_GENE_DISEASE}': {
        'data_type': 'relationship',
        'relationship_type': 'geneAssociatesWithDisease',
        'source_label': 'Jensen DISEASES',
        'source_filename': f'{JENSENLAB_GENE_DISEASE}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Gene',
            'subject_column_name': 'gene_symbol',
            'subject_match_property': 'geneSymbol',
            'object_node_type': 'Disease',
            'object_column_name': 'disease_id',
            'object_match_property': 'xrefDiseaseOntology',
            'data_property_map': {
                'confidence': 'confidence',
                'channel': 'channel',
            },
        },
        'merge': False,
        'skip': True,
    },

    # =========================================================================
    # Jensen Lab TISSUES — BTO Tissue Nodes (new BodyParts not in Uberon)
    # =========================================================================
    f'jensen_tissues.{JENSEN_TISSUES_TISSUE_NODES}': {
        'data_type': 'node',
        'node_type': 'BodyPart',
        'source_filename': f'{JENSEN_TISSUES_TISSUE_NODES}.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'xrefUberon',
            'data_property_map': {
                'xrefUberon': 'xrefUberon',
                'commonName': 'commonName',
            },
        },
        'merge': True,
        'skip': True,
    },

    # =========================================================================
    # Jensen Lab TISSUES — Gene-Tissue Expression Associations
    # =========================================================================
    f'jensen_tissues.{JENSEN_TISSUES_GENE_TISSUE}': {
        'data_type': 'relationship',
        'relationship_type': 'geneExpressedInBodyPart',
        'source_label': 'Jensen TISSUES',
        'source_filename': f'{JENSEN_TISSUES_GENE_TISSUE}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Gene',
            'subject_column_name': 'gene_symbol',
            'subject_match_property': 'geneSymbol',
            'object_node_type': 'BodyPart',
            'object_column_name': 'tissue_name',
            'object_match_property': 'commonName',
            'data_property_map': {
                'evidence_type': 'evidenceType',
                'score': 'score',
            },
        },
        'merge': False,
        'skip': False,
    },

    # =========================================================================
    # HPO — Human Phenotype Ontology Nodes
    # =========================================================================
    f'hpo.{HPO_PHENOTYPE_NODES}': {
        'data_type': 'node',
        'node_type': 'Phenotype',
        'source_filename': f'{HPO_PHENOTYPE_NODES}.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'hp_id',
            'data_property_map': {
                'hp_id': 'xrefHPO',
                'hp_name': 'commonName',
                'definition': 'definition',
                'synonyms': 'synonyms',
                'source_database': 'sourceDatabase',
            },
        },
        'merge': False,
        'skip': False,
    },

    # ---- HPO Gene-Phenotype Associations ----
    f'hpo.{HPO_GENE_PHENOTYPE}': {
        'data_type': 'relationship',
        'relationship_type': 'geneAssociatesWithPhenotype',
        'source_label': 'HPO',
        'source_filename': f'{HPO_GENE_PHENOTYPE}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Gene',
            'subject_column_name': 'ncbi_gene_id',
            'subject_match_property': 'xrefNcbiGene',
            'subject_match_type': 'integer',
            'object_node_type': 'Phenotype',
            'object_column_name': 'hp_id',
            'object_match_property': 'xrefHPO',
        },
        'merge': False,
        'skip': False,
    },

    # =========================================================================
    # Reactome — Pathway Nodes
    # =========================================================================
    f'reactome.{REACTOME_PATHWAY_NODES}': {
        'data_type': 'node',
        'node_type': 'Pathway',
        'source_filename': f'{REACTOME_PATHWAY_NODES}.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'reactome_id',
            'data_property_map': {
                'reactome_id': 'pathwayId',
                'pathway_name': 'pathwayName',
                'species': 'species',
                'source_database': 'sourceDatabase',
            },
        },
        'merge': True,
        'skip': False,
    },

    # ---- Reactome Gene-Pathway Edges ----
    f'reactome.{REACTOME_GENE_PATHWAY}': {
        'data_type': 'relationship',
        'relationship_type': 'geneInPathway',
        'inverse_relationship_type': 'pathwayContainsGene',
        'source_label': 'Reactome',
        'source_filename': f'{REACTOME_GENE_PATHWAY}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Gene',
            'subject_column_name': 'ncbi_gene_id',
            'subject_match_property': 'xrefNcbiGene',
            'subject_match_type': 'integer',
            'object_node_type': 'Pathway',
            'object_column_name': 'reactome_id',
            'object_match_property': 'pathwayId',
            'data_property_map': {
                'evidence_code': 'evidenceCode',
            },
        },
        'merge': False,
        'skip': False,
    },

    # =========================================================================
    # WikiPathways — REMOVED (redundant with Reactome)
    # =========================================================================
    f'wikipathways.{WIKIPATHWAYS_PATHWAY_NODES}': {
        'data_type': 'node',
        'node_type': 'Pathway',
        'source_filename': f'{WIKIPATHWAYS_PATHWAY_NODES}.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'pathwayName',
            'data_property_map': {
                'pathwayName': 'pathwayName',
                'sourceDatabase': 'sourceDatabase',
            },
        },
        'merge': True,
        'skip': True,
    },
    f'wikipathways.{WIKIPATHWAYS_GENE_PATHWAY}': {
        'data_type': 'relationship',
        'relationship_type': 'geneInPathway',
        'inverse_relationship_type': 'pathwayContainsGene',
        'source_label': 'WikiPathways',
        'source_filename': f'{WIKIPATHWAYS_GENE_PATHWAY}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Gene',
            'subject_column_name': 'ncbi_gene_id',
            'subject_match_property': 'xrefNcbiGene',
            'object_node_type': 'Pathway',
            'object_column_name': 'pathway_name',
            'object_match_property': 'pathwayName',
        },
        'merge': False,
        'skip': True,
    },

    # =========================================================================
    # STRING — Protein-Protein Interactions (high confidence)
    # =========================================================================
    f'string.{STRING_GENE_INTERACTS}': {
        'data_type': 'relationship',
        'relationship_type': 'geneInteractsWithGene',
        'source_label': 'STRING',
        'source_filename': f'{STRING_GENE_INTERACTS}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Gene',
            'subject_column_name': 'gene_id_1',
            'subject_match_property': 'xrefNcbiGene',
            'subject_match_type': 'integer',
            'object_node_type': 'Gene',
            'object_column_name': 'gene_id_2',
            'object_match_property': 'xrefNcbiGene',
            'object_match_type': 'integer',
            'data_property_map': {
                'combined_score': 'combinedScore',
            },
        },
        'merge': False,
        'skip': False,
    },

    # =========================================================================
    # OpenTargets — Gene-Disease Associations
    # =========================================================================
    f'opentargets.{OPENTARGETS_GENE_DISEASE}': {
        'data_type': 'relationship',
        'relationship_type': 'geneAssociatesWithDisease',
        'source_label': 'OpenTargets',
        'source_filename': f'{OPENTARGETS_GENE_DISEASE}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Gene',
            'subject_column_name': 'gene_symbol',
            'subject_match_property': 'geneSymbol',
            'object_node_type': 'Disease',
            'object_column_name': 'disease_id',
            'object_match_property': 'xrefDiseaseOntology',
            'data_property_map': {
                'overall_score': 'score',
            },
        },
        'merge': False,
        'skip': False,
    },

    # =========================================================================
    # HGNC Gene Families
    # =========================================================================
    'hgnc.gene_family_nodes': {
        'data_type': 'node',
        'node_type': 'GeneFamily',
        'source_filename': 'gene_family_nodes.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'family_id',
            'data_property_map': {
                'family_id': 'familyId',
                'family_name': 'familyName',
                'source_database': 'sourceDatabase',
            },
        },
        'merge': False,
        'skip': False,
    },
    'hgnc.gene_family_edges': {
        'data_type': 'relationship',
        'relationship_type': 'geneInFamily',
        'inverse_relationship_type': 'familyContainsGene',
        'source_label': 'HGNC',
        'source_filename': 'gene_family_associations.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Gene',
            'subject_column_name': 'gene_symbol',
            'subject_match_property': 'geneSymbol',
            'object_node_type': 'GeneFamily',
            'object_column_name': 'family_id',
            'object_match_property': 'familyId',
        },
        'merge': False,
        'skip': False,
    },

    # =========================================================================
    # hgnc base — REMOVED (redundant with NCBI Gene + HGNC Families)
    # =========================================================================
    'hgnc.gene_nodes': {
        'data_type': 'node',
        'node_type': 'Gene',
        'source_filename': 'gene_nodes.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'geneSymbol',
            'data_property_map': {
                'geneSymbol': 'geneSymbol',
                'hgnc_id': 'xrefHGNC',
                'geneName': 'geneName',
                'xrefEnsembl': 'xrefEnsembl',
                'xrefUcsc': 'xrefUcsc',
                'xrefRefseq': 'xrefRefseq',
                'chromosomeLocation': 'chromosomeLocation',
            },
        },
        'merge': True,
        'skip': True,
    },

    # =========================================================================
    # clinvar (auto-generated by database agent)
    # =========================================================================
    'clinvar.variant_nodes': {
        'data_type': 'node',
        'node_type': 'Variant',
        'source_filename': 'variant_nodes.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'allele_id',
            'data_property_map': {
                'allele_id': 'variantId',
                'variant_name': 'commonName',
                'variant_type': 'variantType',
                'clinical_significance': 'clinicalSignificance',
                'review_status': 'reviewStatus',
                'assembly': 'genomeAssembly',
                'chromosome': 'chromosome',
                'start_pos': 'positionStart',
                'stop_pos': 'positionStop',
                'ref_allele': 'referenceAllele',
                'alt_allele': 'alternateAllele',
                'dbsnp_id': 'dbSnpId',
                'source_database': 'sourceDatabase',
            },
        },
        'merge': False,
        'use_create': True,  # ClinVar allele_ids are unique — use CREATE for speed
        'skip': False,
    },
    'clinvar.gene_variant': {
        'data_type': 'relationship',
        'relationship_type': 'hasVariant',
        'inverse_relationship_type': 'variantInGene',
        'source_label': 'ClinVar',
        'source_filename': 'variant_gene_associations.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Gene',
            'subject_column_name': 'gene_id',
            'subject_match_property': 'xrefNcbiGene',
            'subject_match_type': 'integer',
            'object_node_type': 'Variant',
            'object_column_name': 'allele_id',
            'object_match_property': 'variantId',
            'data_property_map': {'gene_symbol': 'geneSymbol'},
        },
        'merge': False,
        'skip': False,
    },
    'clinvar.disease_variant_omim': {
        'data_type': 'relationship',
        'relationship_type': 'associatedWithVariant',
        'inverse_relationship_type': 'variantAssociatedWithDisease',
        'source_label': 'ClinVar',
        'source_filename': 'disease_variant_omim.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Disease',
            'subject_column_name': 'disease_id',
            'subject_match_property': 'xrefDiseaseOntology',
            'object_node_type': 'Variant',
            'object_column_name': 'variant_id',
            'object_match_property': 'variantId',
            'data_property_map': {'phenotype_name': 'phenotypeName', 'source_ontology': 'sourceOntology'},
        },
        'merge': False,
        'skip': True,
    },
    'clinvar.disease_variant_mondo': {
        'data_type': 'relationship',
        'relationship_type': 'associatedWithVariant',
        'inverse_relationship_type': 'variantAssociatedWithDisease',
        'source_label': 'ClinVar',
        'source_filename': 'disease_variant_mondo.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Disease',
            'subject_column_name': 'disease_id',
            'subject_match_property': 'commonName',
            'subject_match_column': 'phenotype_name',
            'object_node_type': 'Variant',
            'object_column_name': 'variant_id',
            'object_match_property': 'variantId',
            'data_property_map': {'phenotype_name': 'phenotypeName', 'source_ontology': 'sourceOntology'},
        },
        'merge': False,
        'skip': True,
    },
    'clinvar.disease_variant_orphanet': {
        'data_type': 'relationship',
        'relationship_type': 'associatedWithVariant',
        'inverse_relationship_type': 'variantAssociatedWithDisease',
        'source_label': 'ClinVar',
        'source_filename': 'disease_variant_orphanet.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Disease',
            'subject_column_name': 'disease_id',
            'subject_match_property': 'commonName',
            'subject_match_column': 'phenotype_name',
            'object_node_type': 'Variant',
            'object_column_name': 'variant_id',
            'object_match_property': 'variantId',
            'data_property_map': {'phenotype_name': 'phenotypeName', 'source_ontology': 'sourceOntology'},
        },
        'merge': False,
        'skip': True,
    },
    'clinvar.variant_properties': {
        'data_type': 'node',
        'node_type': 'Variant',
        'source_filename': 'variant_nodes.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'allele_id',
            'data_property_map': {
                'variation_id': 'variationId',
                'dbsnp_id': 'dbSnpId',
            },
        },
        'merge': True,
        'skip': True,  # Properties already loaded in clinvar.variant_nodes
    },

    # =========================================================================
    # drugage (auto-generated by database agent)
    # =========================================================================
    # =========================================================================
    # drugage — REMOVED (too sparse: 386 edges, minimal ML value)
    # =========================================================================
    'drugage.gene_nodes': {
        'data_type': 'node',
        'node_type': 'Gene',
        'source_filename': 'gene_nodes.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'geneId',
            'data_property_map': {'geneId': 'xrefNcbiGene', 'geneName': 'geneName', 'sourceDatabase': 'sourceDatabase'},
        },
        'merge': True,
        'skip': True,
    },
    'drugage.aging_property_nodes': {
        'data_type': 'node',
        'node_type': 'AgeingProperty',
        'source_filename': 'aging_property_nodes.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'propertyName',
            'data_property_map': {'propertyName': 'propertyName', 'sourceDatabase': 'sourceDatabase'},
        },
        'merge': False,
        'skip': True,
    },
    'drugage.gene_aging_association': {
        'data_type': 'relationship',
        'relationship_type': 'associatedWithAging',
        'source_label': 'DrugAge',
        'source_filename': 'gene_aging_association.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Gene',
            'subject_column_name': 'geneId',
            'subject_match_property': 'xrefNcbiGene',
            'subject_match_type': 'integer',
            'object_node_type': 'AgeingProperty',
            'object_column_name': 'agingProperty',
            'object_match_property': 'propertyName',
            'data_property_map': {'agingProperty': 'agingProperty'},
        },
        'merge': False,
        'skip': True,
    },


    # =========================================================================
    # cellage — REMOVED
    # =========================================================================
    'cellage.gene_nodes': {
        'data_type': 'node',
        'node_type': 'Gene',
        'source_filename': 'gene_nodes.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'geneSymbol',
            'data_property_map': {'geneSymbol': 'geneSymbol', 'sourceDatabase': 'sourceDatabase'},
        },
        'merge': True,
        'skip': True,
    },
    'cellage.gene_properties': {
        'data_type': 'node',
        'node_type': 'Gene',
        'source_filename': 'gene_properties.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'geneSymbol',
            'data_property_map': {'geneSymbol': 'geneSymbol', 'sourceDatabase': 'sourceDatabase'},
        },
        'merge': True,
        'skip': True,
    },



    # =========================================================================
    # anage — REMOVED (node-only source with no edges; hurts ML model training)
    # =========================================================================
    'anage.species_nodes': {
        'data_type': 'node',
        'node_type': 'Species',
        'source_filename': 'species_nodes.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'speciesName',
            'data_property_map': {
                'speciesName': 'speciesName',
                'commonName': 'commonName',
                'maximumLifespan': 'maximumLifespan',
                'sampleSize': 'sampleSize',
                'sourceDatabase': 'sourceDatabase',
            },
        },
        'merge': False,
        'skip': True,
    },

    # =========================================================================
    # genage — REMOVED
    # =========================================================================
    'genage.gene_nodes': {
        'data_type': 'node',
        'node_type': 'Gene',
        'source_filename': 'gene_nodes.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'geneSymbol',
            'data_property_map': {'geneSymbol': 'geneSymbol', 'xrefNcbiGene': 'xrefNcbiGene', 'sourceDatabase': 'sourceDatabase'},
        },
        'merge': True,
        'skip': True,
    },
}
