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

# Core Services
backend:
	@echo "🚀 Starting Backend (FastAPI)..."
	cd backend && DATABASE_URL=postgresql://postgres:postgres@localhost:5433/smooth_route \
	../$(UVICORN) app.main:app --host 0.0.0.0 --port 8000 --reload

frontend:
	@echo "🎨 Starting Frontend (Vite)..."
	cd frontend && npm run dev

dev:
	@echo "🌟 Starting all services sensibly (Ctrl+C to stop all)..."
	@cd frontend && npx concurrently \
		-n "BACKEND,FRONTEND" \
		-c "blue,magenta" \
		"cd ../backend && DATABASE_URL=postgresql://postgres:postgres@localhost:5433/smooth_route ../$(UVICORN) app.main:app --host 0.0.0.0 --port 8000 --reload" \
		"npm run dev"

# Data & Training Management
reimport-images:
	@echo "🔄 Re-importing all images with -20 pitch..."
	DATABASE_URL=postgresql://postgres:postgres@localhost:5433/smooth_route \
	$(PYTHON) scripts/redownload_images.py

purge-data:
	@echo "🗑️ Purging training data..."
	DATABASE_URL=postgresql://postgres:postgres@localhost:5433/smooth_route \
	$(PYTHON) scripts/purge_data.py

download-models:
	@echo "📦 Downloading and building AI models..."
	$(PYTHON) scripts/download_models.py

# Analysis & Utility
clear-jobs:
	@echo "🧹 Clearing background jobs..."
	DATABASE_URL=postgresql://postgres:postgres@localhost:5433/smooth_route \
	$(PYTHON) clear_jobs.py

list-jobs:
	$(PYTHON) list_jobs.py

analyze-calibration:
	$(PYTHON) analyze_calibration.py

verify-real:
	$(PYTHON) verify_real_images.py

lint:
	@echo "🧹 Linting..."
	cd frontend && npm run lint
	$(PYTHON) -m ruff check backend

clean:
	rm -rf frontend/dist
	rm -rf frontend/node_modules
	rm -rf $(PYTHON_VENV)
	find . -type d -name "__pycache__" -exec rm -rf {} +
