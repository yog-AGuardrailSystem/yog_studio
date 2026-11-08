# Render (free) / any Docker host. One container: FastAPI serves the API at /api and the built UI at /.
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# The engine team's real C lexer (vendored, pinned commit in engine/c_front/VERSION). Only the compiled binary is
# copied into the runtime image, so the final image carries no compiler. Built on bookworm so it runs on newer glibc.
FROM gcc:13-bookworm AS cbuild
WORKDIR /src
COPY engine/c_front/ ./
RUN gcc -std=c11 -O2 -Wall -Wextra -I src src/lexer/lexer.c tools/lexdump.c -o /lexdump

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
COPY --from=cbuild /lexdump /app/bin/lexdump
ENV LLM_PROVIDER=fake YOG_ENGINE=python YOG_LEXDUMP=/app/bin/lexdump
EXPOSE 10000
# Render sets $PORT; default 10000 for local `docker run`
CMD ["sh", "-c", "uv run --no-sync python -m uvicorn app.asgi:app --host 0.0.0.0 --port ${PORT:-10000}"]
