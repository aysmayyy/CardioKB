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

BATCH_SIZE = 1000


class Neo4jLoader:
    """
    Loads parsed DataFrames into Neo4j using Cypher queries.

    Driven by ONTOLOGY_CONFIGS: iterates configs, loads nodes first,
    then relationships, using MERGE or CREATE as specified.
    """

    def __init__(self, uri: str, username: str, password: str,
                 database: str = "neo4j"):
        """
        Initialize Neo4j connection.

        Args:
            uri: Neo4j bolt URI (e.g., bolt://localhost:7687)
            username: Neo4j username
            password: Neo4j password
            database: Neo4j database name
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
        logger.info("Setting up Neo4j constraints...")
        seen = set()

        for config_key, config in ontology_configs.items():
            if config.get('data_type') != 'node' or config.get('skip'):
                continue

            node_type = config['node_type']
            iri_col = config['parse_config'].get('iri_column_name', '')
            prop_map = config['parse_config'].get('data_property_map', {})

            # Map the IRI column to its Neo4j property name
            neo4j_prop = prop_map.get(iri_col, iri_col)
            key = (node_type, neo4j_prop)
            if key in seen:
                continue
            seen.add(key)

            constraint_name = f"uniq_{node_type}_{neo4j_prop}"
            query = (
                f"CREATE CONSTRAINT {constraint_name} IF NOT EXISTS "
                f"FOR (n:{node_type}) REQUIRE n.{neo4j_prop} IS UNIQUE"
            )
            try:
                with self.driver.session(database=self.database) as session:
                    session.run(query)
                logger.info(f"  Constraint: {node_type}.{neo4j_prop}")
            except Exception as e:
                logger.warning(f"  Failed constraint {constraint_name}: {e}")

    def setup_indexes(self, ontology_configs: Dict[str, Dict]):
        """
        Create indexes on match_property fields used in relationships.

        Args:
            ontology_configs: The ONTOLOGY_CONFIGS dictionary.
        """
        logger.info("Setting up Neo4j indexes...")
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

                index_name = f"idx_{node_type}_{match_prop}"
                query = (
                    f"CREATE INDEX {index_name} IF NOT EXISTS "
                    f"FOR (n:{node_type}) ON (n.{match_prop})"
                )
                try:
                    with self.driver.session(database=self.database) as session:
                        session.run(query)
                    logger.info(f"  Index: {node_type}.{match_prop}")
                except Exception as e:
                    logger.warning(f"  Failed index {index_name}: {e}")

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
                    return pd.read_csv(tsv_path, sep='\t')
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
        iri_col = pc.get('iri_column_name', '')
        prop_map = pc.get('data_property_map', {})

        # Filter if needed
        df = self._apply_filter(df, pc)

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

        if merge:
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
        rows = rows.where(pd.notna(rows), None)
        row_dicts = rows.to_dict('records')

        count = self._execute_batch(query, row_dicts)
        action = "merged" if merge else "created/merged"
        logger.info(f"  {config_key}: {action} {count} {node_type} nodes")

        if merge:
            self.stats['nodes_merged'] += count
        else:
            self.stats['nodes_created'] += count

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

        # Forward relationship query
        query = (
            f"UNWIND $rows AS row "
            f"MATCH (s:{subj_node_type} {{{subj_match_prop}: row.{subj_col}}}) "
            f"MATCH (o:{obj_node_type} {{{obj_match_prop}: row.{obj_col}}}) "
            f"MERGE (s)-[r:{rel_type}]->(o) "
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
        # Coerce match columns to match Neo4j property types.
        # float-that-are-ints → int, str-that-are-ints → int, keep other str as str.
        for col in [subj_col, obj_col]:
            if col in rows.columns:
                rows[col] = rows[col].apply(
                    lambda x: (
                        int(x) if isinstance(x, float) and x == int(x)
                        else int(x) if isinstance(x, str) and x.isdigit()
                        else x
                    ) if x is not None else None
                )
        row_dicts = rows.to_dict('records')

        count = self._execute_batch(query, row_dicts, source_label=source_label)
        logger.info(f"  {config_key}: merged {count} {rel_type} relationships")
        self.stats['relationships_merged'] += count

        # Inverse relationship
        if inverse_rel_type:
            inv_query = (
                f"UNWIND $rows AS row "
                f"MATCH (s:{subj_node_type} {{{subj_match_prop}: row.{subj_col}}}) "
                f"MATCH (o:{obj_node_type} {{{obj_match_prop}: row.{obj_col}}}) "
                f"MERGE (o)-[r:{inverse_rel_type}]->(s) "
            )
            inv_set_parts = []
            if source_label:
                inv_set_parts.append("r.source = $source_label")
            if rel_set_str:
                inv_set_parts.append(rel_set_str)
            if inv_set_parts:
                inv_query += f"SET {', '.join(inv_set_parts)}"

            inv_count = self._execute_batch(inv_query, row_dicts, source_label=source_label)
            logger.info(f"  {config_key}: merged {inv_count} {inverse_rel_type} (inverse) relationships")
            self.stats['relationships_merged'] += inv_count

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

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
                       source_label: Optional[str] = None) -> int:
        """
        Execute a Cypher query in batches using UNWIND.

        Args:
            query: Cypher query with $rows parameter.
            rows: List of row dictionaries.
            source_label: Optional source label passed as a top-level Cypher parameter.

        Returns:
            Total rows processed.
        """
        total = 0
        params: Dict[str, Any] = {}
        if source_label:
            params['source_label'] = source_label

        with self.driver.session(database=self.database) as session:
            for i in range(0, len(rows), BATCH_SIZE):
                batch = rows[i:i + BATCH_SIZE]
                try:
                    result = session.run(query, rows=batch, **params)
                    summary = result.consume()
                    total += len(batch)
                except Exception as e:
                    logger.error(f"Batch error at offset {i}: {e}")
                    self.stats['errors'].append(str(e))

        return total

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
            counts['enriched'] = self._execute_batch(query_enrich, rows_doid)
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
            counts['created'] = self._execute_batch(query_create, rows_new)
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

        with self.driver.session(database=self.database) as session:
            # Node counts by label
            records = session.run(
                "CALL db.labels() YIELD label "
                "CALL { WITH label "
                "  CALL db.stats.retrieve('GRAPH COUNTS') YIELD data "
                "  RETURN data } "
                "RETURN label"
            )
            # Simpler approach: count per label
            labels_result = session.run("CALL db.labels() YIELD label RETURN label")
            for record in labels_result:
                label = record['label']
                count_result = session.run(f"MATCH (n:{label}) RETURN count(n) as cnt")
                cnt = count_result.single()['cnt']
                results['node_counts'][label] = cnt
                results['total_nodes'] += cnt

            # Relationship counts by type
            rel_types_result = session.run(
                "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType"
            )
            for record in rel_types_result:
                rel_type = record['relationshipType']
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
