# Stage 1: Build stage
FROM python:3.11-slim as builder

WORKDIR /app

# Install poetry
RUN pip install poetry

# Copy only files needed for dependency installation
COPY pyproject.toml poetry.lock ./

# Install dependencies, without installing the project itself
# --no-root: don't install the project itself in this stage
# --without dev: don't install dev dependencies
RUN poetry install --no-root --without dev

# Stage 2: Final image
FROM python:3.11-slim

WORKDIR /app

# Copy python path
ENV PYTHONPATH=/app

# Copy virtual env from builder stage
COPY --from=builder /app/.venv /.venv

# Activate virtual env
ENV PATH="/app/.venv/bin:$PATH"

# Copy the rest of the application code
COPY . .

# Expose the port the app runs on
EXPOSE 8004

# Command to run the application
# Use reload for development, switch to gunicorn or similar for production
CMD ["uvicorn", "agents.jina.main:app", "--host", "0.0.0.0", "--port", "8004", "--reload"] 