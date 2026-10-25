# Render (free) / any Docker host. One container: FastAPI serves the API at /api and the built UI at /.
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UV_LINK_MODE=copy
RUN pip install --no-cache-dir uv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev
COPY backend/ ./
COPY engine/ /app/engine/
COPY examples/ /app/examples/
COPY --from=web /web/dist /app/frontend/dist
ENV LLM_PROVIDER=fake YOG_ENGINE=python
EXPOSE 10000
# Render sets $PORT; default 10000 for local `docker run`
CMD ["sh", "-c", "uv run --no-sync python -m uvicorn app.asgi:app --host 0.0.0.0 --port ${PORT:-10000}"]
