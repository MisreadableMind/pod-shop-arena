# Two stages: build the frontend with node, run everything from python.
# The API serves the built bundle itself, so a deployment is one service plus a
# database — no separate static site, no CORS to get wrong.

FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm ci
COPY web/ ./
RUN npm run build


FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.6.10 /uv /bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/usr/local

WORKDIR /app

# Dependencies first, so a code change does not reinstall the world.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY core/ ./core/
COPY adapters/ ./adapters/
COPY api/ ./api/
COPY worker/ ./worker/
COPY verifier/ ./verifier/
COPY demo/ ./demo/
COPY scripts/ ./scripts/
RUN uv sync --frozen --no-dev

COPY --from=web /web/dist ./web/dist

# Blobs are write-once evidence. On Render this is a mounted disk; set the S3
# variables instead if you would rather not depend on one.
ENV PODARENA_BLOB_DIR=/data/blobs
RUN mkdir -p /data/blobs

EXPOSE 8000
CMD ["sh", "scripts/start.sh"]
