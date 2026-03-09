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
DISGENET_GENE_DISEASE_ASSOCIATIONS = 'gene_disease_associations'
# DrugBank
DRUGBANK_DRUGS = 'drugs'
# NCBI Gene
NCBI_GENES = 'genes'
# DoRothEA
DOROTHEA_TRANSCRIPTION_FACTORS = 'transcription_factors'
DOROTHEA_TF_GENE_INTERACTIONS = 'tf_gene_interactions'
# ClinicalTrials.gov
CT_CLINICAL_TRIALS = 'clinical_trials'
CT_TRIAL_STUDIES_CONDITION = 'trial_studies_condition'
CT_TRIAL_TESTS_INTERVENTION = 'trial_tests_intervention'
# ClinPGx
CLINPGX_CLINICAL_ANNOTATIONS = 'clinical_annotations'
CLINPGX_DRUG_LABELS = 'drug_labels'
CLINPGX_VARIANTS = 'variants'
CLINPGX_VARIANT_IN_GENE = 'variant_in_gene'

# Hetionet Components — Disease Ontology
DO_DISEASE_NODES = 'disease_nodes'
DO_DISEASE_ANATOMY = 'disease_anatomy'
# Hetionet Components — Gene Ontology
GO_BP_NODES = 'biological_process_nodes'
GO_MF_NODES = 'molecular_function_nodes'
GO_CC_NODES = 'cellular_component_nodes'
GO_GENE_BP = 'gene_bp_associations'
GO_GENE_MF = 'gene_mf_associations'
GO_GENE_CC = 'gene_cc_associations'
# Hetionet Components — Uberon
UBERON_ANATOMY_NODES = 'anatomy_nodes'
# Hetionet Components — MeSH
MESH_SYMPTOM_NODES = 'symptom_nodes'
# Hetionet Components — SIDER
SIDER_SIDE_EFFECT_NODES = 'side_effect_nodes'
SIDER_COMPOUND_CAUSES_SE = 'compound_causes_side_effect'
# Hetionet Components — LINCS
LINCS_CUG = 'compound_upregulates_gene'
LINCS_CDG = 'compound_downregulates_gene'
LINCS_GRG = 'gene_regulates_gene'
# Hetionet Components — MEDLINE
MEDLINE_DPS = 'disease_symptom_cooccurrence'
MEDLINE_DLA = 'disease_anatomy_cooccurrence'
MEDLINE_DRD = 'disease_disease_cooccurrence'
# Hetionet Components — DrugCentral
DC_PHARMACOLOGIC_CLASSES = 'pharmacologic_classes'
DC_PCIC = 'pharmacologic_class_includes_compound'
DC_DRUG_TREATS = 'drug_treats_disease'
DC_DRUG_PALLIATES = 'drug_palliates_disease'
# Hetionet Components — GWAS
GWAS_GENE_DISEASE = 'gene_disease_gwas'
# Hetionet Components — PubTator
PUBTATOR_DD_COOCCURRENCE = 'disease_disease_cooccurrence'
PUBTATOR_GD_LITERATURE = 'gene_disease_literature'
# Hetionet Components — BindingDB
BINDINGDB_DRUG_BINDS_GENE = 'drug_binds_gene'
# Hetionet Components — CTD
CTD_CHEM_INCREASES_EXPR = 'chemical_increases_expression'
CTD_CHEM_DECREASES_EXPR = 'chemical_decreases_expression'
# Hetionet Components — Bgee
BGEE_OVEREXPRESSES = 'bodypart_overexpresses_gene'
BGEE_UNDEREXPRESSES = 'bodypart_underexpresses_gene'
# Hetionet Components — Hetionet Precomputed
HETIO_GENE_INTERACTS = 'gene_interacts'
HETIO_GENE_COVARIES = 'gene_covaries'
HETIO_GENE_REGULATES = 'gene_regulates'

# AOPDB table mapping for MySQL queries
AOPDB_TABLE_MAPPING = {
    AOPDB_AOPS: 'aop_info',
    AOPDB_PATHWAYS: 'pathway_gene',
    AOPDB_GENE_PATHWAY_RELATIONSHIPS: 'pathway_gene',
    AOPDB_DRUGS: 'chemical_info',
}


