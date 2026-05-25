"""
Neo4jLoader: Direct Cypher-based graph loader for CardioKB.

Replaces AlzKB's ista/RDF/Memgraph pathway with direct Neo4j loading
using the official neo4j Python driver and UNWIND-based batch operations.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

import pandas as pd

try:
    from neo4j import GraphDatabase
except ImportError:
    GraphDatabase = None

logger = logging.getLogger(__name__)

BATCH_SIZE = 5000


class Neo4jLoader:
    """
    Loads parsed DataFrames into Neo4j using Cypher queries.

    Driven by ONTOLOGY_CONFIGS: iterates configs, loads nodes first,
    then relationships, using MERGE or CREATE as specified.
    """

    def __init__(self, uri: str, username: str, password: str,
                 database: str = ""):
        """
        Initialize Neo4j connection.

        Args:
            uri: Bolt URI (e.g., bolt://localhost:7687)
            username: Database username
            password: Database password
            database: Database name (unused for Memgraph, kept for API compat)
        """
        if GraphDatabase is None:
            raise ImportError(
                "neo4j package is required for Neo4jLoader. "
                "Install with: pip install neo4j"
            )

        self.uri = uri
        self.username = username
        self.password = password
        self.database = database
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
        self.stats = {
            'nodes_created': 0,
            'nodes_merged': 0,
            'relationships_created': 0,
            'relationships_merged': 0,
            'errors': [],
        }

        # Verify connectivity
        try:
            self.driver.verify_connectivity()
            logger.info(f"Connected to Neo4j at {uri}")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j at {uri}: {e}")
            raise

    def close(self):
        """Close the Neo4j driver."""
        if self.driver:
            self.driver.close()
            logger.info("Neo4j connection closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # -------------------------------------------------------------------------
    # Schema setup
    # -------------------------------------------------------------------------

    def setup_constraints(self, ontology_configs: Dict[str, Dict]):
        """
        Create uniqueness constraints for each node type's IRI column.

        Args:
            ontology_configs: The ONTOLOGY_CONFIGS dictionary.
        """
        logger.info("Setting up uniqueness constraints...")
        seen = set()

        for config_key, config in ontology_configs.items():
            if config.get('data_type') != 'node' or config.get('skip'):
                continue

            node_type = config['node_type']
            iri_col = config['parse_config'].get('iri_column_name', '')
            prop_map = config['parse_config'].get('data_property_map', {})

            # Map the IRI column to its database property name
            db_prop = prop_map.get(iri_col, iri_col)
            key = (node_type, db_prop)
            if key in seen:
                continue
            seen.add(key)

            query = (
                f"CREATE CONSTRAINT ON (n:{node_type}) "
                f"ASSERT n.{db_prop} IS UNIQUE"
            )
            try:
                with self.driver.session() as session:
                    session.run(query)
                logger.info(f"  Constraint: {node_type}.{db_prop}")
            except Exception as e:
                logger.warning(f"  Failed constraint {node_type}.{db_prop}: {e}")

    def setup_indexes(self, ontology_configs: Dict[str, Dict]):
        """
        Create indexes on match_property fields used in relationships.

        Args:
            ontology_configs: The ONTOLOGY_CONFIGS dictionary.
        """
        logger.info("Setting up indexes...")
        seen = set()

        for config_key, config in ontology_configs.items():
            if config.get('data_type') != 'relationship' or config.get('skip'):
                continue

            pc = config['parse_config']
            for prefix in ('subject', 'object'):
                node_type = pc.get(f'{prefix}_node_type', '')
                match_prop = pc.get(f'{prefix}_match_property', '')
                key = (node_type, match_prop)
                if key in seen or not node_type or not match_prop:
                    continue
                seen.add(key)

                query = f"CREATE INDEX ON :{node_type}({match_prop})"
                try:
                    with self.driver.session() as session:
                        session.run(query)
                    logger.info(f"  Index: {node_type}.{match_prop}")
                except Exception as e:
                    logger.warning(f"  Failed index {node_type}.{match_prop}: {e}")

    # -------------------------------------------------------------------------
    # Main loading entry point
    # -------------------------------------------------------------------------

    def load_from_configs(self, parsed_data: Dict[str, Dict[str, pd.DataFrame]],
                          ontology_configs: Dict[str, Dict],
                          processed_dir: Optional[Path] = None):
        """
        Load all data into Neo4j using ontology configs.

        Two passes: nodes first, then relationships.

        Args:
            parsed_data: {source_name: {data_name: DataFrame}}
            ontology_configs: The ONTOLOGY_CONFIGS dictionary.
            processed_dir: Directory containing TSV files (fallback if DataFrame not in parsed_data).
        """
        # Pass 1: nodes
        logger.info("=" * 60)
        logger.info("Pass 1: Loading nodes")
        logger.info("=" * 60)
        for config_key, config in ontology_configs.items():
            if config.get('data_type') != 'node' or config.get('skip'):
                continue
            df = self._resolve_dataframe(config_key, parsed_data, processed_dir, config)
            if df is not None and len(df) > 0:
                self._load_nodes(df, config, config_key)

        # Pass 2: relationships
        logger.info("=" * 60)
        logger.info("Pass 2: Loading relationships")
        logger.info("=" * 60)
        for config_key, config in ontology_configs.items():
            if config.get('data_type') != 'relationship' or config.get('skip'):
                continue
            df = self._resolve_dataframe(config_key, parsed_data, processed_dir, config)
            if df is not None and len(df) > 0:
                self._load_relationships(df, config, config_key)

    def _resolve_dataframe(self, config_key: str,
                           parsed_data: Dict[str, Dict[str, pd.DataFrame]],
                           processed_dir: Optional[Path],
                           config: Dict) -> Optional[pd.DataFrame]:
        """
        Resolve a DataFrame from parsed_data or fall back to TSV file.
        """
        source_name, data_name = config_key.split('.', 1)

        # Try parsed_data first
        if source_name in parsed_data and data_name in parsed_data[source_name]:
            return parsed_data[source_name][data_name]

        # Fall back to TSV file
        if processed_dir:
            tsv_path = processed_dir / source_name / config['source_filename']
            if tsv_path.exists():
                try:
                    return pd.read_csv(tsv_path, sep='\t', dtype=str, keep_default_na=False, na_values=[''])
                except Exception as e:
                    logger.warning(f"Failed to read {tsv_path}: {e}")

        logger.debug(f"No data found for {config_key}")
        return None

    # -------------------------------------------------------------------------
    # Node loading
    # -------------------------------------------------------------------------

    def _load_nodes(self, df: pd.DataFrame, config: Dict, config_key: str):
        """
        Load nodes from a DataFrame using UNWIND + MERGE or CREATE.

        Args:
            df: DataFrame of node data.
            config: Ontology config entry.
            config_key: Config key for logging.
        """
        node_type = config['node_type']
        pc = config['parse_config']
        merge = config.get('merge', False)
        use_create = config.get('use_create', False)  # Use CREATE instead of MERGE for unique datasets
        iri_col = pc.get('iri_column_name', '')
        prop_map = pc.get('data_property_map', {})

        # Filter if needed
        df = self._apply_filter(df, pc)

        # Filter out rows where IRI column is null (can't MERGE on null)
        if iri_col and iri_col in df.columns:
            before_count = len(df)
            df = df[df[iri_col].notna() & (df[iri_col] != '')].copy()
            dropped = before_count - len(df)
            if dropped > 0:
                logger.info(f"    Dropped {dropped} rows with null IRI ({iri_col})")

        # Deduplicate by IRI column, keeping row with most non-null values
        if iri_col and iri_col in df.columns:
            before_count = len(df)
            df['_completeness'] = df.notna().sum(axis=1)
            df = df.sort_values('_completeness', ascending=False).drop_duplicates(subset=[iri_col], keep='first')
            df = df.drop(columns=['_completeness'])
            deduped = before_count - len(df)
            if deduped > 0:
                logger.info(f"    Deduplicated {deduped} rows by {iri_col}")

        # Map IRI column to Neo4j property
        iri_prop = prop_map.get(iri_col, iri_col)

        # Build SET clause for properties
        set_clauses = []
        source_cols = []
        for src_col, neo4j_prop in prop_map.items():
            if src_col in df.columns:
                set_clauses.append(f"n.{neo4j_prop} = row.{src_col}")
                source_cols.append(src_col)

        set_str = ', '.join(set_clauses) if set_clauses else ''

        if use_create:
            # CREATE directly — faster for large unique datasets (e.g., ClinVar variants)
            if iri_col not in df.columns:
                logger.warning(f"IRI column '{iri_col}' not in DataFrame for {config_key}")
                return

            # Build property assignments for CREATE
            create_props = [f"{iri_prop}: row.{iri_col}"]
            for src_col, neo4j_prop in prop_map.items():
                if src_col in df.columns and src_col != iri_col:
                    create_props.append(f"{neo4j_prop}: row.{src_col}")
            props_str = ', '.join(create_props)

            query = (
                f"UNWIND $rows AS row "
                f"CREATE (n:{node_type} {{{props_str}}})"
            )
            logger.info(f"    Using CREATE (fast path) for {node_type}")
        elif merge:
            # MERGE on IRI property, then SET all other properties
            if iri_col not in df.columns:
                logger.warning(f"IRI column '{iri_col}' not in DataFrame for {config_key}")
                return

            merge_prop = iri_prop
            query = (
                f"UNWIND $rows AS row "
                f"MERGE (n:{node_type} {{{merge_prop}: row.{iri_col}}}) "
            )
            if set_str:
                query += f"SET {set_str}"

            # Handle merge_column (additional property to merge on)
            merge_col_config = pc.get('merge_column')
            if merge_col_config:
                src_col = merge_col_config.get('source_column_name', '')
                data_prop = merge_col_config.get('data_property', '')
                if src_col in df.columns and data_prop:
                    if set_str:
                        query += f", n.{data_prop} = row.{src_col}"
                    else:
                        query += f"SET n.{data_prop} = row.{src_col}"
        else:
            # MERGE on IRI property (to avoid duplicates), SET properties
            if iri_col not in df.columns:
                logger.warning(f"IRI column '{iri_col}' not in DataFrame for {config_key}")
                return

            query = (
                f"UNWIND $rows AS row "
                f"MERGE (n:{node_type} {{{iri_prop}: row.{iri_col}}}) "
            )
            if set_str:
                query += f"ON CREATE SET {set_str} "
                query += f"ON MATCH SET {set_str}"

        # Prepare rows, converting NaN to None
        rows = df[list(set(col for col in df.columns if col in
                          [iri_col] + source_cols +
                          [pc.get('merge_column', {}).get('source_column_name', '')]))].copy()
        # Coerce IRI column to string — Neo4j MERGE requires exact type matching,
        # and IDs must be consistently typed across node creation and relationship
        # matching. String is the universal safe type for identifiers.
        if iri_col in rows.columns:
            rows[iri_col] = rows[iri_col].apply(
                lambda x: str(int(x)) if isinstance(x, float) and pd.notna(x) and x == int(x)
                else str(x) if pd.notna(x) else None
            )
        rows = rows.where(pd.notna(rows), None)
        row_dicts = rows.to_dict('records')

        result = self._execute_batch(query, row_dicts)
        action = "merged" if merge else "created/merged"
        created = result['nodes_created']
        logger.info(
            f"  {config_key}: {action} {result['rows_sent']} {node_type} nodes "
            f"({created} new)"
        )

        if merge:
            self.stats['nodes_merged'] += result['rows_sent']
        else:
            self.stats['nodes_created'] += result['rows_sent']

    # -------------------------------------------------------------------------
    # Relationship loading
    # -------------------------------------------------------------------------

    def _load_relationships(self, df: pd.DataFrame, config: Dict, config_key: str):
        """
        Load relationships from a DataFrame.

        MATCH subject, MATCH object, MERGE relationship.

        Args:
            df: DataFrame of relationship data.
            config: Ontology config entry.
            config_key: Config key for logging.
        """
        pc = config['parse_config']
        rel_type = config['relationship_type']
        inverse_rel_type = config.get('inverse_relationship_type')
        use_create = config.get('use_create', False)

        subj_node_type = pc['subject_node_type']
        subj_col = pc['subject_column_name']
        subj_match_prop = pc['subject_match_property']

        obj_node_type = pc['object_node_type']
        obj_col = pc['object_column_name']
        obj_match_prop = pc['object_match_property']

        # Filter if needed
        df = self._apply_filter(df, pc)

        if subj_col not in df.columns or obj_col not in df.columns:
            logger.warning(
                f"Missing columns for {config_key}: "
                f"need '{subj_col}' and '{obj_col}', "
                f"have {list(df.columns)}"
            )
            return

        # Build relationship properties SET clause
        rel_prop_map = pc.get('data_property_map', {})
        rel_set_parts = []
        rel_cols = []
        for src_col, neo4j_prop in rel_prop_map.items():
            if src_col in df.columns:
                rel_set_parts.append(f"r.{neo4j_prop} = row.{src_col}")
                rel_cols.append(src_col)
        rel_set_str = ', '.join(rel_set_parts)

        # Source label (set once per config, not per row)
        source_label = config.get('source_label')
        if not source_label:
            logger.warning(
                f"  {config_key}: missing 'source_label' in config — "
                f"relationships will not have r.source set"
            )

        # Type-aware matching: wrap row values with toInteger() when the
        # target property is stored as an integer in Neo4j.  Config can set
        # 'subject_match_type' / 'object_match_type' to 'integer'.
        subj_match_type = pc.get('subject_match_type')
        obj_match_type = pc.get('object_match_type')

        def _match_expr(col, match_type):
            if match_type == 'integer':
                return f"toInteger(row.{col})"
            return f"row.{col}"

        subj_expr = _match_expr(subj_col, subj_match_type)
        obj_expr = _match_expr(obj_col, obj_match_type)

        # Forward relationship query
        rel_verb = "CREATE" if use_create else "MERGE"
        query = (
            f"UNWIND $rows AS row "
            f"MATCH (s:{subj_node_type} {{{subj_match_prop}: {subj_expr}}}) "
            f"MATCH (o:{obj_node_type} {{{obj_match_prop}: {obj_expr}}}) "
            f"{rel_verb} (s)-[r:{rel_type}]->(o) "
        )
        # Build SET clause: source label + any data properties
        set_parts = []
        if source_label:
            set_parts.append("r.source = $source_label")
        if rel_set_str:
            set_parts.append(rel_set_str)
        if set_parts:
            query += f"SET {', '.join(set_parts)}"

        # Prepare rows
        needed_cols = list(set([subj_col, obj_col] + rel_cols))
        needed_cols = [c for c in needed_cols if c in df.columns]
        rows = df[needed_cols].copy()
        # Handle NaN → None
        rows = rows.where(pd.notna(rows), None)
        # Coerce match columns to string — IRI/ID columns are stored as strings
        # by the node loader (see _load_nodes), so relationship match columns must
        # also be strings for Neo4j MERGE to find exact type matches.  The previous
        # approach (sampling one existing node) broke when mixed sources stored the
        # same property as different types (e.g., ClinPGx Variant variantId=str vs
        # ClinVar variantId=int).
        for col in (subj_col, obj_col):
            if col not in rows.columns:
                continue
            rows[col] = rows[col].apply(
                lambda x: str(int(x)) if isinstance(x, float) and pd.notna(x) and x == int(x)
                else str(x) if pd.notna(x) and x is not None
                else None
            )
        row_dicts = rows.to_dict('records')

        result = self._execute_batch(query, row_dicts, source_label=source_label)
        created = result['relationships_created']
        props_set = result['properties_set']
        sent = result['rows_sent']
        # Distinguish "existing" (MERGE matched) from "skipped" (MATCH found no
        # endpoint nodes).  When MERGE hits an existing rel it still sets properties,
        # so props_set > 0 indicates real merges.  When MATCH fails, no SET runs and
        # both created and props_set are 0.
        if created == 0 and props_set == 0 and sent > 0:
            logger.warning(
                f"  {config_key}: {sent} rows -> 0 relationships created "
                f"(endpoint MATCH likely failed — check ID types/values for "
                f"{subj_node_type}.{subj_match_prop} and {obj_node_type}.{obj_match_prop})"
            )
        else:
            matched = sent - created if sent > created else 0
            logger.info(
                f"  {config_key}: {sent} rows -> {created} new + "
                f"{matched} existing {rel_type} relationships"
            )
        self.stats['relationships_merged'] += created

        # Inverse relationship
        if inverse_rel_type:
            inv_query = (
                f"UNWIND $rows AS row "
                f"MATCH (s:{subj_node_type} {{{subj_match_prop}: {subj_expr}}}) "
                f"MATCH (o:{obj_node_type} {{{obj_match_prop}: {obj_expr}}}) "
                f"{rel_verb} (o)-[r:{inverse_rel_type}]->(s) "
            )
            inv_set_parts = []
            if source_label:
                inv_set_parts.append("r.source = $source_label")
            if rel_set_str:
                inv_set_parts.append(rel_set_str)
            if inv_set_parts:
                inv_query += f"SET {', '.join(inv_set_parts)}"

            inv_result = self._execute_batch(inv_query, row_dicts, source_label=source_label)
            inv_created = inv_result['relationships_created']
            inv_props = inv_result['properties_set']
            inv_sent = inv_result['rows_sent']
            if inv_created == 0 and inv_props == 0 and inv_sent > 0:
                logger.warning(
                    f"  {config_key}: {inv_sent} rows -> 0 inverse relationships created "
                    f"(endpoint MATCH likely failed)"
                )
            else:
                inv_matched = inv_sent - inv_created if inv_sent > inv_created else 0
                logger.info(
                    f"  {config_key}: {inv_sent} rows -> {inv_created} new + "
                    f"{inv_matched} existing {inverse_rel_type} (inverse) relationships"
                )
            self.stats['relationships_merged'] += inv_created

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _sample_property_type(self, node_type: str, property_name: str) -> str:
        """Sample one existing node to determine the Python type of a Neo4j property.

        Returns 'str', 'int', or 'unknown'.
        """
        cache_key = (node_type, property_name)
        if not hasattr(self, '_prop_type_cache'):
            self._prop_type_cache = {}
        if cache_key in self._prop_type_cache:
            return self._prop_type_cache[cache_key]

        result = 'unknown'
        try:
            with self.driver.session() as session:
                rec = session.run(
                    f"MATCH (n:{node_type}) WHERE n.{property_name} IS NOT NULL "
                    f"RETURN n.{property_name} AS v LIMIT 1"
                ).single()
                if rec is not None:
                    v = rec['v']
                    if isinstance(v, str):
                        result = 'str'
                    elif isinstance(v, int):
                        result = 'int'
        except Exception:
            pass

        self._prop_type_cache[cache_key] = result
        return result

    def _apply_filter(self, df: pd.DataFrame, parse_config: Dict) -> pd.DataFrame:
        """Apply filter_column/filter_value pre-filtering."""
        filter_col = parse_config.get('filter_column')
        filter_val = parse_config.get('filter_value')

        if filter_col and filter_val is not None and filter_col in df.columns:
            # filter_value='0' means exclude rows where column equals '0' or is empty
            if filter_val == '0':
                df = df[df[filter_col].notna() & (df[filter_col].astype(str) != '0')
                        & (df[filter_col].astype(str) != '')].copy()
            else:
                df = df[df[filter_col].astype(str) == str(filter_val)].copy()

        return df

    def _execute_batch(self, query: str, rows: List[Dict[str, Any]],
                       source_label: Optional[str] = None) -> dict:
        """
        Execute a Cypher query in batches using UNWIND.

        Args:
            query: Cypher query with $rows parameter.
            rows: List of row dictionaries.
            source_label: Optional source label passed as a top-level Cypher parameter.

        Returns:
            Dict with 'rows_sent', 'relationships_created', 'nodes_created',
            'properties_set' counts from Neo4j counters.
        """
        totals = {
            'rows_sent': 0,
            'relationships_created': 0,
            'nodes_created': 0,
            'properties_set': 0,
        }
        params: Dict[str, Any] = {}
        if source_label:
            params['source_label'] = source_label

        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i:i + BATCH_SIZE]
            with self.driver.session() as session:
                try:
                    result = session.run(query, rows=batch, **params)
                    summary = result.consume()
                    totals['rows_sent'] += len(batch)
                    totals['relationships_created'] += summary.counters.relationships_created
                    totals['nodes_created'] += summary.counters.nodes_created
                    totals['properties_set'] += summary.counters.properties_set
                except Exception as e:
                    logger.error(f"Batch error at offset {i}: {e}")
                    self.stats['errors'].append(str(e))

        return totals

    # -------------------------------------------------------------------------
    # Custom loaders (source-specific logic beyond config system)
    # -------------------------------------------------------------------------

    def load_disgenet_diseases(self, diseases_df: pd.DataFrame) -> Dict[str, int]:
        """
        Load DisGeNET diseases with DOID-aware merging.

        For diseases WITH a DOID mapping: matches the existing Disease
        Ontology node by xrefDiseaseOntology and enriches it with xrefUmlsCUI.
        For diseases WITHOUT a DOID mapping: creates a new Disease node
        keyed by xrefUmlsCUI.

        Args:
            diseases_df: DataFrame with columns diseaseId, diseaseName, DO,
                         sourceDatabase.

        Returns:
            Dict with counts: enriched, created.
        """
        import pandas as pd

        counts = {'enriched': 0, 'created': 0}

        # Split: diseases with DOID vs without
        has_doid = diseases_df[
            diseases_df['DO'].notna() &
            (diseases_df['DO'] != '') &
            (diseases_df['DO'] != '0')
        ].copy()

        no_doid = diseases_df[
            ~diseases_df['diseaseId'].isin(has_doid['diseaseId'])
        ].copy()

        logger.info(f"  DisGeNET diseases: {len(has_doid)} with DOID, {len(no_doid)} without")

        # Pass 1: Enrich existing Disease Ontology nodes by DOID
        if len(has_doid) > 0:
            has_doid = has_doid.where(pd.notna(has_doid), None)
            rows_doid = has_doid[['diseaseId', 'diseaseName', 'DO']].to_dict('records')

            query_enrich = (
                "UNWIND $rows AS row "
                "MATCH (d:Disease {xrefDiseaseOntology: row.DO}) "
                "SET d.xrefUmlsCUI = row.diseaseId"
            )
            enrich_result = self._execute_batch(query_enrich, rows_doid)
            counts['enriched'] = enrich_result['rows_sent']
            self.stats['nodes_merged'] += counts['enriched']
            logger.info(f"  disgenet.diseases: enriched {counts['enriched']} existing Disease nodes with xrefUmlsCUI")

        # Pass 2: Create new Disease nodes for those without DOID match
        if len(no_doid) > 0:
            no_doid = no_doid.where(pd.notna(no_doid), None)
            rows_new = no_doid[['diseaseId', 'diseaseName']].to_dict('records')

            query_create = (
                "UNWIND $rows AS row "
                "MERGE (d:Disease {xrefUmlsCUI: row.diseaseId}) "
                "ON CREATE SET d.commonName = row.diseaseName, "
                "d.sourceDatabase = 'DisGeNET'"
            )
            create_result = self._execute_batch(query_create, rows_new)
            counts['created'] = create_result['nodes_created']
            self.stats['nodes_created'] += counts['created']
            logger.info(f"  disgenet.diseases: created {counts['created']} new Disease nodes")

        return counts

    # -------------------------------------------------------------------------
    # Verification
    # -------------------------------------------------------------------------

    def verify_graph(self) -> Dict[str, Any]:
        """
        Verify graph contents with node/relationship counts.

        Returns:
            Dictionary with verification results.
        """
        results = {'node_counts': {}, 'relationship_counts': {}, 'total_nodes': 0, 'total_relationships': 0}

        with self.driver.session() as session:
            # Node counts by label
            labels_result = session.run(
                "MATCH (n) RETURN DISTINCT labels(n) AS l"
            )
            for record in labels_result:
                label = record['l'][0] if record['l'] else None
                if not label:
                    continue
                count_result = session.run(f"MATCH (n:{label}) RETURN count(n) as cnt")
                cnt = count_result.single()['cnt']
                results['node_counts'][label] = cnt
                results['total_nodes'] += cnt

            # Relationship counts by type
            rel_types_result = session.run(
                "MATCH ()-[r]->() RETURN DISTINCT type(r) AS rt"
            )
            for record in rel_types_result:
                rel_type = record['rt']
                count_result = session.run(
                    f"MATCH ()-[r:{rel_type}]->() RETURN count(r) as cnt"
                )
                cnt = count_result.single()['cnt']
                results['relationship_counts'][rel_type] = cnt
                results['total_relationships'] += cnt

        return results

    def get_stats(self) -> Dict[str, Any]:
        """Return loading statistics."""
        return self.stats
