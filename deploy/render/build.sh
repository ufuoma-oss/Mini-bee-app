#!/bin/bash
# Build script for Render deployment
# This script runs during the Docker build process

set -e

echo "=========================================="
echo "Building CoPaw for Render deployment"
echo "=========================================="

# Print environment info
echo "Python version: $(python3 --version)"
echo "Pip version: $(pip --version)"
echo "Working directory: $(pwd)"

# Verify console build
if [ -d "src/copaw/console" ]; then
    echo "Console frontend found"
    ls -la src/copaw/console/ | head -10
else
    echo "WARNING: Console frontend not found!"
fi

# Verify source files
echo "Source files:"
ls -la src/copaw/ | head -10

echo "=========================================="
echo "Build completed successfully!"
echo "=========================================="
