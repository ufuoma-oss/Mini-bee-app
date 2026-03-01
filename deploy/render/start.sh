#!/bin/bash
# Start script for Render deployment
# Render automatically sets the PORT environment variable

set -e

# Use Render's PORT or default to 8088
export PORT="${PORT:-8088}"

# Ensure working directory exists
mkdir -p ${COPAW_WORKING_DIR:-/app/working}

# Initialize CoPaw if not already initialized
if [ ! -f "${COPAW_WORKING_DIR:-/app/working}/config.json" ]; then
    echo "Initializing CoPaw..."
    copaw init --defaults --accept-security
fi

echo "Starting CoPaw on port ${PORT}..."
echo "Working directory: ${COPAW_WORKING_DIR:-/app/working}"
echo "Enabled channels: ${COPAW_ENABLED_CHANNELS:-console}"

# Start the CoPaw application
exec copaw app --host 0.0.0.0 --port ${PORT}
