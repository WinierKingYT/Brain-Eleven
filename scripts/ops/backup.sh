#!/bin/bash
set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

BACKUP_DIR="data/backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p $BACKUP_DIR

echo -e "${YELLOW}🔄 Creating backup: $BACKUP_DIR${NC}"

# 1. Backup PostgreSQL
echo -e "\n${YELLOW}Backing up PostgreSQL...${NC}"
docker-compose exec -T postgres pg_dump -U brain brain_eleven | gzip > $BACKUP_DIR/database.sql.gz
echo -e "${GREEN}✅ Database backed up${NC}"

# 2. Backup Redis
echo -e "\n${YELLOW}Backing up Redis...${NC}"
docker-compose exec -T redis redis-cli BGSAVE > /dev/null 2>&1 || true
docker-compose exec redis cat /data/dump.rdb > $BACKUP_DIR/redis.rdb 2>/dev/null || true
echo -e "${GREEN}✅ Redis backed up${NC}"

# 3. Backup Memory Store
echo -e "\n${YELLOW}Backing up memory store...${NC}"
test -f .claude/validated-memory.json && cp .claude/validated-memory.json $BACKUP_DIR/
test -f .claude/embeddings.json && cp .claude/embeddings.json $BACKUP_DIR/
echo -e "${GREEN}✅ Memory store backed up${NC}"

# 4. Tag Docker image
echo -e "\n${YELLOW}Tagging current image...${NC}"
CURRENT_IMAGE=$(docker-compose images -q app 2>/dev/null || echo "")
if [ ! -z "$CURRENT_IMAGE" ]; then
    docker tag $CURRENT_IMAGE brain-eleven:backup 2>/dev/null || true
fi
echo -e "${GREEN}✅ Image tagged${NC}"

# 5. Create symlink to latest
echo -e "\n${YELLOW}Creating latest symlink...${NC}"
rm -f data/backups/latest
ln -s $(basename $BACKUP_DIR) data/backups/latest
echo -e "${GREEN}✅ Latest symlink created${NC}"

# 6. Cleanup old backups (keep last 7)
echo -e "\n${YELLOW}Cleaning up old backups...${NC}"
cd data/backups
ls -t | tail -n +8 | xargs -r rm -rf
cd - > /dev/null
echo -e "${GREEN}✅ Cleanup complete${NC}"

echo -e "\n${GREEN}✅ Backup complete!${NC}"
du -sh $BACKUP_DIR
echo -e "${YELLOW}Backups location: data/backups/${NC}"
