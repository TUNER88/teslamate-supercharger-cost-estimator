# TeslaMate Supercharger Cost Estimator

Estimate Supercharger session costs in [TeslaMate](https://github.com/teslamate-org/teslamate) from **public** published rates — **no Tesla account login**.

**Covers every car on your TeslaMate instance**, not only vehicles you own. Shared and fleet cars get the same estimates as long as their Supercharging sessions are logged in TeslaMate. Invoice importers usually cannot do that, because they need access to that account’s Tesla invoices.

Rates come from [SuC Tracker](https://suc-tracker.eu/) (`/data/europe.json`). The tool matches finished charging sessions to nearby Superchargers and writes an estimated total into `charging_processes.cost`.

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
4. Pick the time-of-use €/kWh window for the session start (station timezone).
5. Set `cost = energy_kWh × rate` (uses the larger of `charge_energy_used` / `charge_energy_added`).

Sessions that **start in one time-of-use window and end in another** are **skipped by default** (the tool does not split energy across rates). Opt in with `ALLOW_CROSS_TOU=true` or `--allow-cross-tou` to price the whole session at the start-window rate.

Price integers in the public feed are **micro-units** (e.g. `420000` → `0.42 EUR/kWh`).

## Use the Docker image (recommended)

Published image:

`ghcr.io/tuner88/teslamate-supercharger-cost-estimator:latest`

If the first pull fails with `unauthorized`, open the package on GitHub → **Package settings** → set visibility to **Public** (or `docker login ghcr.io` with a token that can read packages).

### 1. Add the service to your TeslaMate Compose file

Create a cache folder next to your compose file:

```bash
mkdir -p suc-estimator-cache
```

Paste this under `services:` (same file as your `database` service). Full copy also in [`deploy/docker-compose.snippet.yml`](deploy/docker-compose.snippet.yml):

```yaml
  suc-estimator:
    image: ghcr.io/tuner88/teslamate-supercharger-cost-estimator:latest
    container_name: teslamate-suc-estimator
    restart: "no"
    depends_on:
      - database
    environment:
      - DATABASE_HOST=database
      - DATABASE_PORT=5432
      - DATABASE_NAME=teslamate
      - DATABASE_USER=teslamate
      - DATABASE_PASS=${DATABASE_PASS}
      - PRICE_SOURCE_URL=https://suc-tracker.eu/data/europe.json
      - CACHE_DIR=/cache
      - CACHE_TTL_SECONDS=43200
      - PRICING_FAMILY=tesla
      - MATCH_RADIUS_M=400
      - LOOKBACK_DAYS=90
      - OVERWRITE_EXISTING=false
      - ALLOW_CROSS_TOU=false
      - TZ=Europe/Berlin
    volumes:
      - ./suc-estimator-cache:/cache
```

Set `DATABASE_PASS` to the same Postgres password TeslaMate uses.

### 2. Pull and run

```bash
docker compose pull suc-estimator
docker compose run --rm suc-estimator --dry-run
docker compose run --rm suc-estimator
```

`--dry-run` logs what would be written without changing the database. A normal run fills `charging_processes.cost` where it is still null (for every car in that TeslaMate DB).

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
docker compose run --rm suc-estimator --dry-run
```

## Configuration

| Variable | Default | Meaning |
|----------|---------|---------|
| `DATABASE_*` | TeslaMate defaults | Postgres connection |
| `PRICE_SOURCE_URL` | SuC Tracker Europe JSON | Public rates URL |
| `PRICING_FAMILY` | `tesla` | `tesla` or `nonTesla` |
| `MATCH_RADIUS_M` | `400` | Max metres to match a station |
| `LOOKBACK_DAYS` | `90` | How far back to scan |
| `OVERWRITE_EXISTING` | `false` | Also rewrite non-null costs |
| `ALLOW_CROSS_TOU` | `false` | If true, estimate sessions that cross a TOU rate change using the **start-time** rate (skipped by default) |
| `CACHE_TTL_SECONDS` | `43200` | Rate cache lifetime |

CLI flags mirror these (`--dry-run`, `--lookback-days`, `--match-radius-m`, `--overwrite`, `--allow-cross-tou`, …).

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Limitations

- Energy-only estimate (no idle fees).
- Public coverage depends on SuC Tracker (strong in Europe).
- Sessions without coordinates cannot be matched.
- Home / destination chargers should stay on Agile or geofence cost settings; this tool only fills costs for sessions near a known Supercharger.

## License

MIT
