#!/bin/bash
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}🔄 Rolling back Brain-Eleven...${NC}"

# 1. Stop current services
echo -e "\n${YELLOW}[1/4] Stopping services...${NC}"
docker-compose down
echo -e "${GREEN}✅ Services stopped${NC}"

# 2. Check for backup image
echo -e "\n${YELLOW}[2/4] Checking backup image...${NC}"
BACKUP_TAG="brain-eleven:backup"
if docker image inspect $BACKUP_TAG > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Backup image found${NC}"
    docker tag $BACKUP_TAG brain-eleven:latest
else
    echo -e "${YELLOW}⚠️  No backup image found${NC}"
fi

# 3. Restore data if backup exists
echo -e "\n${YELLOW}[3/4] Checking for data backups...${NC}"
if [ -f "data/backups/latest/database.sql.gz" ]; then
    echo -e "${YELLOW}Restoring database...${NC}"
    docker-compose up -d postgres
    sleep 5
    gunzip -c data/backups/latest/database.sql.gz | \
        docker-compose exec -T postgres psql -U brain -d brain_eleven
    echo -e "${GREEN}✅ Database restored${NC}"
fi

# 4. Start services
echo -e "\n${YELLOW}[4/4] Starting services...${NC}"
docker-compose up -d
echo -e "${GREEN}✅ Services started${NC}"

echo -e "\n${GREEN}✅ Rollback complete!${NC}"
docker-compose ps
echo -e "\n${YELLOW}System restored to previous version${NC}"
