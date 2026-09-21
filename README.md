# TeslaMate Supercharger Cost Estimator

Estimate Supercharger session costs in [TeslaMate](https://github.com/teslamate-org/teslamate) from **public** published rates — **no Tesla account login**.

Rates come from [SuC Tracker](https://suc-tracker.eu/) (`/data/europe.json`). The tool matches finished TeslaMate charging sessions to nearby Superchargers and writes an estimated total into `charging_processes.cost`.

## Estimate vs billed cost

| | This tool | Invoice importers (e.g. ownership-API tools) |
|--|-----------|-----------------------------------------------|
| Tesla account | Not needed | Required |
| Source | Public station tariffs | Your Tesla invoices |
| Idle / congestion fees | Not included | Included when billed |
| Membership / credits | Uses published Tesla-owner tariff | Exact billed amount |
| Accuracy | Good approximation | Exact |

Use this when you do not want to give a Tesla refresh token to a sidecar. Keep home energy pricing (e.g. TeslaMateAgile) separate.

## How it works

1. Download (and cache) Europe Supercharger tariffs.
2. Load finished TeslaMate sessions with `cost IS NULL` (default).
3. Match each session to the nearest priced station within ~400 m (geofence or position coordinates).
4. Pick the time-of-use €/kWh window for the session start (station timezone).
5. Set `cost = energy_kWh × rate` (uses the larger of `charge_energy_used` / `charge_energy_added`).

Price integers in the public feed are **micro-units** (e.g. `420000` → `0.42 EUR/kWh`).

## Docker Compose (TeslaMate)

Clone next to your TeslaMate compose file:

```bash
git clone https://github.com/TUNER88/teslamate-supercharger-cost-estimator.git
mkdir -p suc-estimator-cache
```

Paste the service from [`deploy/docker-compose.snippet.yml`](deploy/docker-compose.snippet.yml) into the same compose file as `database`. Set `DATABASE_PASS` to the same password as TeslaMate Postgres.

```bash
docker compose build suc-estimator
docker compose run --rm suc-estimator --dry-run
docker compose run --rm suc-estimator
```

Suggested cron (invoices are not involved; twice daily is plenty):

```cron
0 6,18 * * * cd /path/to/teslamate && docker compose run --rm suc-estimator
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
| `CACHE_TTL_SECONDS` | `43200` | Rate cache lifetime |

CLI flags mirror these (`--dry-run`, `--lookback-days`, `--match-radius-m`, `--overwrite`, …).

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
