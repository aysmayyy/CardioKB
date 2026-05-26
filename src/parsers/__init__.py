"""
Data parsers for the knowledge graph.

This module contains parsers for various data sources used to populate the knowledge graph.
Each parser is responsible for downloading, parsing, and formatting data from
a specific source.
"""

from .base_parser import BaseParser

# ---- Phase 1: Template-based parsers ----
from .ncbigene_parser import NCBIGeneParser
from .drugbank_parser import DrugBankParser
from .disgenet_parser import DisGeNETParser
from .aopdb_parser import AOPDBParser
from .dorothea_parser import DoRothEAParser
from .collecttri_parser import CollectTRIParser
from .disease_ontology_parser import DiseaseOntologyParser
from .gene_ontology_parser import GeneOntologyParser
from .uberon_parser import UberonParser
from .mesh_parser import MeSHParser
from .drugcentral_parser import DrugCentralParser
from .bindingdb_parser import BindingDBParser
from .bgee_parser import BgeeParser
from .ctd_parser import CTDParser
from .medline_parser import MEDLINEParser
from .evolutionary_rate_covariation import EvolutionaryRateCovariationParser
from .reactome_parser import ReactomeParser
from .string_parser import StringParser

# ---- Phase 2: New parsers (written from scratch for CardioKB) ----
from .clinvar_parser import ClinVarParser
from .hpo_parser import HPOParser
from .hgnc_parser import HGNCFamiliesParser
from .pubtator_parser import PubTatorParser
from .jensen_tissues_parser import JensenTissuesParser
from .sider_parser import SIDERParser
from .clinicaltrials_parser import ClinicalTrialsParser
from .clinpgx_parser import ClinPGxParser
from .lincs_parser import LINCSParser
from .opentargets_parser import OpenTargetsParser

__all__ = [
    'BaseParser',
    # Phase 1
    'NCBIGeneParser',
    'DrugBankParser',
    'DisGeNETParser',
    'AOPDBParser',
    'DoRothEAParser',
    'CollectTRIParser',
    'DiseaseOntologyParser',
    'GeneOntologyParser',
    'UberonParser',
    'MeSHParser',
    'DrugCentralParser',
    'BindingDBParser',
    'BgeeParser',
    'CTDParser',
    'MEDLINEParser',
    'EvolutionaryRateCovariationParser',
    'ReactomeParser',
    'StringParser',
    # Phase 2
    'ClinVarParser',
    'HPOParser',
    'HGNCFamiliesParser',
    'PubTatorParser',
    'JensenTissuesParser',
    'SIDERParser',
    'ClinicalTrialsParser',
    'ClinPGxParser',
    'LINCSParser',
    'OpenTargetsParser',
]
