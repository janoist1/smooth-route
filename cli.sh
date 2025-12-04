#!/bin/bash
# Wrapper script to run the Smooth Route CLI
# Usage: ./cli.sh [command] [args]
#        ./cli.sh docker [command] [args]  # Run in Docker

# Ensure we are in the project root
cd "$(dirname "$0")"

# Check if .env exists, if not warn
if [ ! -f .env ]; then
    echo "Warning: .env file not found in root. Please create one with GOOGLE_MAPS_API_KEY."
fi

# Run the CLI
if [ "$1" == "docker" ]; then
    shift
    docker-compose run --rm backend smooth-route "$@"
else
    # Local run (requires venv setup)
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
    elif [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
    else
        echo "Error: Virtual environment not found."
        echo "Please run: python3 -m venv .venv && source .venv/bin/activate && pip install -e backend/"
        exit 1
    fi
    
    # Use the installed CLI command if available, otherwise fallback to module
    if command -v smooth-route &> /dev/null; then
        smooth-route "$@"
    else
        export PYTHONPATH=$PYTHONPATH:$(pwd)/backend
        python -m app.cli "$@"
    fi
fi
