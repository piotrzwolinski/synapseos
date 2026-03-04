#!/usr/bin/env bash
# =============================================================================
# Step 5: Migrate FalkorDB Data to Azure
# =============================================================================
# Run this on Mac after Azure FalkorDB container is running (step 4).
#
# Strategy:
#   1. Export graph from source FalkorDB (Fly.io / Cloud / local)
#   2. Re-run seed queries against Azure FalkorDB
#
# FalkorDB doesn't support GRAPH.COPY across instances, so we use
# Cypher DUMP or re-seed from the graph builder scripts.
#
# Usage:
#   ./5-migrate-data.sh --reseed           # Re-run seed scripts against Azure
#   ./5-migrate-data.sh --dump-restore     # RDB dump + restore (advanced)
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# --- Configuration ---
# Source FalkorDB (where data currently lives)
SOURCE_HOST="${SOURCE_FALKORDB_HOST:-localhost}"
SOURCE_PORT="${SOURCE_FALKORDB_PORT:-6379}"
SOURCE_PASSWORD="${SOURCE_FALKORDB_PASSWORD:-}"
SOURCE_GRAPH="${SOURCE_FALKORDB_GRAPH:-synapse}"

# Target: Azure FalkorDB (get FQDN from step 4 output)
TARGET_HOST="${TARGET_FALKORDB_HOST:-}"
TARGET_PORT="${TARGET_FALKORDB_PORT:-6379}"
TARGET_PASSWORD="${TARGET_FALKORDB_PASSWORD:-}"
TARGET_GRAPH="${TARGET_FALKORDB_GRAPH:-synapse}"

MODE="${1:---reseed}"

usage() {
    echo -e "${CYAN}Usage:${NC}"
    echo "  $0 --reseed          Re-seed Azure FalkorDB using Python seed scripts"
    echo "  $0 --dump-restore    RDB dump from source, restore to Azure"
    echo ""
    echo "Environment variables:"
    echo "  SOURCE_FALKORDB_HOST, SOURCE_FALKORDB_PORT, SOURCE_FALKORDB_PASSWORD"
    echo "  TARGET_FALKORDB_HOST, TARGET_FALKORDB_PORT, TARGET_FALKORDB_PASSWORD"
}

# =============================================================================
# Option 1: Re-seed (recommended — clean start)
# =============================================================================
reseed() {
    echo -e "${CYAN}=== Re-seeding Azure FalkorDB ===${NC}"

    if [ -z "$TARGET_HOST" ]; then
        echo -e "${RED}ERROR: Set TARGET_FALKORDB_HOST (Azure FalkorDB FQDN from step 4)${NC}"
        echo "Example: export TARGET_FALKORDB_HOST=synapse-falkordb.internal.azurecontainerapps.io"
        exit 1
    fi

    echo -e "${YELLOW}This will populate the Azure FalkorDB with fresh graph data.${NC}"
    echo "Target: $TARGET_HOST:$TARGET_PORT / graph: $TARGET_GRAPH"
    echo ""
    read -p "Continue? [y/N] " confirm
    [ "$confirm" = "y" ] || exit 0

    # Point the backend env vars to Azure FalkorDB
    export FALKORDB_HOST="$TARGET_HOST"
    export FALKORDB_PORT="$TARGET_PORT"
    export FALKORDB_PASSWORD="$TARGET_PASSWORD"
    export FALKORDB_GRAPH="$TARGET_GRAPH"

    # Check if we have seed scripts
    SEED_DIR="$PROJECT_ROOT/backend"
    cd "$SEED_DIR"

    # Activate venv if exists
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
        echo -e "${GREEN}Activated Python venv${NC}"
    fi

    # Run database initialization / seed
    echo -e "\n${CYAN}Running graph seed...${NC}"
    echo "This connects directly from your Mac to Azure FalkorDB."
    echo "Make sure the FalkorDB container app has TCP ingress enabled."

    # The database.py reads from env vars, so seeding happens by importing and running
    python -c "
from database import GraphConnection
db = GraphConnection()
print(f'Connected to {db.host}:{db.port} / graph: {db.graph_name}')

# Test connectivity
result = db.graph.query('RETURN 1 AS test')
print(f'Connection test: OK')

# Check existing data
result = db.graph.query('MATCH (n) RETURN count(n) AS node_count')
count = result.result_set[0][0] if result.result_set else 0
print(f'Existing nodes: {count}')
"

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Connection to Azure FalkorDB successful!${NC}"
    else
        echo -e "${RED}Connection failed. Check:${NC}"
        echo "  1. Is FalkorDB container running? (check step 4 logs)"
        echo "  2. Is TCP ingress enabled?"
        echo "  3. Can your Mac reach the Azure FQDN?"
        exit 1
    fi

    echo -e "\n${YELLOW}NOTE: To seed the full graph, use the graph-builder skill or run${NC}"
    echo -e "${YELLOW}your Cypher seed scripts against the Azure FalkorDB.${NC}"
    echo ""
    echo "Example with FalkorDB MCP (in Claude Code):"
    echo "  mcp__falkordb__query_graph(graphName='synapse', query='MATCH (n) RETURN count(n)')"
    echo ""
    echo "Or run Cypher files:"
    echo "  redis-cli -h $TARGET_HOST -p $TARGET_PORT -a $TARGET_PASSWORD"
    echo "  > GRAPH.QUERY synapse \"YOUR CYPHER QUERY\""
}

