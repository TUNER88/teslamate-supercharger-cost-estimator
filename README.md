# TeslaMate Supercharger Cost Estimator

[![CI](https://github.com/TUNER88/teslamate-supercharger-cost-estimator/actions/workflows/ci.yml/badge.svg)](https://github.com/TUNER88/teslamate-supercharger-cost-estimator/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/TUNER88/teslamate-supercharger-cost-estimator)](https://github.com/TUNER88/teslamate-supercharger-cost-estimator/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)

Estimate Supercharger session costs in [TeslaMate](https://github.com/teslamate-org/teslamate) from **public** published rates — **no Tesla account login**.

**Covers every car on your TeslaMate instance**, not only vehicles you own. Shared and fleet cars get the same estimates as long as their Supercharging sessions are logged in TeslaMate. Invoice importers usually cannot do that, because they need access to that account’s Tesla invoices.

Rates come from [SuC Tracker](https://suc-tracker.eu/) (`/data/europe.json`). The tool matches finished charging sessions to nearby Superchargers and writes an estimated total into `charging_processes.cost`.

See [CHANGELOG.md](CHANGELOG.md) for release history.

## Estimate vs billed cost

| | This tool | Invoice importers (e.g. ownership-API tools) |
|--|-----------|-----------------------------------------------|
| Tesla account | Not needed | Required |
| Shared / fleet / all cars in TeslaMate | **Yes** — any session in the database | Only cars whose invoices you can access |
| Source | Public station tariffs | Your Tesla invoices |
| Idle / congestion fees | Not included | Included when billed |
| Membership / credits | Uses published Tesla-owner tariff | Exact billed amount |
| Accuracy | Good approximation | Exact |

Keep home energy pricing (e.g. TeslaMateAgile) separate.

## How it works

1. Download (and cache) Europe Supercharger tariffs.
2. Load finished TeslaMate sessions with `cost IS NULL` (default) for **all cars** in the database.
3. Match each session to the nearest priced station within ~400 m (geofence or position coordinates).
4. Pick the **time-of-use (TOU)** €/kWh window for the session start (station timezone). TOU means the published rate can change by clock time at that station (for example cheaper at night, more expensive during the day).
5. Set `cost = energy_kWh × rate` (uses the larger of `charge_energy_used` / `charge_energy_added`).

Sessions that **start in one TOU window and end in another** are **skipped by default** (the tool does not split energy across rates). Opt in with `ALLOW_CROSS_TOU=true` or `--allow-cross-tou` to price the whole session at the start-window rate.

Price integers in the public feed are **micro-units** (e.g. `420000` → `0.42 EUR/kWh`).

## Use the Docker image (recommended)

Published image:

`ghcr.io/tuner88/teslamate-supercharger-cost-estimator:latest`

Prefer a pinned tag in production:

`ghcr.io/tuner88/teslamate-supercharger-cost-estimator:0.2.0`

Also published: `0.2` (latest patch on that minor) and `sha-<commit>`.

If the first pull fails with `unauthorized`, open the package on GitHub → **Package settings** → set visibility to **Public** (or `docker login ghcr.io` with a token that can read packages).

### 1. Add the service to your TeslaMate Compose file

```bash
mkdir -p suc-estimator-cache
```

Paste this under `services:` (same file as your `database` service). Full copy also in [`deploy/docker-compose.snippet.yml`](deploy/docker-compose.snippet.yml):

```yaml
  suc-estimator:
    image: ghcr.io/tuner88/teslamate-supercharger-cost-estimator:0.2.0
    container_name: teslamate-suc-estimator
    restart: "no"
    depends_on:
      - database
    environment:
      - DATABASE_PASS=${DATABASE_PASS}
    volumes:
      - ./suc-estimator-cache:/cache
```

Only `DATABASE_PASS` is required (same Postgres password as TeslaMate). Other settings use built-in defaults (see [Environment variables](#environment-variables)). A normal run **writes** costs; use `DRY_RUN=true` or `--dry-run` for a preview.

### 2. Pull and run

```bash
docker compose pull suc-estimator
docker compose run --rm -e DRY_RUN=true suc-estimator
docker compose run --rm suc-estimator
```

Check the image/tool version:

```bash
docker compose run --rm suc-estimator --version
```

The first command previews without writing. The second fills `charging_processes.cost` where it is still null (for every car in that TeslaMate DB).

### 3. Schedule (optional)

Twice daily is enough:

```cron
0 6,18 * * * cd /path/to/teslamate && docker compose run --rm suc-estimator
```

### Build from source (optional)

```bash
git clone https://github.com/TUNER88/teslamate-supercharger-cost-estimator.git
```

In the Compose service, replace `image: ...` with `build: ./teslamate-supercharger-cost-estimator`, then:

```bash
docker compose build suc-estimator
docker compose run --rm -e DRY_RUN=true suc-estimator
docker compose run --rm suc-estimator
```

## Environment variables

| Variable | Required | Default | Meaning |
|----------|----------|---------|---------|
| `DATABASE_PASS` | **Yes** | — | Postgres password (`DATABASE_PASSWORD` also accepted) |
| `DATABASE_HOST` | No | `database` | Postgres host (Compose service name) |
| `DATABASE_PORT` | No | `5432` | Postgres port |
| `DATABASE_NAME` | No | `teslamate` | Database name |
| `DATABASE_USER` | No | `teslamate` | Database user |
| `PRICE_SOURCE_URL` | No | `https://suc-tracker.eu/data/europe.json` | Public rates URL |
| `PRICING_FAMILY` | No | `tesla` | `tesla` or `nonTesla` |
| `MATCH_RADIUS_M` | No | `400` | Max metres to match a station |
| `LOOKBACK_DAYS` | No | `90` | How far back to scan |
| `OVERWRITE_EXISTING` | No | `false` | Also rewrite non-null costs |
| `ALLOW_CROSS_TOU` | No | `false` | If `true`, estimate sessions that cross a time-of-use (TOU) rate change using the **start-time** rate (skipped by default) |
| `DRY_RUN` | No | `false` | If `true`, log estimates without writing to the database |
| `CACHE_DIR` | No | `/cache` | Directory for the rates cache |
| `CACHE_TTL_SECONDS` | No | `43200` | Rate cache lifetime (12 hours) |

CLI flags mirror these (`--version`, `--dry-run`, `--lookback-days`, `--match-radius-m`, `--overwrite`, `--allow-cross-tou`, …).

## Versioning

This project uses [Semantic Versioning](https://semver.org/):

- **Source of truth:** `version` in [`pyproject.toml`](pyproject.toml)
- **Changelog:** [`CHANGELOG.md`](CHANGELOG.md)
- **CLI:** `suc-estimator --version`
- **Docker (every merge to `main`):** `latest`, `X.Y.Z`, `X.Y`, and `sha-<commit>`

### Automated release

On every merge to `main`, CI:

1. Publishes the Docker image tags above
2. Reads the version from `pyproject.toml`
3. If GitHub Release `vX.Y.Z` does **not** exist yet, creates the tag and the release automatically

So a release is: bump `pyproject.toml` + update `CHANGELOG.md`, open a PR, merge when CI is green.

## Contributing

**All changes go through a pull request** — including docs and tiny fixes. Direct pushes to `main` are blocked.

1. Branch from `main`
2. Open a PR
3. Wait for the **test** check to pass
4. Merge the PR (no extra reviewer required on this solo repo)

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
suc-estimator --version
```

## Limitations

- Energy-only estimate (no idle fees).
- Public coverage depends on SuC Tracker (strong in Europe).
- Sessions without coordinates cannot be matched.
- Home / destination chargers should stay on Agile or geofence cost settings; this tool only fills costs for sessions near a known Supercharger.

## License

MIT
