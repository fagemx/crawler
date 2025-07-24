# Use the official Python image from the Docker Hub
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the entire project context
COPY . .

# Install dependencies
# Note: This list should be maintained, but for now, it mirrors playwright's successful build
RUN pip install --no-cache-dir \
    fastapi>=0.104.0 \
    uvicorn>=0.24.0 \
    pydantic>=2.0.0 \
    pydantic-settings>=2.0.0 \
    python-dotenv>=1.0.0 \
    loguru>=0.7.2 \
    requests>=2.31.0 \
    beautifulsoup4>=4.12.3 \
    redis>=5.0.1 \
    psycopg2-binary>=2.9.9 \
    asyncpg>=0.29.0 \
    "uvicorn[standard]" \
    celery>=5.3.6 \
    flower>=2.0.1 \
    google-generativeai>=0.5.4 \
    sse-starlette>=1.6.5 

# Set Python path
ENV PYTHONPATH=/app

# Expose the port the app runs on
EXPOSE 8004

# Command to run the application
CMD ["uvicorn", "agents.jina.main:app", "--host", "0.0.0.0", "--port", "8004", "--reload"] 