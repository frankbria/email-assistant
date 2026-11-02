# Build from the repo root: docker build -f backend/Dockerfile .
FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv

WORKDIR /app/backend
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/backend/.venv/bin:$PATH"

# Dependencies first so code-only changes reuse this layer.
# uv --locked needs every path dependency's project, dev-only ones included.
COPY packages /app/packages
COPY plugins /app/plugins
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY backend/app ./app

USER nobody
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
