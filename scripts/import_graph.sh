#!/usr/bin/env bash
# =============================================================================
# CardioKB Graph Import
#
# Restores graph data into the Dockerized Memgraph from an export archive.
# Works with the volume backup produced by export_graph.sh.
#
# Usage:
#   ./scripts/import_graph.sh data/export/memgraph-data.tar.gz
#   ./scripts/import_graph.sh --cypher data/export/cardiokb.cypherl
#
# Prerequisites:
#   docker compose up -d memgraph   (Memgraph service must exist)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Docker compose volume name: <project-dir-name>_memgraph-data
# docker compose prefixes with the project directory name in lowercase
COMPOSE_PROJECT=$(basename "$PROJECT_DIR" | tr '[:upper:]' '[:lower:]' | tr -cd '[:alnum:]-')
VOLUME_NAME="${COMPOSE_PROJECT}_memgraph-data"
SERVICE_NAME="memgraph"

usage() {
    echo "Usage:"
    echo "  $0 <memgraph-data.tar.gz>                  # Volume restore"
    echo "  $0 --cypher <cardiokb.cypherl>              # Cypher import"
    exit 1
}

if [[ $# -lt 1 ]]; then
    usage
fi

if [[ "$1" == "--cypher" ]]; then
    # ── Cypher import mode ──────────────────────────────────────────────────
    CYPHERL="${2:-}"
    if [[ -z "$CYPHERL" || ! -f "$CYPHERL" ]]; then
        echo "ERROR: Cypher file not found: $CYPHERL"
        usage
    fi

    echo ""
    echo "Importing Cypher dump into Memgraph..."
    echo "File: $CYPHERL"
    echo ""

    # Ensure Memgraph is running
    cd "$PROJECT_DIR"
    docker compose up -d "$SERVICE_NAME"
    CONTAINER=$(docker compose ps -q "$SERVICE_NAME")
    if [[ -z "$CONTAINER" ]]; then
        echo "ERROR: Memgraph container not found. Run 'docker compose up -d memgraph' first."
        exit 1
    fi
    echo "Waiting for Memgraph to be ready..."
    for i in $(seq 1 30); do
        if echo "RETURN 1;" | docker exec -i "$CONTAINER" mgconsole >/dev/null 2>&1; then
            echo "Memgraph is ready."
            break
        fi
        if [ "$i" -eq 30 ]; then
            echo "ERROR: Memgraph did not become ready within 60 seconds."
            exit 1
        fi
        sleep 2
    done
    if [[ -z "$CONTAINER" ]]; then
        echo "ERROR: Memgraph container not found. Run 'docker compose up -d memgraph' first."
        exit 1
    fi

    # Stream the Cypher file into mgconsole
    cat "$CYPHERL" | docker exec -i "$CONTAINER" mgconsole

    echo ""
    echo "Done. Verifying node count..."
    echo "MATCH (n) RETURN count(n);" | docker exec -i "$CONTAINER" mgconsole
    echo ""

else
    # ── Volume restore mode (default) ──────────────────────────────────────
    ARCHIVE="$1"
    if [[ ! -f "$ARCHIVE" ]]; then
        echo "ERROR: Archive not found: $ARCHIVE"
        usage
    fi

    echo ""
    echo "Restoring Memgraph data volume from backup..."
    echo "Archive: $ARCHIVE"
    echo "Target volume: $VOLUME_NAME"
    echo ""

    # Stop Memgraph if running
    cd "$PROJECT_DIR"
    docker compose stop "$SERVICE_NAME" 2>/dev/null || true
    sleep 2

    # Create volume if it doesn't exist
    docker volume create "$VOLUME_NAME" 2>/dev/null || true

    # Clear existing data and restore from archive
    ARCHIVE_ABS="$(cd "$(dirname "$ARCHIVE")" && pwd)/$(basename "$ARCHIVE")"
    docker run --rm \
        -v "${VOLUME_NAME}:/data" \
        -v "${ARCHIVE_ABS}:/backup/archive.tar.gz:ro" \
        alpine sh -c "rm -rf /data/* && tar xzf /backup/archive.tar.gz -C /data"

    echo "Volume restored. Starting Memgraph..."
    docker compose up -d "$SERVICE_NAME"

    # Wait for Memgraph to finish loading the snapshot
    CONTAINER=$(docker compose ps -q "$SERVICE_NAME")
    echo "Waiting for Memgraph to be ready..."
    for i in $(seq 1 30); do
        if echo "RETURN 1;" | docker exec -i "$CONTAINER" mgconsole >/dev/null 2>&1; then
            echo "Memgraph is ready."
            break
        fi
        if [ "$i" -eq 30 ]; then
            echo "ERROR: Memgraph did not become ready within 60 seconds."
            exit 1
        fi
        sleep 2
    done

    # Verify
    echo "Verifying graph..."
    echo "MATCH (n) RETURN count(n) AS nodes;" | docker exec -i "$CONTAINER" mgconsole
    echo "MATCH ()-[r]->() RETURN count(r) AS relationships;" | docker exec -i "$CONTAINER" mgconsole
    echo ""
    echo "Done. Start the full stack with: docker compose up -d"
fi
