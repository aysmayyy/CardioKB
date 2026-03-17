"""
DiseaseQueryAgent -- comprehensive disease knowledge graph builder.

Extends the basic agent workflow with:
  - Pre-fetch coverage stats from Neo4j
  - ClinicalTrials.gov API v2 clinical trial fetching
  - Neo4j loading of trial nodes + STUDIES_CONDITION edges
  - Full subgraph stats in result

Usage:
    from src.disease_agent import DiseaseQueryAgent
    agent = DiseaseQueryAgent("lupus", on_progress=callback)
    result = agent.run()
"""

import logging
import os
import time
from pathlib import Path

import pandas as pd
import requests

from src.agent import (
    PROJECT_ROOT,
    _run_disgenet,
    _standardize_disease,
    _write_temp_filter,
    KNOWN_FILTERS,
    _query_subgraph_stats,
)

logger = logging.getLogger('cardiokb.disease_agent')

MAX_TRIAL_PAGES = 5
TRIALS_PAGE_SIZE = 100
TRIAL_REQUEST_DELAY = 1.2


class DiseaseQueryAgent:
    def __init__(self, disease_name: str, on_progress=None):
        self.disease_name = disease_name.strip()
        self.on_progress = on_progress
        self.canonical_key = None
        self.canonical_name = None
        self.search_terms = []

    def _emit(self, event: str, data: dict):
        if self.on_progress:
            self.on_progress(event, data)

    def run(self) -> dict:
        """Main orchestration -- returns result dict."""
        from src.utils import (
            check_disease_cache, add_to_disease_cache, add_alias_to_disease_cache,
        )

        user_input = self.disease_name
        logger.info(f"DiseaseQueryAgent: '{user_input}'")
        self._emit('status', {'phase': 'start', 'message': f"Processing '{user_input}'..."})

        # Phase 1: Cache check (raw input)
        self._emit('status', {'phase': 'cache_check', 'message': 'Checking disease cache...'})
        cached = check_disease_cache(user_input)
        if cached:
            logger.info(f"Cache hit (raw): {cached['disease_name']}")
            add_alias_to_disease_cache(cached['disease_name'], user_input)
            self._emit('status', {'phase': 'cache_hit', 'message': f"Found in cache: {cached['disease_name']}"})
            stats = _query_subgraph_stats(cached['disease_name'])
            return {
                'disease_key': cached['disease_name'],
                'canonical_name': cached.get('canonical_name', cached['disease_name']),
                'user_input': user_input,
                'cached': True,
                'cache_info': cached,
                'subgraph_stats': stats,
            }

        # Phase 2: Standardize via Claude
        self._emit('status', {'phase': 'standardize', 'message': 'Standardizing disease name via Claude...'})
        std = _standardize_disease(user_input)
        self.canonical_key = std['canonical_key']
        self.canonical_name = std['canonical_name']
        self.search_terms = std['search_terms']
        existing_filter = std['existing_filter']

        self._emit('status', {
            'phase': 'standardized',
            'message': f"Resolved to: {self.canonical_name}",
            'canonical_key': self.canonical_key,
            'canonical_name': self.canonical_name,
            'search_terms_count': len(self.search_terms),
            'existing_filter': existing_filter,
        })

        # Phase 3: Cache check (canonical)
        cached = check_disease_cache(self.canonical_key)
        if cached:
            logger.info(f"Cache hit (canonical): {self.canonical_key}")
            add_alias_to_disease_cache(self.canonical_key, user_input)
            self._emit('status', {'phase': 'cache_hit', 'message': f"Found in cache: {self.canonical_key}"})
            stats = _query_subgraph_stats(self.canonical_key)
            return {
                'disease_key': self.canonical_key,
                'canonical_name': self.canonical_name,
                'user_input': user_input,
                'cached': True,
                'cache_info': cached,
                'subgraph_stats': stats,
            }

        # Phase 4: Current coverage
        self._emit('status', {'phase': 'coverage', 'message': 'Querying current graph coverage...'})
        coverage = self._query_current_coverage()
        if coverage:
            self._emit('status', {
                'phase': 'coverage',
                'message': (
                    f"Current coverage: {coverage.get('genes', 0)} genes, "
                    f"{coverage.get('drugs', 0)} drugs, "
                    f"{coverage.get('trials', 0)} trials, "
                    f"{coverage.get('pathways', 0)} pathways"
                ),
                'coverage': coverage,
            })

        # Phase 5: DisGeNET fetch
        self._emit('status', {'phase': 'disgenet', 'message': f"Querying DisGeNET for '{self.canonical_name}'..."})

        if existing_filter:
            filter_path = str(PROJECT_ROOT / KNOWN_FILTERS[existing_filter])
            temp_filter = False
        else:
            filter_path = _write_temp_filter(self.search_terms)
            temp_filter = True

        try:
            disgenet_result = _run_disgenet(self.canonical_key, filter_path)
        finally:
            if temp_filter:
                try:
                    os.unlink(filter_path)
                except OSError:
                    pass

        gda_count = disgenet_result['gda_count']
        partial = disgenet_result['partial']

        self._emit('status', {
            'phase': 'disgenet_done',
            'message': f"DisGeNET: {gda_count} gene-disease associations"
                       f"{' (partial)' if partial else ''}",
            'gda_count': gda_count,
            'partial': partial,
        })

        # Phase 6: ClinicalTrials.gov API v2
        self._emit('status', {'phase': 'trials', 'message': f"Fetching clinical trials for '{self.canonical_name}'..."})
        trials_df = self._fetch_clinical_trials()
        trials_loaded = 0
        if trials_df is not None and len(trials_df) > 0:
            self._emit('status', {
                'phase': 'loading',
                'message': f"Loading {len(trials_df)} clinical trials into Neo4j...",
            })
            trials_loaded = self._load_trials_to_neo4j(trials_df)

        self._emit('status', {
            'phase': 'trials_done',
            'message': f"Clinical trials: {trials_loaded} loaded into Neo4j",
            'trials_loaded': trials_loaded,
        })

        # Phase 7: Cache + stats
        if gda_count > 0 or trials_loaded > 0:
            self._emit('status', {'phase': 'caching', 'message': 'Caching results...'})
            aliases = [user_input.lower()]
            if self.canonical_name.lower() != user_input.lower():
                aliases.append(self.canonical_name.lower())
            if self.canonical_key != user_input.lower():
                aliases.append(self.canonical_key)

            sources = []
            if gda_count > 0:
                sources.append('DisGeNET')
            if trials_loaded > 0:
                sources.append('ClinicalTrials.gov')

            add_to_disease_cache(self.canonical_key, {
                'canonical_name': self.canonical_name,
                'filter_file': f'agent:{self.canonical_key}',
                'disgenet_rows': gda_count,
                'trials_loaded': trials_loaded,
                'sources_loaded': sources,
                'aliases': aliases,
            })
        else:
            self._emit('status', {
                'phase': 'error',
                'message': f"No data found for '{self.canonical_name}'. Try a different disease name.",
            })
            return {
                'disease_key': self.canonical_key,
                'canonical_name': self.canonical_name,
                'user_input': user_input,
                'cached': False,
                'error': f"No data found for '{self.canonical_name}'",
                'subgraph_stats': {},
            }

        self._emit('status', {'phase': 'stats', 'message': 'Querying subgraph statistics...'})
        stats = _query_subgraph_stats(self.canonical_key)

        result = {
            'disease_key': self.canonical_key,
            'canonical_name': self.canonical_name,
            'user_input': user_input,
            'cached': False,
            'partial': partial,
            'search_terms_count': len(self.search_terms),
            'disgenet_edges_loaded': gda_count,
            'trials_loaded': trials_loaded,
            'subgraph_stats': stats,
        }

        self._emit('status', {'phase': 'complete', 'message': 'Done.'})
        logger.info(f"DiseaseQueryAgent complete: {result}")
        return result

    def _query_current_coverage(self) -> dict:
        """Query Neo4j for existing coverage of this disease."""
        from src.utils import _get_neo4j_driver

        driver = _get_neo4j_driver()
        if not driver:
            return {}

        search = self.canonical_name or self.disease_name
        try:
            with driver.session(database='neo4j') as s:
                rec = s.run(
                    "MATCH (d:Disease) "
                    "WHERE toLower(d.commonName) CONTAINS toLower($name) "
                    "OPTIONAL MATCH (d)--(g:Gene) "
                    "OPTIONAL MATCH (d)--(dr:Drug) "
                    "OPTIONAL MATCH (d)--(t:ClinicalTrial) "
                    "OPTIONAL MATCH (d)--(p:Pathway) "
                    "RETURN count(DISTINCT d) AS diseases, "
                    "       count(DISTINCT g) AS genes, "
                    "       count(DISTINCT dr) AS drugs, "
                    "       count(DISTINCT t) AS trials, "
                    "       count(DISTINCT p) AS pathways",
                    name=search,
                ).single()
                if rec:
                    return {
                        'diseases': rec['diseases'],
                        'genes': rec['genes'],
                        'drugs': rec['drugs'],
                        'trials': rec['trials'],
                        'pathways': rec['pathways'],
                    }
        except Exception as e:
            logger.warning(f"Coverage query failed: {e}")
        finally:
            driver.close()
        return {}

    def _fetch_clinical_trials(self) -> pd.DataFrame | None:
        """Fetch clinical trials from ClinicalTrials.gov API v2."""
        search_term = self.canonical_name or self.disease_name
        base_url = 'https://clinicaltrials.gov/api/v2/studies'

        all_rows = []
        next_token = None

        for page in range(MAX_TRIAL_PAGES):
            params = {
                'query.cond': search_term,
                'pageSize': TRIALS_PAGE_SIZE,
                'format': 'json',
            }
            if next_token:
                params['pageToken'] = next_token

            try:
                resp = requests.get(base_url, params=params, timeout=30)

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get('Retry-After', 5))
                    logger.warning(f"Rate limited, waiting {retry_after}s...")
                    time.sleep(retry_after)
                    resp = requests.get(base_url, params=params, timeout=30)

                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.warning(f"ClinicalTrials API error (page {page}): {e}")
                break

            studies = data.get('studies', [])
            if not studies:
                break

            for study in studies:
                ps = study.get('protocolSection', {})
                id_mod = ps.get('identificationModule', {})
                status_mod = ps.get('statusModule', {})
                design_mod = ps.get('designModule', {})
                cond_mod = ps.get('conditionsModule', {})
                arms_mod = ps.get('armsInterventionsModule', {})

                trial_id = id_mod.get('nctId', '')
                title = id_mod.get('briefTitle', '')
                status = status_mod.get('overallStatus', '')
                phases = design_mod.get('phases', [])
                phase = phases[0] if phases else ''
                conditions = cond_mod.get('conditions', [])
                interventions = arms_mod.get('interventions', [])

                condition_str = '; '.join(conditions[:5]) if conditions else ''

                if interventions:
                    for intv in interventions[:3]:
                        all_rows.append({
                            'trial_id': trial_id,
                            'title': title,
                            'phase': phase,
                            'status': status,
                            'condition': condition_str,
                            'intervention_name': intv.get('name', ''),
                            'source_database': 'ClinicalTrials.gov',
                        })
                else:
                    all_rows.append({
                        'trial_id': trial_id,
                        'title': title,
                        'phase': phase,
                        'status': status,
                        'condition': condition_str,
                        'intervention_name': '',
                        'source_database': 'ClinicalTrials.gov',
                    })

            next_token = data.get('nextPageToken')
            if not next_token:
                break

            if page < MAX_TRIAL_PAGES - 1:
                time.sleep(TRIAL_REQUEST_DELAY)

        if not all_rows:
            logger.info("No clinical trials found")
            return None

        df = pd.DataFrame(all_rows).drop_duplicates(subset=['trial_id', 'intervention_name'])
        logger.info(f"Fetched {len(df)} clinical trial rows ({df['trial_id'].nunique()} unique trials)")
        return df

    def _load_trials_to_neo4j(self, trials_df: pd.DataFrame) -> int:
        """Save trial TSVs and load into Neo4j via ontology configs."""
        from src.neo4j_loader import Neo4jLoader
        from src.ontology_configs import ONTOLOGY_CONFIGS

        out_dir = PROJECT_ROOT / 'data' / 'processed' / 'clinicaltrials_agent'
        out_dir.mkdir(parents=True, exist_ok=True)

        # Node TSV: deduplicated by trial_id
        node_df = trials_df.drop_duplicates(subset=['trial_id'])
        node_df.to_csv(out_dir / 'clinical_trials.tsv', sep='\t', index=False)

        # Relationship TSV: trial_id + condition (for STUDIES_CONDITION)
        rel_rows = []
        for _, row in trials_df.iterrows():
            conditions = str(row.get('condition', '')).split('; ')
            for cond in conditions:
                cond = cond.strip()
                if cond:
                    rel_rows.append({
                        'trial_id': row['trial_id'],
                        'condition': cond,
                    })
        rel_df = pd.DataFrame(rel_rows).drop_duplicates() if rel_rows else pd.DataFrame()
        rel_df.to_csv(out_dir / 'trial_studies_condition.tsv', sep='\t', index=False)

        uri = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
        username = os.getenv('NEO4J_USERNAME', 'neo4j')
        password = os.getenv('NEO4J_PASSWORD', '')
        if not password:
            logger.error("NEO4J_PASSWORD not set, skipping trial load")
            return 0

        node_config = ONTOLOGY_CONFIGS.get('clinicaltrials.clinical_trials')
        rel_config = ONTOLOGY_CONFIGS.get('clinicaltrials.trial_studies_condition')

        loaded = 0
        try:
            with Neo4jLoader(uri, username, password) as loader:
                if node_config and len(node_df) > 0:
                    # Use merge to avoid duplicates with existing trials
                    merge_config = dict(node_config)
                    merge_config['merge'] = True
                    loader._load_nodes(node_df, merge_config, 'clinicaltrials.clinical_trials')
                    loaded = len(node_df)
                    logger.info(f"Loaded {loaded} ClinicalTrial nodes")

                if rel_config and len(rel_df) > 0:
                    merge_rel = dict(rel_config)
                    merge_rel['merge'] = True
                    loader._load_relationships(rel_df, merge_rel, 'clinicaltrials.trial_studies_condition')
                    logger.info(f"Loaded {len(rel_df)} STUDIES_CONDITION edges")
        except Exception as e:
            logger.error(f"Trial Neo4j load failed: {e}")

        return loaded
