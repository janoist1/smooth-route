# Makefile for Smooth Route project
# Managing both Frontend (React/Vite) and Backend (FastAPI)

PYTHON_VENV = .venv
PYTHON = $(PYTHON_VENV)/bin/python
UVICORN = $(PYTHON_VENV)/bin/uvicorn

.PHONY: setup backend frontend dev lint clean retrain postprocess test-ml

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
	$(PYTHON) scripts/clear_jobs.py

list-jobs:
	$(PYTHON) scripts/list_jobs.py

clean-orphans:
	@echo "🧹 Cleaning orphaned points..."
	DATABASE_URL=postgresql://postgres:postgres@localhost:5433/smooth_route \
	$(PYTHON) scripts/clean_orphaned_points.py

lint:
	@echo "🧹 Linting..."
	cd frontend && npm run lint
	$(PYTHON) -m ruff check backend

clean:
	rm -rf frontend/dist
	rm -rf frontend/node_modules
	rm -rf $(PYTHON_VENV)
	find . -type d -name "__pycache__" -exec rm -rf {} +

# One-command retrain (ml/retrain.py): new owner labels -> features -> spatial
# gate -> ml/cache/rqi_model_candidate.joblib + summary. Never replaces the live
# ml/cache/rqi_model.joblib; promotion is printed for a human to run.
# Flags: make retrain ARGS="--force"   (also --min-new N, --no-extract, --labels CSV)
retrain:
	$(PYTHON) ml/retrain.py $(ARGS)

# Post-process newly collected frames (frame quality -> DINO re-score -> segments
# -> collector report). Incremental, idempotent, safe while the collector runs.
postprocess:
	bash backend/scripts/postprocess_new_frames.sh

# Unit tests for the ML promotion pipeline (synthetic data; no torch/MPS/images, ~20 s)
test-ml:
	$(PYTHON) -m pytest -q ml/tests
