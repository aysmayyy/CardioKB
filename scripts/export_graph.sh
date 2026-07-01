#!/usr/bin/env bash
# =============================================================================
# CardioKB Graph Export
#
# Exports the Memgraph graph data for deployment. Two modes:
#
#   1. Volume backup (default, fast) — tars the Docker volume directly
#      Produces: data/export/memgraph-data.tar.gz (~2-4 GB)
#
#   2. Cypher dump (--cypher) — uses DUMP DATABASE via mgconsole
#      Produces: data/export/cardiokb.cypherl (very large, slow for 5M+ nodes)
#
# Usage:
#   ./scripts/export_graph.sh              # Volume backup (recommended)
#   ./scripts/export_graph.sh --cypher     # Cypher text dump
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
EXPORT_DIR="$PROJECT_DIR/data/export"

# Derive Docker Compose container and volume names from project directory
COMPOSE_PROJECT=$(basename "$PROJECT_DIR" | tr '[:upper:]' '[:lower:]' | tr -cd '[:alnum:]-')
CONTAINER_NAME="${COMPOSE_PROJECT}-memgraph-1"
VOLUME_NAME="${COMPOSE_PROJECT}_memgraph-data"

mkdir -p "$EXPORT_DIR"

# ── Ensure Memgraph is running ──────────────────────────────────────────────
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Starting Memgraph container..."
    docker start "$CONTAINER_NAME"
    sleep 10
fi

# ── Trigger a fresh snapshot before export ──────────────────────────────────
echo "Triggering snapshot inside Memgraph..."
echo "FREE MEMORY;" | docker exec -i "$CONTAINER_NAME" mgconsole 2>/dev/null || true
echo "Snapshot triggered."

if [[ "${1:-}" == "--cypher" ]]; then
    # ── Mode 2: Cypher dump ─────────────────────────────────────────────────
    OUTFILE="$EXPORT_DIR/cardiokb.cypherl"
    echo ""
    echo "Exporting graph as Cypher dump..."
    echo "WARNING: This will be very large for a 4.9M node graph. Consider using"
    echo "         the default volume backup instead."
    echo ""
    echo "Output: $OUTFILE"
    echo ""

    echo "DUMP DATABASE;" | docker exec -i "$CONTAINER_NAME" \
        mgconsole -output_format=cypherl > "$OUTFILE"

    SIZE=$(du -h "$OUTFILE" | cut -f1)
    echo ""
    echo "Done. Exported $SIZE to $OUTFILE"
    echo ""
    echo "To import on the target host:"
    echo "  cat $OUTFILE | docker exec -i <container> mgconsole"

else
    # ── Mode 1: Volume backup (default) ────────────────────────────────────
    OUTFILE="$EXPORT_DIR/memgraph-data.tar.gz"
    echo ""
    echo "Exporting Memgraph data volume..."
    echo "Output: $OUTFILE"
    echo ""

    # Stop Memgraph to get a consistent snapshot
    echo "Stopping Memgraph for consistent backup..."
    docker stop "$CONTAINER_NAME"
    sleep 3

    # Tar the volume contents
    docker run --rm \
        -v "${VOLUME_NAME}:/data:ro" \
        -v "${EXPORT_DIR}:/backup" \
        alpine tar czf /backup/memgraph-data.tar.gz -C /data .

    # Restart Memgraph
    echo "Restarting Memgraph..."
    docker start "$CONTAINER_NAME"

    SIZE=$(du -h "$OUTFILE" | cut -f1)
    echo ""
    echo "Done. Exported $SIZE to $OUTFILE"
    echo ""
    echo "To deploy on target host, run:"
    echo "  ./scripts/import_graph.sh $OUTFILE"
fi
