# -----------------------------------------------------------------------------
# Dockerfile for Render Deployment
# Optimized for Render.com cloud platform
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Stage 1: Build console frontend
# -----------------------------------------------------------------------------
FROM node:20-slim AS console-builder
WORKDIR /app
COPY console/package*.json ./console/
RUN cd console && npm ci --include=dev
COPY console ./console
RUN cd console && npm run build

# -----------------------------------------------------------------------------
# Stage 2: Runtime image with Python and minimal dependencies
# -----------------------------------------------------------------------------
FROM python:3.12-slim-bookworm

# Avoid warnings by switching to noninteractive
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    git \
    # For Playwright browser automation
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    # Fonts for browser automation
    fonts-liberation \
    fonts-noto-color-emoji \
    # Clean up
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Environment variables
ENV NODE_ENV=production
ENV WORKSPACE_DIR=/app
ENV COPAW_WORKING_DIR=/app/working
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Available channels for this image
# Override at runtime with -e COPAW_ENABLED_CHANNELS=...
ARG COPAW_ENABLED_CHANNELS="console"
ENV COPAW_ENABLED_CHANNELS=${COPAW_ENABLED_CHANNELS}

WORKDIR ${WORKSPACE_DIR}

# Create virtual environment and install dependencies
COPY pyproject.toml setup.py README.md ./
COPY src ./src

# Inject console dist from build stage
COPY --from=console-builder /app/console/dist/ ./src/copaw/console/

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

# Install Playwright browsers (optional - uncomment if needed)
# RUN playwright install chromium --with-deps

# Create working directory
RUN mkdir -p ${COPAW_WORKING_DIR}

# Initialize CoPaw with default config
RUN copaw init --defaults --accept-security

# Create start script
COPY deploy/render/start.sh /start.sh
RUN chmod +x /start.sh

# Render sets PORT environment variable
# Default to 8088 if not set
ENV PORT=8088
EXPOSE 8088

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT}/ || exit 1

# Start the application
CMD ["/start.sh"]
