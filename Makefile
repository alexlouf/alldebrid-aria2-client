.PHONY: help pull up down restart logs shell test clean dev-up dev-down dev-logs dev-build dev-rebuild stats health

help:
	@echo "AllDebrid Client - Makefile commands:"
	@echo ""
	@echo "Production (using pre-built image):"
	@echo "  make pull          - Pull latest image from GitHub Container Registry"
	@echo "  make up            - Start services with pre-built image"
	@echo "  make down          - Stop services"
	@echo "  make restart       - Restart services"
	@echo "  make logs          - Show logs"
	@echo ""
	@echo "Development (building locally):"
	@echo "  make dev-build     - Build Docker image locally"
	@echo "  make dev-up        - Start services with local build"
	@echo "  make dev-down      - Stop development services"
	@echo "  make dev-logs      - Show development logs"
	@echo "  make dev-rebuild   - Rebuild and restart development services"
	@echo ""
	@echo "Utilities:"
	@echo "  make shell         - Open shell in container"
	@echo "  make test          - Run tests"
	@echo "  make stats         - Show Docker stats"
	@echo "  make health        - Check service health"
	@echo "  make clean         - Clean up containers and volumes"

# Production commands (using pre-built image)
pull:
	docker-compose pull

up:
	docker-compose up -d

down:
	docker-compose down

restart:
	docker-compose restart

logs:
	docker-compose logs -f alldebrid-client

# Development commands (building locally)
dev-build:
	docker-compose -f docker-compose.dev.yml build

dev-up:
	docker-compose -f docker-compose.dev.yml up -d

dev-down:
	docker-compose -f docker-compose.dev.yml down

dev-logs:
	docker-compose -f docker-compose.dev.yml logs -f alldebrid-client-dev

dev-rebuild:
	docker-compose -f docker-compose.dev.yml up -d --build

# Utility commands
shell:
	@docker exec -it alldebrid-client sh 2>/dev/null || docker exec -it alldebrid-client-dev sh

test:
	@docker exec alldebrid-client pytest 2>/dev/null || docker exec alldebrid-client-dev pytest

stats:
	@docker stats alldebrid-client 2>/dev/null || docker stats alldebrid-client-dev

health:
	@curl -s http://localhost:6500/health | python3 -m json.tool

clean:
	docker-compose down -v
	docker-compose -f docker-compose.dev.yml down -v
	docker system prune -f
