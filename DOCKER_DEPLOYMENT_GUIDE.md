# CardioKB Memgraph Docker Deployment Guide

## Quick Start (One-Liner)

```bash
# Terminal 1: Start Memgraph with data mounted
docker run -it -p 7687:7687 -p 3000:3000 \
  -v /Users/nawaza/Desktop/Cardio-KB/data/output:/import-data \
  memgraph/memgraph-platform

# Terminal 2: Get container ID and import data
CONTAINER_ID=$(docker ps -q -f ancestor=memgraph/memgraph-platform)
docker exec -i $CONTAINER_ID mgconsole < /Users/nawaza/Desktop/Cardio-KB/data/output/import.cypher
```

---

## Detailed Docker Instructions

### Option 1: Docker Run (Manual)

#### Step 1: Start Memgraph Container
```bash
docker run -it \
  --name cardio-kb-memgraph \
  -p 7687:7687 \
  -p 3000:3000 \
  -v /Users/nawaza/Desktop/Cardio-KB/data/output:/import-data \
  -e MEMGRAPH_QUERY_EXECUTION_TIMEOUT_MS=600000 \
  memgraph/memgraph-platform:latest
```

**Explanation**:
- `-it`: Interactive terminal
- `--name cardio-kb-memgraph`: Container name for easy reference
- `-p 7687:7687`: Bolt protocol port (graph database queries)
- `-p 3000:3000`: Web interface port
- `-v /Users/...:/import-data`: Mount data directory for LOAD CSV
- `-e MEMGRAPH_QUERY_EXECUTION_TIMEOUT_MS=600000`: 10-minute timeout for large imports

#### Step 2: Verify Container is Running
```bash
docker ps -f name=cardio-kb-memgraph
```

Expected output:
```
CONTAINER ID   IMAGE                           COMMAND             STATUS
abcd1234ef56   memgraph/memgraph-platform      "..."               Up 10 seconds
```

#### Step 3: Import the Knowledge Graph
```bash
# Method A: Direct file import
docker exec -i cardio-kb-memgraph mgconsole < /Users/nawaza/Desktop/Cardio-KB/data/output/import.cypher

# Method B: Using container ID variable
CONTAINER_ID=$(docker ps -q -f name=cardio-kb-memgraph)
docker exec -i $CONTAINER_ID mgconsole < /Users/nawaza/Desktop/Cardio-KB/data/output/import.cypher
```

**Note**: Import may take 30-60 minutes depending on your system resources.

#### Step 4: Monitor Import Progress
```bash
# Check container logs
docker logs -f cardio-kb-memgraph

# Connect to Memgraph and check node/edge counts
docker exec -it cardio-kb-memgraph mgconsole
```

Then run:
```cypher
MATCH (n) RETURN count(n) AS total_nodes;
MATCH ()-[r]->() RETURN count(r) AS total_edges;
```

---

### Option 2: Docker Compose (Recommended for Production)

#### Step 1: Create docker-compose.yml
```bash
cd /Users/nawaza/Desktop/Cardio-KB
cat > docker-compose.yml << 'COMPOSE'
version: '3.8'

services:
  memgraph:
    image: memgraph/memgraph-platform:latest
    container_name: cardio-kb-memgraph
    ports:
      - "7687:7687"  # Bolt protocol
      - "3000:3000"  # Web UI
    volumes:
      - ./data/output:/import-data:ro  # Read-only mount
      - memgraph-data:/var/lib/memgraph  # Persistent storage
    environment:
      - MEMGRAPH_BOLT_PORT=7687
      - MEMGRAPH_QUERY_EXECUTION_TIMEOUT_MS=600000
      - MEMGRAPH_MEMORY_LIMIT=16gb  # Adjust based on system RAM
    healthcheck:
      test: ["CMD", "mgconsole", "--host", "127.0.0.1", "--port", "7687", "RETURN 1"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    restart: unless-stopped

volumes:
  memgraph-data:
    driver: local
COMPOSE
```

#### Step 2: Start Services
```bash
docker-compose up -d

# Wait for Memgraph to be ready
sleep 30

# Verify health
docker-compose ps
```

#### Step 3: Import Data
```bash
# Execute import script
docker-compose exec -T memgraph mgconsole < data/output/import.cypher

# Or with file streaming for large imports
cat data/output/import.cypher | docker-compose exec -T memgraph mgconsole
```

#### Step 4: Verify Import
```bash
docker-compose exec memgraph mgconsole
```

Then run verification queries (see below).

#### Step 5: Stop Services
```bash
docker-compose down

# Stop and remove all data
docker-compose down -v
```

---

## Verification Queries

### After Import, Run These Queries

#### 1. Total Counts
```cypher
MATCH (n) RETURN count(n) AS total_nodes;
MATCH ()-[r]->() RETURN count(r) AS total_edges;
```

**Expected Results**:
```
total_nodes: 2,409,311
total_edges: 11,978,313
```

#### 2. Node Type Distribution
```cypher
MATCH (n) 
RETURN labels(n)[0] AS node_type, count(n) AS count 
ORDER BY count DESC;
```

**Expected Results**:
```
Variant                      2,100,938
Gene                           193,795
Phenotype                       19,389
BiologicalProcess               24,428
ClinicalTrial                   21,578
Pathway                          2,870
MolecularFunction               10,056
CellularComponent                4,076
Disease                          3,442
GeneFamily                       4,257
Drug                            14,460
TranscriptionFactor              1,568
SideEffect                       4,251
PharmacologicClass               2,359
BodyPart                         1,400
Symptom                            415
DrugLabel                           29
```

