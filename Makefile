.PHONY: help build up down logs test backup rollback clean deploy health

help:
	@echo "Brain-Eleven v3 - Make Commands"
	@echo "================================"
	@echo "make build      - Build Docker image"
	@echo "make up         - Start all services"
	@echo "make down       - Stop all services"
	@echo "make restart    - Restart all services"
	@echo "make logs       - View service logs"
	@echo "make test       - Run test suite"
	@echo "make health     - Check service health"
	@echo "make backup     - Create backup"
	@echo "make rollback   - Rollback to previous version"
	@echo "make deploy     - Full deployment"
	@echo "make clean      - Remove all containers and volumes"

build:
	docker build -t brain-eleven:latest .
	@echo "✅ Docker image built"

up:
	docker-compose up -d
	@echo "✅ Services started"

down:
	docker-compose down
	@echo "✅ Services stopped"

restart:
	docker-compose restart
	@echo "✅ Services restarted"

logs:
	docker-compose logs -f app

test:
	docker-compose exec app pytest tests/ -v

health:
	@echo "Checking service health..."
	@curl -s http://localhost:8000/health | jq . && echo "✅ API healthy" || echo "❌ API unhealthy"
	@docker-compose exec redis redis-cli ping > /dev/null && echo "✅ Redis healthy" || echo "❌ Redis unhealthy"
	@docker-compose exec postgres psql -U brain -c "SELECT 1" > /dev/null && echo "✅ PostgreSQL healthy" || echo "❌ PostgreSQL unhealthy"

backup:
	@bash backup.sh

rollback:
	@bash rollback.sh

deploy:
	@bash deploy.sh

clean:
	docker-compose down -v
	rm -rf data/
	@echo "✅ Cleaned up all containers and volumes"

ps:
	docker-compose ps

shell-api:
	docker-compose exec app bash

shell-postgres:
	docker-compose exec postgres psql -U brain -d brain_eleven

redis-cli:
	docker-compose exec redis redis-cli

.DEFAULT_GOAL := help
