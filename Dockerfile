FROM python:3.12-slim

WORKDIR /app

# Install uv
RUN pip install --no-cache-dir uv

# Copy dependency files first (better cache)
COPY pyproject.toml ./
COPY uv.lock ./

# Install deps
RUN uv sync --frozen

# Copy code last
COPY app ./app
COPY ui ./ui
COPY data ./data

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
