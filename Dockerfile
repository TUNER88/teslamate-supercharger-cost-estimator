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
    UPDATE_INTERVAL_SECONDS=3600 \
    SUC_ESTIMATOR_VERSION=${VERSION}
VOLUME ["/cache"]

ENTRYPOINT ["suc-estimator"]
# Default: loop every 3600s. For a one-shot run: -e UPDATE_INTERVAL_SECONDS=0
# Preview: -e DRY_RUN=true -e UPDATE_INTERVAL_SECONDS=0
