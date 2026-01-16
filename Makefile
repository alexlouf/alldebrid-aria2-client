.PHONY: help build up down restart logs shell test clean

help:
	@echo "AllDebrid Client - Makefile commands:"
	@echo ""
	@echo "  make build    - Build Docker image"
	@echo "  make up       - Start services"
	@echo "  make down     - Stop services"
	@echo "  make restart  - Restart services"
	@echo "  make logs     - Show logs"
	@echo "  make shell    - Open shell in container"
	@echo "  make test     - Run tests"
	@echo "  make clean    - Clean up"

build:
	docker-compose build

up:
	docker-compose up -d

down:
	docker-compose down

restart:
	docker-compose restart

logs:
	docker-compose logs -f alldebrid-client

shell:
	docker exec -it alldebrid-client sh

test:
	docker exec alldebrid-client pytest

clean:
	docker-compose down -v
	docker system prune -f
