# Backend image: serves BOTH the API and the worker (same code, different command).
# Build context: repository root.
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Dependencies first so code edits don't bust the layer cache.
COPY packages/groundtruth/pyproject.toml packages/groundtruth/README.md packages/groundtruth/
COPY packages/groundtruth/src packages/groundtruth/src
RUN pip install "./packages/groundtruth[api,db,genai]" psycopg[binary]

COPY apps ./apps
COPY cases ./cases
COPY configs ./configs
COPY data ./data

RUN useradd --create-home --uid 1000 app && chown -R app /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health')" || exit 1
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
