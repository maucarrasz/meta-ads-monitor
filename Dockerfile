FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /app
COPY requirements-worker.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements-worker.lock \
    && python -m playwright install --with-deps chromium \
    && useradd --create-home --uid 10001 worker \
    && chmod -R a+rX /ms-playwright
COPY ads_worker.py read_domain.py scraper.py ./
USER worker
EXPOSE 8080
CMD ["python", "ads_worker.py"]
