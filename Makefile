.PHONY: help install frontend-install db-up db-down migrate backfill link-github scrape-bitcointalk backfill-bitcointalk-history backend agents frontend dev dev-all test test-e2e test-all

# Silence ADK's "[EXPERIMENTAL] ..." startup warnings (they flag ADK-internal
# features we don't configure); everything else still surfaces normally.
export PYTHONWARNINGS := ignore:[EXPERIMENTAL]

help:
	@echo "make install           - install python dependencies"
	@echo "make db-up             - start the postgres container"
	@echo "make db-down           - stop the postgres container"
	@echo "make migrate           - apply database migrations"
	@echo "make backfill          - download the bitcoin-dev archive and load messages + people"
	@echo "make link-github       - link people to GitHub accounts, across all configured repos (core/knots/bips/secp256k1 -- knots' history heavily overlaps core's, so this now takes noticeably longer than a single-repo run)"
	@echo "make scrape-bitcointalk - ongoing BitcoinTalk crawl, recency-sorted (cron-friendly, catches new posts cheaply)"
	@echo "make backfill-bitcointalk-history - ONE-TIME full-history BitcoinTalk backfill, oldest topic first (slow discovery pass)"
	@echo "make backend           - run the backend API (foreground)"
	@echo "make agents            - run the ADK web UI (foreground)"
	@echo "make frontend          - run the frontend dev server (foreground)"
	@echo "make test              - run the Python test suite"
	@echo "make test-e2e          - run browser E2E tests with Playwright"
	@echo "make test-all          - run Python, frontend, and browser checks"
	@echo "make dev               - start db and apply migrations"
	@echo "make dev-all           - run backend + frontend + agents together (foreground, Ctrl+C stops all)"

install:
	pip install -r requirements.txt

frontend-install:
	cd frontend && npm install

db-up:
	cd db && docker compose --env-file ../.env up -d

db-down:
	cd db && docker compose --env-file ../.env down

migrate:
	python3 db/migrate.py

backfill:
	python3 scripts/backfill_mailing_list.py
	python3 scripts/backfill_early_archives.py

link-github:
	python3 scripts/link_github_contributors.py

scrape-bitcointalk:
	python3 scripts/scrape_bitcointalk.py

backfill-bitcointalk-history:
	python3 scripts/backfill_bitcointalk_history.py

# 8010, not uvicorn's default 8000 -- `adk web` also defaults to 8000, and
# `make dev-all` runs both backend and agents at once.
backend:
	uvicorn backend.main:app --reload --port 8010

agents:
	adk web agents

frontend:
	cd frontend && npm run dev

test:
	pytest -q

test-e2e:
	cd frontend && npm run test:e2e

test-all: test
	cd frontend && npm run lint
	cd frontend && npm run build
	cd frontend && npm run test:e2e

dev: db-up migrate
	@echo "Postgres is up and migrated. Run 'make backend' and 'make agents' in separate terminals."

dev-all:
	./scripts/dev.sh
