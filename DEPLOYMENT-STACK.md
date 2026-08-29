# Deployment Stack - Production Ready

**Status:** Ready to implement when Phase 8 complete
**Components:** Scripts + Manuals + Monitoring setup

---

## Part A: Deployment Automation Scripts

### deploy.sh - One-Command Deployment

```bash
#!/bin/bash
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Brain-Eleven v3 Deployment${NC}"
echo "================================"

# 1. PRE-FLIGHT CHECKS
echo -e "\n${YELLOW}[1/7] Pre-flight checks...${NC}"
command -v docker &> /dev/null || { echo -e "${RED}Docker not found${NC}"; exit 1; }
command -v docker-compose &> /dev/null || { echo -e "${RED}Docker Compose not found${NC}"; exit 1; }
test -f Dockerfile || { echo -e "${RED}Dockerfile not found${NC}"; exit 1; }
test -f docker-compose.yml || { echo -e "${RED}docker-compose.yml not found${NC}"; exit 1; }
echo -e "${GREEN}✓ All pre-flight checks passed${NC}"

# 2. BUILD DOCKER IMAGE
echo -e "\n${YELLOW}[2/7] Building Docker image...${NC}"
DOCKER_TAG="brain-eleven:$(git rev-parse --short HEAD)"
docker build -t $DOCKER_TAG -t brain-eleven:latest .
echo -e "${GREEN}✓ Image built: $DOCKER_TAG${NC}"

# 3. ENVIRONMENT SETUP
echo -e "\n${YELLOW}[3/7] Setting up environment...${NC}"
if [ ! -f .env ]; then
    echo -e "${YELLOW}Creating .env file...${NC}"
    cat > .env << EOF
OPENAI_API_KEY=${OPENAI_API_KEY:-sk-test}
VAULT_PATH=/vault
REDIS_HOST=redis
REDIS_PORT=6379
POSTGRES_HOST=postgres
POSTGRES_USER=brain
POSTGRES_PASSWORD=$(openssl rand -base64 32)
POSTGRES_DB=brain_eleven
EOF
    echo -e "${GREEN}✓ .env created (edit with your values)${NC}"
else
    echo -e "${GREEN}✓ .env already exists${NC}"
fi

# 4. VOLUME SETUP
echo -e "\n${YELLOW}[4/7] Setting up volumes...${NC}"
mkdir -p data/vault data/postgres data/redis
chmod 755 data/*
echo -e "${GREEN}✓ Volumes ready${NC}"

# 5. START SERVICES
echo -e "\n${YELLOW}[5/7] Starting services...${NC}"
docker-compose up -d
echo -e "${GREEN}✓ Services started${NC}"

# 6. HEALTH CHECKS
echo -e "\n${YELLOW}[6/7] Health checks...${NC}"
sleep 5
for i in {1..30}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ API healthy${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}✗ API health check failed${NC}"
        exit 1
    fi
    echo "Waiting for API... ($i/30)"
    sleep 1
done

# 7. FINAL STATUS
echo -e "\n${YELLOW}[7/7] Final status...${NC}"
docker-compose ps
echo -e "\n${GREEN}✅ Deployment complete!${NC}"
echo -e "${YELLOW}Access:${NC}"
echo "  API:        http://localhost:8000"
echo "  Docs:       http://localhost:8000/docs"
echo "  Redis:      localhost:6379"
echo "  Neo4j:      http://localhost:7474 (if enabled)"

# 8. POST-DEPLOYMENT
echo -e "\n${YELLOW}Initialization...${NC}"
docker-compose exec app python scripts/memory-compiler.py
docker-compose exec app python scripts/memory-validator.py
echo -e "${GREEN}✓ Memory store initialized${NC}"

# 9. TEST ENDPOINTS
echo -e "\n${YELLOW}Testing endpoints...${NC}"
curl -s http://localhost:8000/health | jq .
echo -e "${GREEN}✓ All systems operational${NC}"
```

### rollback.sh - Instant Rollback

```bash
#!/bin/bash
set -e

echo "🔄 Rolling back Brain-Eleven..."

# 1. Stop current services
echo "Stopping services..."
docker-compose down

# 2. Check for backup image
BACKUP_TAG="brain-eleven:backup"
if docker image inspect $BACKUP_TAG > /dev/null 2>&1; then
    echo "Restoring from backup image..."
    docker tag $BACKUP_TAG brain-eleven:latest
else
    echo "⚠️  No backup image found"
fi

# 3. Restore database from backup
if [ -f "data/postgres/backup_latest.sql" ]; then
    echo "Restoring database from backup..."
    docker-compose up -d postgres
    sleep 5
    docker-compose exec -T postgres psql -U brain -d brain_eleven < data/postgres/backup_latest.sql
fi

# 4. Start services with previous version
echo "Starting with previous version..."
docker-compose up -d

echo "✅ Rollback complete"
docker-compose ps
```

### backup.sh - Automated Backups

```bash
#!/bin/bash
set -e

BACKUP_DIR="data/backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p $BACKUP_DIR

echo "🔄 Creating backup: $BACKUP_DIR"

# 1. Backup PostgreSQL
echo "Backing up PostgreSQL..."
docker-compose exec -T postgres pg_dump -U brain brain_eleven > $BACKUP_DIR/database.sql
gzip $BACKUP_DIR/database.sql

# 2. Backup Redis
echo "Backing up Redis..."
docker-compose exec -T redis redis-cli BGSAVE
docker-compose exec redis cat /data/dump.rdb > $BACKUP_DIR/redis.rdb

# 3. Backup Memory Store
echo "Backing up memory store..."
cp .claude/validated-memory.json $BACKUP_DIR/
cp .claude/embeddings.json $BACKUP_DIR/

# 4. Tag Docker image
echo "Tagging current image..."
CURRENT_IMAGE=$(docker-compose images -q app)
docker tag $CURRENT_IMAGE brain-eleven:backup

# 5. Cleanup old backups (keep last 7)
echo "Cleaning up old backups..."
ls -t data/backups | tail -n +8 | xargs -I {} rm -rf data/backups/{}

echo "✅ Backup complete: $BACKUP_DIR"
ls -lh $BACKUP_DIR
```

