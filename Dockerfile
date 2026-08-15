# throughline service: FastAPI + the built web bundle in one image.
# HydraDB runs as its own container (see docker-compose.yml) — we talk to it over
# HTTP and never link its code, which is what keeps this repo's licence separate
# from HydraDB's AGPL-3.0.

FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/pnpm-lock.yaml* ./
RUN corepack enable && pnpm install --frozen-lockfile || pnpm install
COPY web/ ./
RUN pnpm build

FROM python:3.12-slim
WORKDIR /app

COPY pyproject.toml ./
COPY loader ./loader
COPY server ./server
COPY mcp_server ./mcp_server
COPY eval_harness ./eval_harness
RUN pip install --no-cache-dir -e .

COPY --from=web /web/dist ./web/dist

ENV HYDRADB_URL=http://hydradb:8443 \
    THROUGHLINE_WORKERS=6 \
    PORT=8000

EXPOSE 8000
CMD ["sh", "-c", "uvicorn server.app:app --host 0.0.0.0 --port ${PORT}"]
