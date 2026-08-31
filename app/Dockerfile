# --- Build stage: install deps into an isolated target dir ---
FROM python:3.12-slim AS build
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/install -r requirements.txt

# --- Runtime stage: minimal image, no build tools, non-root user ---
FROM python:3.12-slim
WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY --from=build /install /usr/local/lib/python3.12/site-packages
COPY app.py .

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

USER app
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz')" || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "app:app"]
