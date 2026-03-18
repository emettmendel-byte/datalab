SHELL := /bin/bash

.PHONY: dev backend frontend

backend:
	uvicorn app.main:app --reload --reload-dir app --port 8000

frontend:
	cd frontend && npm run dev

dev:
	@trap 'echo ""; echo "Stopping backend + frontend..."; kill 0' INT TERM EXIT; \
	echo "Starting backend on http://localhost:8000"; \
	echo "Starting frontend on http://localhost:5173"; \
	(uvicorn app.main:app --reload --reload-dir app --port 8000) & \
	(cd frontend && npm run dev) & \
	wait
