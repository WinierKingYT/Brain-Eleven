#!/bin/bash
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}🚀 Brain-Eleven v3 Deployment${NC}"
echo "================================"

# 1. PRE-FLIGHT CHECKS
echo -e "\n${YELLOW}[1/7] Pre-flight checks...${NC}"
command -v docker &> /dev/null || { echo -e "${RED}❌ Docker not found${NC}"; exit 1; }
command -v docker-compose &> /dev/null || { echo -e "${RED}❌ Docker Compose not found${NC}"; exit 1; }
test -f Dockerfile || { echo -e "${RED}❌ Dockerfile not found${NC}"; exit 1; }
test -f docker-compose.yml || { echo -e "${RED}❌ docker-compose.yml not found${NC}"; exit 1; }
echo -e "${GREEN}✅ All pre-flight checks passed${NC}"

# 2. BUILD DOCKER IMAGE
echo -e "\n${YELLOW}[2/7] Building Docker image...${NC}"
DOCKER_TAG="brain-eleven:$(git rev-parse --short HEAD 2>/dev/null || echo 'local')"
docker build -t $DOCKER_TAG -t brain-eleven:latest .
echo -e "${GREEN}✅ Image built: $DOCKER_TAG${NC}"

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
POSTGRES_PASSWORD=$(openssl rand -base64 32 2>/dev/null || echo "postgres")
POSTGRES_DB=brain_eleven
EOF
    echo -e "${GREEN}✅ .env created (edit with your values)${NC}"
else
    echo -e "${GREEN}✅ .env already exists${NC}"
fi

# 4. VOLUME SETUP
echo -e "\n${YELLOW}[4/7] Setting up volumes...${NC}"
mkdir -p data/vault data/postgres data/redis
chmod 755 data/* 2>/dev/null || true
echo -e "${GREEN}✅ Volumes ready${NC}"

# 5. START SERVICES
echo -e "\n${YELLOW}[5/7] Starting services...${NC}"
docker-compose up -d
echo -e "${GREEN}✅ Services started${NC}"

# 6. HEALTH CHECKS
echo -e "\n${YELLOW}[6/7] Health checks...${NC}"
sleep 5
for i in {1..30}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✅ API healthy${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}❌ API health check failed${NC}"
        exit 1
    fi
    echo "   Waiting for API... ($i/30)"
    sleep 1
done

# 7. FINAL STATUS
echo -e "\n${YELLOW}[7/7] Final status...${NC}"
docker-compose ps
echo -e "\n${GREEN}✅ Deployment complete!${NC}"
echo -e "\n${YELLOW}Access:${NC}"
echo "  API:        http://localhost:8000"
echo "  Docs:       http://localhost:8000/docs"
echo "  Redis:      localhost:6379"
echo ""
echo -e "${GREEN}🎉 Brain-Eleven v3 is LIVE!${NC}"
