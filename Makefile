.PHONY: help install db-up db-down migrate backend agents dev

help:
	@echo "make install   - install python dependencies"
	@echo "make db-up     - start the postgres container"
	@echo "make db-down   - stop the postgres container"
	@echo "make migrate   - apply database migrations"
	@echo "make backend   - run the backend API (foreground)"
	@echo "make agents    - run the ADK agent web UI (foreground)"
	@echo "make dev       - start db and apply migrations"

install:
	pip install -r requirements.txt

db-up:
	cd db && docker compose up -d

db-down:
	cd db && docker compose down

migrate:
	python3 db/migrate.py

backend:
	uvicorn backend.main:app --reload

agents:
	adk web

dev: db-up migrate
	@echo "Postgres is up and migrated. Run 'make backend' and 'make agents' in separate terminals."