ONTOLOGY_CONFIGS = {
    # =========================================================================
    # AOP-DB - Adverse Outcome Pathway Database
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
    # DisGeNET - Gene-Disease Associations (CVD-scoped via parser)
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
                'source_database': 'sourceDatabase',
            },
            'merge_column': {
                'source_column_name': 'cas_number',
                'data_property': 'xrefCasRN',
            },
        },
        'merge': True,
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
        'source_filename': f'{DOROTHEA_TF_GENE_INTERACTIONS}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'TranscriptionFactor',
            'subject_column_name': 'tf_symbol',
            'subject_match_property': 'TF',
            'object_node_type': 'Gene',
            'object_column_name': 'target_gene',
            'object_match_property': 'geneSymbol',
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
            'iri_column_name': 'trial_id',
            'data_property_map': {
                'trial_id': 'trialId',
                'title': 'commonName',
                'phase': 'phase',
                'status': 'status',
                'condition': 'condition',
                'intervention_name': 'interventionName',
                'source_database': 'sourceDatabase',
            },
        },
        'merge': False,
        'skip': False,
    },
    f'clinicaltrials.{CT_TRIAL_STUDIES_CONDITION}': {
        'data_type': 'relationship',
        'relationship_type': 'STUDIES_CONDITION',
        'source_filename': f'{CT_TRIAL_STUDIES_CONDITION}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'ClinicalTrial',
            'subject_column_name': 'trial_id',
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
        'source_filename': f'{CT_TRIAL_TESTS_INTERVENTION}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'ClinicalTrial',
            'subject_column_name': 'trial_id',
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
        'skip': False,
    },
    f'clinpgx.{CLINPGX_DRUG_LABELS}': {
        'data_type': 'node',
        'node_type': 'DrugLabel',
        'source_filename': f'{CLINPGX_DRUG_LABELS}.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'label_id',
            'data_property_map': {
                'label_id': 'labelId',
                'name': 'commonName',
                'drug': 'drug',
                'gene': 'gene',
                'source': 'regulatorySource',
                'biomarker_status': 'biomarkerStatus',
                'testing': 'testing',
                'alternate_drug_available': 'alternateDrugAvailable',
                'source_database': 'sourceDatabase',
            },
        },
        'merge': False,
        'skip': False,
    },
    f'clinpgx.{CLINPGX_CLINICAL_ANNOTATIONS}': {
        'data_type': 'relationship',
        'relationship_type': 'AFFECTS_RESPONSE_TO',
        'source_filename': f'{CLINPGX_CLINICAL_ANNOTATIONS}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Gene',
            'subject_column_name': 'gene',
            'subject_match_property': 'geneSymbol',
            'object_node_type': 'Drug',
            'object_column_name': 'drug',
            'object_match_property': 'commonName',
            'data_property_map': {
                'evidence_level': 'evidenceLevel',
                'annotation_id': 'annotationId',
                'variant': 'variant',
            },
        },
        'merge': False,
        'skip': False,
    },
    f'clinpgx.{CLINPGX_VARIANT_IN_GENE}': {
        'data_type': 'relationship',
        'relationship_type': 'VARIANT_IN',
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
        'skip': False,
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
                'name': 'commonName',
                'definition': 'definition',
            },
        },
        'merge': True,
        'skip': False,
    },
    f'disease_ontology.{DO_DISEASE_ANATOMY}': {
        'data_type': 'relationship',
        'relationship_type': 'diseaseLocalizesToAnatomy',
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
        'skip': False,
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
                'name': 'commonName',
                'definition': 'definition',
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
                'name': 'commonName',
                'tree_numbers': 'meshTreeNumber',
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
            'iri_column_name': 'umls_cui',
            'data_property_map': {
                'umls_cui': 'xrefUmlsCUI',
                'name': 'commonName',
                'source': 'sourceDatabase',
            },
        },
        'merge': False,
        'skip': False,
    },
    f'sider.{SIDER_COMPOUND_CAUSES_SE}': {
        'data_type': 'relationship',
        'relationship_type': 'compoundCausesSideEffect',
        'source_filename': f'{SIDER_COMPOUND_CAUSES_SE}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Drug',
            'subject_column_name': 'drugbank_id',
            'subject_match_property': 'xrefDrugbank',
            'object_node_type': 'SideEffect',
            'object_column_name': 'umls_cui',
            'object_match_property': 'xrefUmlsCUI',
        },
        'merge': False,
        'skip': False,
    },

    # ---- LINCS L1000 ----
    f'lincs.{LINCS_CUG}': {
        'data_type': 'relationship',
        'relationship_type': 'compoundUpregulatesGene',
        'source_filename': f'{LINCS_CUG}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Drug',
            'subject_column_name': 'drugbank_id',
            'subject_match_property': 'xrefDrugbank',
            'object_node_type': 'Gene',
            'object_column_name': 'entrez_gene_id',
            'object_match_property': 'xrefNcbiGene',
        },
        'merge': False,
        'skip': False,
    },
    f'lincs.{LINCS_CDG}': {
        'data_type': 'relationship',
        'relationship_type': 'compoundDownregulatesGene',
        'source_filename': f'{LINCS_CDG}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Drug',
            'subject_column_name': 'drugbank_id',
            'subject_match_property': 'xrefDrugbank',
            'object_node_type': 'Gene',
            'object_column_name': 'entrez_gene_id',
            'object_match_property': 'xrefNcbiGene',
        },
        'merge': False,
        'skip': False,
    },
    f'lincs.{LINCS_GRG}': {
        'data_type': 'relationship',
        'relationship_type': 'geneRegulatesGene',
        'source_filename': f'{LINCS_GRG}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Gene',
            'subject_column_name': 'source_gene',
            'subject_match_property': 'xrefNcbiGene',
            'object_node_type': 'Gene',
            'object_column_name': 'target_gene',
            'object_match_property': 'xrefNcbiGene',
        },
        'merge': False,
        'skip': False,
    },

    # ---- MEDLINE Co-occurrence ----
    f'medline.{MEDLINE_DPS}': {
        'data_type': 'relationship',
        'relationship_type': 'diseasePresentsSymptom',
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
        'skip': False,
    },
    f'medline.{MEDLINE_DLA}': {
        'data_type': 'relationship',
        'relationship_type': 'diseaseLocalizesToAnatomy',
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
        'skip': False,
    },
    f'medline.{MEDLINE_DRD}': {
        'data_type': 'relationship',
        'relationship_type': 'diseaseResemblesDisease',
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
        'skip': False,
    },

    # ---- DrugCentral ----
    f'drugcentral.{DC_PHARMACOLOGIC_CLASSES}': {
        'data_type': 'node',
        'node_type': 'PharmacologicClass',
        'source_filename': f'{DC_PHARMACOLOGIC_CLASSES}.tsv',
        'parse_config': {
            'headers': True,
            'iri_column_name': 'class_id',
            'data_property_map': {
                'class_id': 'classId',
                'class_name': 'commonName',
                'class_type': 'classType',
                'source': 'sourceDatabase',
            },
        },
        'merge': False,
        'skip': False,
    },
    f'drugcentral.{DC_PCIC}': {
        'data_type': 'relationship',
        'relationship_type': 'pharmacologicClassIncludesCompound',
        'inverse_relationship_type': 'compoundInPharmacologicClass',
        'source_filename': f'{DC_PCIC}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'PharmacologicClass',
            'subject_column_name': 'class_id',
            'subject_match_property': 'classId',
            'object_node_type': 'Drug',
            'object_column_name': 'drugbank_id',
            'object_match_property': 'xrefDrugbank',
        },
        'merge': False,
        'skip': False,
    },
    f'drugcentral.{DC_DRUG_TREATS}': {
        'data_type': 'relationship',
        'relationship_type': 'drugTreatsDisease',
        'source_filename': f'{DC_DRUG_TREATS}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Drug',
            'subject_column_name': 'struct_id',
            'subject_match_property': 'xrefDrugCentralStruct',
            'object_node_type': 'Disease',
            'object_column_name': 'umls_cui',
            'object_match_property': 'xrefUmlsCUI',
        },
        'merge': False,
        'skip': False,
    },
    f'drugcentral.{DC_DRUG_PALLIATES}': {
        'data_type': 'relationship',
        'relationship_type': 'drugPalliatesDisease',
        'source_filename': f'{DC_DRUG_PALLIATES}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Drug',
            'subject_column_name': 'struct_id',
            'subject_match_property': 'xrefDrugCentralStruct',
            'object_node_type': 'Disease',
            'object_column_name': 'umls_cui',
            'object_match_property': 'xrefUmlsCUI',
        },
        'merge': False,
        'skip': False,
    },

    # ---- GWAS Catalog ----
    f'gwas.{GWAS_GENE_DISEASE}': {
        'data_type': 'relationship',
        'relationship_type': 'geneAssociatesWithDisease',
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
        'skip': False,
    },

    # ---- PubTator ----
    f'pubtator.{PUBTATOR_DD_COOCCURRENCE}': {
        'data_type': 'relationship',
        'relationship_type': 'diseaseAssociatesWithDisease',
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
        'skip': False,
    },
    f'pubtator.{PUBTATOR_GD_LITERATURE}': {
        'data_type': 'relationship',
        'relationship_type': 'geneAssociatesWithDisease',
        'source_filename': f'{PUBTATOR_GD_LITERATURE}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Gene',
            'subject_column_name': 'gene_id',
            'subject_match_property': 'xrefNcbiGene',
            'object_node_type': 'Disease',
            'object_column_name': 'disease_id',
            'object_match_property': 'xrefDiseaseOntology',
        },
        'merge': False,
        'skip': False,
    },

    # ---- BindingDB ----
    f'bindingdb.{BINDINGDB_DRUG_BINDS_GENE}': {
        'data_type': 'relationship',
        'relationship_type': 'chemicalBindsGene',
        'source_filename': f'{BINDINGDB_DRUG_BINDS_GENE}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Drug',
            'subject_column_name': 'drugbank_id',
            'subject_match_property': 'xrefDrugbank',
            'object_node_type': 'Gene',
            'object_column_name': 'uniprot_id',
            'object_match_property': 'xrefUniProt',
        },
        'merge': False,
        'skip': False,
    },

    # ---- CTD ----
    f'ctd.{CTD_CHEM_INCREASES_EXPR}': {
        'data_type': 'relationship',
        'relationship_type': 'chemicalIncreasesExpression',
        'source_filename': f'{CTD_CHEM_INCREASES_EXPR}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Drug',
            'subject_column_name': 'chemical_id',
            'subject_match_property': 'xrefMeSH',
            'object_node_type': 'Gene',
            'object_column_name': 'gene_symbol',
            'object_match_property': 'geneSymbol',
        },
        'merge': False,
        'skip': False,
    },
    f'ctd.{CTD_CHEM_DECREASES_EXPR}': {
        'data_type': 'relationship',
        'relationship_type': 'chemicalDecreasesExpression',
        'source_filename': f'{CTD_CHEM_DECREASES_EXPR}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Drug',
            'subject_column_name': 'chemical_id',
            'subject_match_property': 'xrefMeSH',
            'object_node_type': 'Gene',
            'object_column_name': 'gene_symbol',
            'object_match_property': 'geneSymbol',
        },
        'merge': False,
        'skip': False,
    },

    # ---- Bgee ----
    f'bgee.{BGEE_OVEREXPRESSES}': {
        'data_type': 'relationship',
        'relationship_type': 'bodyPartOverexpressesGene',
        'source_filename': f'{BGEE_OVEREXPRESSES}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'BodyPart',
            'subject_column_name': 'anatomy_id',
            'subject_match_property': 'xrefUberon',
            'object_node_type': 'Gene',
            'object_column_name': 'gene_id',
            'object_match_property': 'xrefEnsembl',
        },
        'merge': False,
        'skip': False,
    },
    f'bgee.{BGEE_UNDEREXPRESSES}': {
        'data_type': 'relationship',
        'relationship_type': 'bodyPartUnderexpressesGene',
        'source_filename': f'{BGEE_UNDEREXPRESSES}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'BodyPart',
            'subject_column_name': 'anatomy_id',
            'subject_match_property': 'xrefUberon',
            'object_node_type': 'Gene',
            'object_column_name': 'gene_id',
            'object_match_property': 'xrefEnsembl',
        },
        'merge': False,
        'skip': False,
    },

    # ---- Hetionet Precomputed ----
    f'hetionet_precomputed.{HETIO_GENE_INTERACTS}': {
        'data_type': 'relationship',
        'relationship_type': 'geneInteractsWithGene',
        'source_filename': f'{HETIO_GENE_INTERACTS}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Gene',
            'subject_column_name': 'gene1_symbol',
            'subject_match_property': 'geneSymbol',
            'object_node_type': 'Gene',
            'object_column_name': 'gene2_symbol',
            'object_match_property': 'geneSymbol',
        },
        'merge': False,
        'skip': False,
    },
    f'hetionet_precomputed.{HETIO_GENE_COVARIES}': {
        'data_type': 'relationship',
        'relationship_type': 'geneCovariesWithGene',
        'source_filename': f'{HETIO_GENE_COVARIES}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Gene',
            'subject_column_name': 'gene1_symbol',
            'subject_match_property': 'geneSymbol',
            'object_node_type': 'Gene',
            'object_column_name': 'gene2_symbol',
            'object_match_property': 'geneSymbol',
        },
        'merge': False,
        'skip': False,
    },
    f'hetionet_precomputed.{HETIO_GENE_REGULATES}': {
        'data_type': 'relationship',
        'relationship_type': 'geneRegulatesGene',
        'source_filename': f'{HETIO_GENE_REGULATES}.tsv',
        'parse_config': {
            'headers': True,
            'subject_node_type': 'Gene',
            'subject_column_name': 'gene1_symbol',
            'subject_match_property': 'geneSymbol',
            'object_node_type': 'Gene',
            'object_column_name': 'gene2_symbol',
            'object_match_property': 'geneSymbol',
        },
        'merge': False,
        'skip': False,
    },
}
