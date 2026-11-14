# Render (free) / any Docker host. One container: FastAPI serves the API at /api and the built UI at /.
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# The engine team's real C compiler (vendored, pinned commit in engine/c_front/VERSION): `yogc` makes the decisions and
# `lexdump` feeds the compiler explorer. Only the compiled binaries are copied into the runtime image, so the final
# image carries no compiler. Built on bookworm so it runs on newer glibc.
FROM gcc:13-bookworm AS cbuild
WORKDIR /src
COPY engine/c_front/ ./
RUN gcc -std=c11 -O2 -Wall -Wextra -I src src/lexer/lexer.c tools/lexdump.c -o /lexdump \
 && gcc -std=c11 -O2 -I src -I include src/lexer/lexer.c src/parser/*.c src/sema/*.c src/ir/*.c src/vm/*.c src/api/yog.c tools/yogc.c -o /yogc

# Downloadable yogc packages for the /download page: Windows installer (NSIS) + zip, static Linux tarball, checksums.
# Built from the same vendored engine/c_front, cross-compiled with mingw-w64; see scripts/build_downloads.sh.
FROM debian:bookworm AS dist
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends gcc libc6-dev gcc-mingw-w64-x86-64 nsis zip \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY engine/c_front/ engine/c_front/
COPY packaging/ packaging/
COPY scripts/build_downloads.sh scripts/build_downloads.sh
RUN bash scripts/build_downloads.sh /dist

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
COPY --from=cbuild /yogc /app/bin/yogc
COPY --from=dist /dist /app/downloads
# Deployed default is the C engine (a missing/broken yogc is a startup error, never a silent fallback to Python).
ENV LLM_PROVIDER=fake YOG_ENGINE=c YOG_YOGC=/app/bin/yogc YOG_LEXDUMP=/app/bin/lexdump YOG_DOWNLOADS_DIR=/app/downloads
EXPOSE 10000
# Render sets $PORT; default 10000 for local `docker run`
CMD ["sh", "-c", "uv run --no-sync python -m uvicorn app.asgi:app --host 0.0.0.0 --port ${PORT:-10000}"]
