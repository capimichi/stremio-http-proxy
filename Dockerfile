FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md alembic.ini ./
COPY alembic ./alembic
COPY stremio_http_proxy ./stremio_http_proxy
COPY templates ./templates
COPY static ./static

RUN pip install --no-cache-dir .

EXPOSE 8691

CMD ["python", "-m", "stremio_http_proxy.cli", "serve"]
