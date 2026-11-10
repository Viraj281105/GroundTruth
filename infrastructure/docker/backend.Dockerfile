# Backend image: serves BOTH the API and the worker (same code, different command).
# Build context: repository root.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Dependencies first so code edits don't bust the layer cache.
COPY packages/groundtruth/pyproject.toml packages/groundtruth/README.md packages/groundtruth/
COPY packages/groundtruth/src packages/groundtruth/src
# "ingest" carries the satellite ingestion libraries; without it the worker cannot run an
# observation request (it fails on the first import). rasterio's wheel bundles GDAL but links the
# system libexpat, which the slim base image does not ship. The import check fails the build,
# not a user's request, if either goes missing again.
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install "./packages/groundtruth[api,db,genai,ingest]" psycopg[binary] \
    && python -c "import rasterio, pystac_client, planetary_computer"

# Only the two backend entrypoints. apps/web is a separate image and does not belong here.
COPY apps/api ./apps/api
COPY apps/worker ./apps/worker
COPY cases ./cases
COPY configs ./configs
COPY data ./data

# Directories written at runtime. The API and the worker are separate containers, so compose
# mounts shared volumes here; creating them now makes those volumes inherit the app user's ownership.
RUN mkdir -p cases/boundaries/projects data/project_documents data/processed
RUN useradd --create-home --uid 1000 app && chown -R app /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health')" || exit 1
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
