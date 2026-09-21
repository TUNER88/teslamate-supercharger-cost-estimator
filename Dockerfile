FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .

ENV CACHE_DIR=/cache \
    TZ=Europe/Berlin
VOLUME ["/cache"]

ENTRYPOINT ["suc-estimator"]
# No default args: a plain `docker compose run` writes costs.
# Pass --dry-run explicitly when you only want a preview.
