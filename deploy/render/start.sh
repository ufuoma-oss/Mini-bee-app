#!/bin/bash
# Start script for Mini Bee Backend (Render deployment)
# Render automatically sets the PORT environment variable

set -e

# Use Render's PORT or default to 8088
export PORT="${PORT:-8088}"

# Ensure working directory exists
mkdir -p ${COPAW_WORKING_DIR:-/app/working}

# Initialize Mini Bee if not already initialized
if [ ! -f "${COPAW_WORKING_DIR:-/app/working}/config.json" ]; then
    echo "Initializing Mini Bee..."
    copaw init --defaults --accept-security
fi

echo "=========================================="
echo "Mini Bee Backend"
echo "=========================================="
echo "Port: ${PORT}"
echo "Working directory: ${COPAW_WORKING_DIR:-/app/working}"
echo "Enabled channels: ${COPAW_ENABLED_CHANNELS:-console}"
echo "=========================================="

# Start the Mini Bee API application
exec copaw app --host 0.0.0.0 --port ${PORT}
