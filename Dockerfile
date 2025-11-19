# Dockerfile for Agent Memory Service Interactive Demo
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml ./
COPY README.md ./

# Copy source code
COPY memory/ ./memory/
COPY client/ ./client/
COPY server/ ./server/
COPY agent/ ./agent/
COPY demo/ ./demo/

# Install Python dependencies
RUN pip install --no-cache-dir -e . && \
    pip install --no-cache-dir streamlit plotly pandas

# Expose Streamlit port
EXPOSE 8501

# Set environment variables for Streamlit
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Run the Streamlit app
CMD ["streamlit", "run", "demo/interactive_demo_live.py", "--server.port=8501", "--server.address=0.0.0.0"]
