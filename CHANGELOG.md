# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Always skip **AC** charging sessions before geo-matching (TeslaMate Grafana
  `charger_phases` mode rule: null/0 → DC, else AC). Home / destination AC is
  ignored automatically; only DC / Supercharger-like sessions are considered.
  No config flag. Processes with no charge samples are treated as DC so sparse
  SuC data is still matched. AC skips are logged once at INFO per session id
  (`skip id=… AC (charger_phases)`); repeats stay at DEBUG and count toward
  `skipped` in quiet no-op passes.

## [0.4.1] - 2026-09-23

### Changed

- Unmatched sessions are logged once at INFO per process (session id, geofence/place, nearest station + metres); repeats stay at DEBUG
- Unchanged no-op loop passes collapse to a single INFO line (`No changes since last pass`) instead of re-logging Fetching/Loaded/Connecting/Candidate/Done
- `httpx` / `httpcore` loggers are raised to WARNING so rate fetches do not spam INFO

## [0.4.0] - 2026-09-22

### Added

- README project preview image (`docs/assets/social-preview.svg`) for discoverability
- Support for stations that publish **per-minute, power-tiered** tariffs
  (`pricingUnit: minute`, e.g. Innsbruck, Bregenz, Morocco). They are parsed
  from the feed, matched to sessions, and estimated from session duration and
  average power (`energy / duration` picks the published bracket). Previously
  such stations were dropped entirely, so sessions there showed as
  "unmatched" or could be matched to a *different* nearby kWh-priced station.
- Stale-cache fallback: if the rates download fails (network outage, 5xx) and
  a cached copy exists, the run continues with the stale copy and logs a
  warning instead of crashing — scheduled runs survive transient outages.
- Per-car cost summary: `car_id` is now selected from the DB and the final log
  lists each car's session count and estimated total.
- Warning for unmatched sessions whose geofence name identifies a
  Supercharger (e.g. "Innsbruck Supercharger") but which found no priced
  station within the match radius — surfaces stations missing from the feed.

### Changed

- `rate_at` / `select_window` now work over both kWh windows and per-minute
  windows; `crosses_tou_window` compares windows structurally so it applies
  to both tariff kinds.

## [0.3.0] - 2026-09-21

### Added

- Long-running loop mode via `UPDATE_INTERVAL_SECONDS` / `--update-interval-seconds` (TeslaMateAgile-style)
- Compose example uses `restart: always` (no host cron required)

### Changed

- Default `UPDATE_INTERVAL_SECONDS` is **3600** (loop hourly). Set `0` for a one-shot run (manual/cron)

## [0.2.0] - 2026-09-21

### Added

- `DRY_RUN` environment variable (default `false`) and `suc-estimator --version`
- Docker image tags from `pyproject.toml` version (`0.2.0`, `0.2`, `latest`) plus git tag releases
- Shared / fleet vehicle coverage called out in the README
- Skip sessions that cross a time-of-use (TOU) rate change by default; opt in with `ALLOW_CROSS_TOU`
- Automatic GitHub Release when the version in `pyproject.toml` is new on `main`

### Changed

- Docker image no longer defaults to `--dry-run`; a plain run writes costs
- Compose example shows only required `DATABASE_PASS`; full env table in the README

## [0.1.1] - 2026-09-21

### Added

- Public-rate Supercharger cost estimator for TeslaMate (no Tesla account)
- GHCR image `ghcr.io/tuner88/teslamate-supercharger-cost-estimator`

[Unreleased]: https://github.com/TUNER88/teslamate-supercharger-cost-estimator/compare/v0.4.1...HEAD
[0.4.1]: https://github.com/TUNER88/teslamate-supercharger-cost-estimator/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/TUNER88/teslamate-supercharger-cost-estimator/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/TUNER88/teslamate-supercharger-cost-estimator/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/TUNER88/teslamate-supercharger-cost-estimator/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/TUNER88/teslamate-supercharger-cost-estimator/releases/tag/v0.1.1