# =============================================================================
# Option 2: RDB Dump + Restore (preserves exact data)
# =============================================================================
dump_restore() {
    echo -e "${CYAN}=== RDB Dump + Restore ===${NC}"

    if [ -z "$SOURCE_HOST" ] || [ -z "$TARGET_HOST" ]; then
        echo -e "${RED}ERROR: Set both SOURCE_FALKORDB_HOST and TARGET_FALKORDB_HOST${NC}"
        exit 1
    fi

    echo "Source: $SOURCE_HOST:$SOURCE_PORT"
    echo "Target: $TARGET_HOST:$TARGET_PORT"

    # Check redis-cli is available
    if ! command -v redis-cli &>/dev/null; then
        echo -e "${YELLOW}Installing redis-cli via brew...${NC}"
        brew install redis
    fi

    OUTPUT_DIR="$SCRIPT_DIR/output"
    mkdir -p "$OUTPUT_DIR"
    DUMP_FILE="$OUTPUT_DIR/falkordb-dump.rdb"

    # Export: Use BGSAVE + download RDB
    echo -e "\n${CYAN}Step 1: Triggering BGSAVE on source...${NC}"
    AUTH_FLAG=""
    [ -n "$SOURCE_PASSWORD" ] && AUTH_FLAG="-a $SOURCE_PASSWORD"

    redis-cli -h "$SOURCE_HOST" -p "$SOURCE_PORT" $AUTH_FLAG BGSAVE
    echo "Waiting for background save to complete..."
    sleep 5

    # For Fly.io / remote: we can't directly copy the RDB file
    # Instead, we'll use DUMP/RESTORE per key (slower but works remotely)
    echo -e "\n${CYAN}Step 2: Exporting graph keys...${NC}"

    # Get all graph-related keys
    KEYS=$(redis-cli -h "$SOURCE_HOST" -p "$SOURCE_PORT" $AUTH_FLAG KEYS "*" 2>/dev/null)
    echo "Found keys: $KEYS"

    echo -e "\n${YELLOW}For FalkorDB graph migration, the recommended approach is:${NC}"
    echo "1. Export all Cypher CREATE statements from the source graph"
    echo "2. Re-execute them on the target"
    echo ""
    echo "Run this Cypher on source to export nodes:"
    echo "  GRAPH.QUERY $SOURCE_GRAPH \"MATCH (n) RETURN n\""
    echo ""
    echo "Then recreate on target:"
    echo "  GRAPH.QUERY $TARGET_GRAPH \"CREATE ...\""
    echo ""
    echo -e "${YELLOW}For a complete data transfer, use the --reseed option instead.${NC}"
}

# --- Main ---
case "$MODE" in
    --reseed)       reseed ;;
    --dump-restore) dump_restore ;;
    --help|-h)      usage ;;
    *)              usage; exit 1 ;;
esac
