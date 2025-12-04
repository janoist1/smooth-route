#!/bin/bash
# Wrapper script to run the CLI
# Usage: ./cli.sh [command] [args]

# Ensure we are in the project root or adjust paths
cd "$(dirname "$0")"

# Check if .env exists, if not warn
if [ ! -f .env ]; then
    echo "Warning: .env file not found in root. Please create one with GOOGLE_MAPS_API_KEY."
fi

# Run the python module
# We assume python3 is available and dependencies are installed.
# Ideally this should run inside the docker container or venv.

if [ "$1" == "docker" ]; then
    shift
    docker-compose run --rm backend python -m app.cli "$@"
else
    # Local run (requires venv setup)
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
    elif [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
    else
        echo "Error: Virtual environment not found. Please run 'python3 -m venv .venv && .venv/bin/pip install -e backend/'"
        exit 1
    fi
    
    export PYTHONPATH=$PYTHONPATH:$(pwd)/backend
    python -m app.cli "$@"
fi
