# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.11.16

FROM python:${PYTHON_VERSION}-slim-bookworm AS dependency-builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
COPY requirements.lock .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install -r requirements.lock

FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RAG_OBJECT_STORAGE_PATH=/app/data/objects

RUN groupadd --gid 10001 rag \
    && useradd --uid 10001 --gid rag --no-create-home --shell /usr/sbin/nologin rag

WORKDIR /app
COPY --from=dependency-builder /opt/venv /opt/venv
COPY alembic ./alembic
COPY alembic.ini pyproject.toml ./
COPY app ./app
COPY docker/entrypoint.sh /usr/local/bin/rag-entrypoint

RUN chmod 0555 /usr/local/bin/rag-entrypoint \
    && mkdir -p /app/data/objects \
    && chown -R rag:rag /app/data

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/live', timeout=3).read()"]

ENTRYPOINT ["rag-entrypoint"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