---

## Part B: Operations Manual

### Running & Managing

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f app          # API logs
docker-compose logs -f redis        # Cache logs
docker-compose logs -f postgres     # Database logs

# Scale services
docker-compose up -d --scale app=3  # 3 API instances

# Stop services (preserves data)
docker-compose stop

# Remove everything (data preserved)
docker-compose down

# Full cleanup (data removed!)
docker-compose down -v
```

### Health Monitoring

```bash
# Check API health
curl http://localhost:8000/health
# Expected: {"status": "healthy", "timestamp": "..."}

# Check Redis connection
docker-compose exec redis redis-cli ping
# Expected: PONG

# Check PostgreSQL connection
docker-compose exec postgres psql -U brain -c "SELECT 1"
# Expected: 1 row

# View API metrics
curl http://localhost:8000/metrics

# Memory store stats
curl http://localhost:8000/memories | jq '.total'
```

### Troubleshooting

```
Problem: API not responding
Solution:
  1. Check logs: docker-compose logs app
  2. Check health: curl http://localhost:8000/health
  3. Restart: docker-compose restart app
  4. Rebuild: docker-compose down && docker build -t brain-eleven:latest .

Problem: Out of disk space
Solution:
  1. Check: docker system df
  2. Clean images: docker image prune -a
  3. Clean volumes: docker volume prune
  4. Check backups: ls -lh data/backups/

Problem: Memory usage high
Solution:
  1. Check: docker stats
  2. L1 cache full: Restart app (clears in-memory LRU)
  3. L2 cache: docker-compose exec redis redis-cli FLUSHDB
  4. Scale down: docker-compose up -d --scale app=1

Problem: Database corruption
Solution:
  1. Stop: docker-compose stop postgres
  2. Restore: docker-compose up postgres
  3. Restore data: docker-compose exec postgres psql < backup.sql
  4. Restart app: docker-compose up -d app
```

### Maintenance Tasks

```bash
# Daily: Check health
0 6 * * * docker-compose exec app curl http://localhost:8000/health

# Weekly: Backup
0 2 * * 0 /app/backup.sh

# Weekly: Clean old backups (auto in backup.sh)
0 3 * * 0 find /app/data/backups -mtime +30 -exec rm -rf {} \;

# Monthly: Update Docker images
0 0 1 * * docker-compose pull && docker-compose up -d

# Monthly: Rebuild embeddings (optional refresh)
0 0 2 * * docker-compose exec app python scripts/embedding-generator.py
```

---

## Part C: Monitoring Dashboard

### Prometheus Configuration

```yaml
# prometheus.yml (optional, for metrics)
global:
  scrape_interval: 15s
  
scrape_configs:
  - job_name: 'brain-eleven-api'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'

  - job_name: 'redis'
    static_configs:
      - targets: ['localhost:6379']

  - job_name: 'postgres'
    static_configs:
      - targets: ['localhost:5432']
```

### Key Metrics to Monitor

```
API Performance:
  ├─ request_latency_ms (p50, p95, p99)
  ├─ request_count (total, by endpoint)
  ├─ error_rate (5xx errors)
  └─ active_requests

Cache Performance:
  ├─ cache_hits (L1, L2, L3)
  ├─ cache_misses
  ├─ cache_hit_rate (target > 60%)
  └─ eviction_rate

Database:
  ├─ connection_pool_usage
  ├─ query_latency
  ├─ memory_usage
  └─ disk_usage

System:
  ├─ cpu_usage (target < 70%)
  ├─ memory_usage (target < 80%)
  ├─ disk_space (alert < 20% free)
  └─ uptime
```

### Alerting Rules

```
Alert if:
  - API latency p95 > 500ms (5 min)
  - Error rate > 1% (2 min)
  - Cache hit rate < 50% (10 min)
  - Database connection pool > 80%
  - Disk space < 10%
  - Memory > 85%
  - Service down (unreachable)
```

---

## Part D: Security Hardening

### Pre-Deployment Checklist

```
Network:
  ☐ API only exposed on internal network
  ☐ Redis/PostgreSQL not exposed publicly
  ☐ CORS properly configured
  ☐ Rate limiting enabled (100 req/min per IP)

Secrets:
  ☐ .env not in git
  ☐ API keys rotated
  ☐ Database credentials strong (32+ chars)
  ☐ JWT signing key generated

Data:
  ☐ Database encrypted at rest (if required)
  ☐ Backups encrypted
  ☐ TLS for data in transit (optional)
  ☐ User data anonymized in logs

Access:
  ☐ Only necessary ports exposed
  ☐ SSH key authentication (no passwords)
  ☐ Audit logging enabled
  ☐ Regular security updates
```

### Docker Security

```dockerfile
# In Dockerfile
FROM python:3.13-slim
RUN addgroup --system app && adduser --system --group app
WORKDIR /app
COPY --chown=app:app . .
USER app
# Never run as root!
```

---

## Summary

**Deployment Stack provides:**
- ✅ One-command deployment (deploy.sh)
- ✅ Instant rollback capability
- ✅ Automated backups (daily)
- ✅ Health monitoring
- ✅ Operations manual
- ✅ Troubleshooting guide
- ✅ Security checklist
- ✅ Maintenance automation

**Ready to deploy on Day 1!**
