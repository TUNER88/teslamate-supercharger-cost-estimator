FROM python:3.12-slim

ARG VERSION=0.0.0
LABEL org.opencontainers.image.title="teslamate-supercharger-cost-estimator" \
      org.opencontainers.image.description="Estimate TeslaMate Supercharger costs from public rates" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.source="https://github.com/TUNER88/teslamate-supercharger-cost-estimator"

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .

ENV CACHE_DIR=/cache \
    TZ=Europe/Berlin \
    SUC_ESTIMATOR_VERSION=${VERSION}
VOLUME ["/cache"]

ENTRYPOINT ["suc-estimator"]
# No default args: a plain `docker compose run` writes costs.
# Pass --dry-run (or DRY_RUN=true) for a preview.
