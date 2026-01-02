# Makefile for Smooth Route project
# Managing both Frontend (React/Vite) and Backend (FastAPI)

PYTHON_VENV = .venv
PYTHON = $(PYTHON_VENV)/bin/python
UVICORN = $(PYTHON_VENV)/bin/uvicorn

.PHONY: setup backend frontend dev lint clean

setup:
	@echo "🔍 Setting up environments..."
	@if [ ! -d "$(PYTHON_VENV)" ]; then python3 -m venv $(PYTHON_VENV); fi
	$(PYTHON) -m pip install --upgrade pip
	cd backend && ../$(PYTHON) -m pip install -e .
	cd frontend && npm install

backend:
	@echo "🚀 Starting Backend..."
	cd backend && DATABASE_URL=postgresql://postgres:postgres@localhost:5433/smooth_route \
	../$(UVICORN) app.main:app --host 0.0.0.0 --port 8000 --reload

frontend:
	@echo "🎨 Starting Frontend..."
	cd frontend && npm run dev

dev:
	@echo "🌟 Starting all services..."
	# Use foreman, or just run in parallel if simple
	# For now, suggest running in separate terminals or use a tool if available
	@echo "Please run 'make backend' and 'make frontend' in separate terminals."

lint:
	@echo "🧹 Linting..."
	cd frontend && npm run lint
	$(PYTHON) -m ruff check backend

clean:
	rm -rf frontend/dist
	rm -rf frontend/node_modules
	rm -rf $(PYTHON_VENV)
	find . -type d -name "__pycache__" -exec rm -rf {} +