#### 3. Edge Type Distribution
```cypher
MATCH ()-[r]->() 
RETURN type(r) AS relationship_type, count(r) AS count 
ORDER BY count DESC;
```

**Expected Top 5 Results**:
```
bodyPartOverexpressesGene              6,616,463
chemicalIncreasesExpression            1,288,204
chemicalDecreasesExpression            1,001,149
geneAssociatesWithPhenotype              314,250
geneExpressedInBodyPart                  398,361
```

#### 4. Sample Query: Genes Associated with Heart Disease
```cypher
MATCH (g:Gene)-[:geneAssociatesWithDisease]->(d:Disease)
WHERE d.diseaseName CONTAINS 'heart'
RETURN g.geneSymbol, d.diseaseName
LIMIT 10;
```

#### 5. Sample Query: Drug-Gene-Disease Path
```cypher
MATCH (drug:Drug)-[:chemicalBindsGene]->(gene:Gene)-[:geneAssociatesWithDisease]->(disease:Disease)
WHERE drug.commonName IS NOT NULL 
  AND gene.geneSymbol IS NOT NULL
  AND disease.diseaseName IS NOT NULL
RETURN drug.commonName, gene.geneSymbol, disease.diseaseName
LIMIT 10;
```

---

## Web Interface Access

### URL
```
http://localhost:3000
```

### Features
- Visual graph exploration
- Query editor
- Real-time graph visualization
- Database statistics

### Default Access
- No authentication required by default
- Check Memgraph documentation for security setup

---

## Troubleshooting

### Issue 1: Port Already in Use
```bash
# Kill process on port 7687
lsof -ti:7687 | xargs kill -9

# Or use different ports
docker run -p 7688:7687 -p 3001:3000 ...
```

### Issue 2: Import Takes Too Long
```bash
# Check current progress
docker logs -f cardio-kb-memgraph

# Increase timeout in docker-compose.yml
MEMGRAPH_QUERY_EXECUTION_TIMEOUT_MS=1800000  # 30 minutes
```

### Issue 3: Out of Memory
```bash
# Increase Docker memory limit
docker run -m 32g ...

# Or in docker-compose.yml
mem_limit: 32gb
memswap_limit: 32gb
```

### Issue 4: CSV File Not Found
```bash
# Verify mount is correct
docker inspect cardio-kb-memgraph | grep -A 5 Mounts

# Check file permissions
ls -la /Users/nawaza/Desktop/Cardio-KB/data/output/*.csv | head -5
```

### Issue 5: Connection Refused
```bash
# Verify container is running
docker ps -a -f name=cardio-kb-memgraph

# Check logs for errors
docker logs cardio-kb-memgraph

# Restart container
docker restart cardio-kb-memgraph
```

---

## Performance Tuning

### Memory Configuration
```bash
# For systems with 32GB+ RAM
docker run -m 32g \
  -e MEMGRAPH_MEMORY_LIMIT=28gb \
  ...

# For systems with 16GB RAM
docker run -m 16g \
  -e MEMGRAPH_MEMORY_LIMIT=14gb \
  ...
```

### CPU Configuration
```bash
# Limit CPU usage to 4 cores
docker run --cpus="4" ...

# In docker-compose.yml
cpus: '4'
```

### Query Timeout
```bash
# Increase timeout for large queries
MEMGRAPH_QUERY_EXECUTION_TIMEOUT_MS=1800000  # 30 minutes
```

---

## Backup and Restore

### Backup Data
```bash
# Using docker-compose
docker-compose exec memgraph memgraph-backup --dest /tmp/backup

# Extract from container
docker cp cardio-kb-memgraph:/tmp/backup ./backups/
```

### Restore Data
```bash
# Copy backup to container
docker cp ./backups/backup cardio-kb-memgraph:/tmp/

# Restore
docker exec cardio-kb-memgraph memgraph-restore --source /tmp/backup
```

---

## Cleanup

### Remove Container
```bash
docker stop cardio-kb-memgraph
docker rm cardio-kb-memgraph
```

### Remove Image
```bash
docker rmi memgraph/memgraph-platform
```

### Remove Volumes
```bash
docker volume rm cardio-kb-memgraph_data
```

### Complete Cleanup
```bash
docker-compose down -v
rm docker-compose.yml
```

---

## System Requirements

### Minimum
- **CPU**: 4 cores
- **RAM**: 16 GB
- **Disk**: 100 GB (for import + indexes)
- **OS**: macOS, Linux, or Windows (with WSL2)

### Recommended
- **CPU**: 8+ cores
- **RAM**: 32 GB
- **Disk**: 500 GB SSD
- **Network**: 1 Gbps+ for optimal performance

---

## Additional Resources

- **Memgraph Documentation**: https://memgraph.com/docs
- **Cypher Query Language**: https://memgraph.com/docs/cypher-manual
- **Docker Documentation**: https://docs.docker.com
- **CardioKB Repository**: /Users/nawaza/Desktop/Cardio-KB

---

## Support

For issues or questions:
1. Check logs: `docker logs cardio-kb-memgraph`
2. Review troubleshooting section above
3. Consult Memgraph documentation
4. Check CardioKB repository for updates
